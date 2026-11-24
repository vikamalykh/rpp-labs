import os
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import strawberry
from graphql import GraphQLError
from strawberry.dataloader import DataLoader
from strawberry.extensions import MaskErrors
from strawberry.types import Info

from app import db, events, services


#состояния заказа, используемые в схеме и подписке
OrderStatus = strawberry.enum(db.OrderStatus)
FINAL_STATES = {OrderStatus.DELIVERED, OrderStatus.CANCELLED}
STATUS_ORDER = list(OrderStatus)


#загружаем рестораны пакетом в порядке запрошенных id
async def load_restaurants(ids: list[int]):
    rows = await db.get_restaurants(ids)
    return [rows.get(id) for id in ids]


#загружаем блюда пакетом в порядке запрошенных id
async def load_dishes(ids: list[int]):
    rows = await db.get_dishes(ids)
    return [rows.get(id) for id in ids]


#загружаем позиции пакетом в порядке id заказов
async def load_items(ids: list[int]):
    rows = await db.get_items_by_orders(ids)
    return [rows[id] for id in ids]


#создаём загрузчики для текущего запроса
async def get_context():
    if os.getenv("USE_DATALOADER", "1") == "0":
        return {}
    return {
        "restaurants": DataLoader(load_fn=load_restaurants),
        "dishes": DataLoader(load_fn=load_dishes),
        "items": DataLoader(load_fn=load_items),
    }


#описание ресторана в схеме
@strawberry.type
class Restaurant:
    id: strawberry.ID
    name: str
    address: str

    #возвращаем меню этого ресторана
    @strawberry.field(graphql_type=list["Dish"])
    async def dishes(self):
        rows = await db.list_restaurant_dishes(int(self.id))
        return [to_dish(row) for row in rows]


#описание блюда в схеме
@strawberry.type
class Dish:
    id: strawberry.ID
    name: str
    price: Decimal
    restaurant_id: strawberry.Private[int]

    #возвращаем ресторан, в меню которого есть блюдо
    @strawberry.field(graphql_type=Restaurant)
    async def restaurant(self, info: Info):
        return await resolve_restaurant(info, self.restaurant_id)


#описание позиции заказа в схеме
@strawberry.type
class OrderItem:
    quantity: int
    price: Decimal
    dish_id: strawberry.Private[int]

    #считаем стоимость всей позиции
    @strawberry.field(graphql_type=Decimal)
    def amount(self):
        return self.price * self.quantity

    #загружаем блюдо для позиции
    @strawberry.field(graphql_type=Dish)
    async def dish(self, info: Info):
        loader = info.context.get("dishes")
        row = await (loader.load(self.dish_id) if loader else db.get_dish(self.dish_id))
        return to_dish(row)


#описание заказа в схеме
@strawberry.type
class Order:
    id: strawberry.ID
    status: OrderStatus
    total: Decimal
    created_at: datetime
    customer_name: str
    delivery_address: str
    cancel_reason: str | None
    restaurant_id: strawberry.Private[int]

    #загружаем ресторан для заказа
    @strawberry.field(graphql_type=Restaurant)
    async def restaurant(self, info: Info):
        return await resolve_restaurant(info, self.restaurant_id)

    #загружаем позиции заказа
    @strawberry.field(graphql_type=list[OrderItem])
    async def items(self, info: Info):
        order_id = int(self.id)
        loader = info.context.get("items")
        rows = await (loader.load(order_id) if loader else db.get_items(order_id))
        return [
            OrderItem(quantity=row.quantity, price=row.price, dish_id=row.dish_id)
            for row in rows
        ]


#преобразуем запись ресторана в тип схемы
def to_restaurant(row: db.Restaurant):
    return Restaurant(id=strawberry.ID(str(row.id)), name=row.name, address=row.address)


#преобразуем запись блюда в тип схемы
def to_dish(row: db.Dish):
    return Dish(
        id=strawberry.ID(str(row.id)), name=row.name, price=row.price,
        restaurant_id=row.restaurant_id,
    )


#преобразуем запись заказа в тип схемы
def to_order(row: db.Order):
    return Order(
        id=strawberry.ID(str(row.id)), status=row.status, total=row.total,
        created_at=row.created_at, customer_name=row.customer_name,
        delivery_address=row.delivery_address, cancel_reason=row.cancel_reason,
        restaurant_id=row.restaurant_id,
    )


#выбираем пакетное или одиночное чтение ресторана
async def resolve_restaurant(info: Info, restaurant_id: int):
    loader = info.context.get("restaurants")
    row = await (loader.load(restaurant_id) if loader else db.get_restaurant(restaurant_id))
    return to_restaurant(row)


#данные одной позиции нового заказа
@strawberry.input
class OrderItemInput:
    dish_id: strawberry.ID
    quantity: int


#данные для оформления заказа
@strawberry.input
class CreateOrderInput:
    restaurant_id: strawberry.ID
    customer_name: str
    delivery_address: str
    items: list[OrderItemInput]


#запросы на чтение данных
@strawberry.type
class Query:
    #возвращаем заказ по id, а при отсутствии возвращаем null
    @strawberry.field(graphql_type=Order | None)
    async def order(self, id: strawberry.ID):
        try:
            order_id = services.parse_id(id, "Заказ")
        except services.NotFound:
            return None
        row = await db.get_order(order_id)
        return to_order(row) if row else None

    #возвращаем список заказов с необязательным фильтром
    @strawberry.field(graphql_type=list[Order])
    async def orders(self, status: OrderStatus | None = None):
        return [to_order(row) for row in await db.list_orders(status)]

    #возвращаем список ресторанов
    @strawberry.field(graphql_type=list[Restaurant])
    async def restaurants(self):
        return [to_restaurant(row) for row in await db.list_restaurants()]


#мутации передают изменение заказа в модуль services
@strawberry.type
class Mutation:
    #оформляем заказ с переданными позициями
    @strawberry.mutation(graphql_type=Order | None)
    async def create_order(self, input: CreateOrderInput):
        return to_order(await services.create_order(
            input.restaurant_id, input.customer_name, input.delivery_address,
            [(item.dish_id, item.quantity) for item in input.items],
        ))

    #принимаем заказ в работу
    @strawberry.mutation(graphql_type=Order | None)
    async def accept_order(self, id: strawberry.ID):
        return to_order(await services.accept(id))

    #отмечаем заказ готовым
    @strawberry.mutation(graphql_type=Order | None)
    async def mark_order_ready(self, id: strawberry.ID):
        return to_order(await services.mark_ready(id))

    #отмечаем заказ доставленным
    @strawberry.mutation(graphql_type=Order | None)
    async def mark_order_delivered(self, id: strawberry.ID):
        return to_order(await services.mark_delivered(id))

    #передаём причину отмены заказа
    @strawberry.mutation(graphql_type=Order | None)
    async def cancel_order(self, id: strawberry.ID, reason: str):
        return to_order(await services.cancel(id, reason))


#подписка на изменения состояния заказа
@strawberry.type
class Subscription:
    #отправляем текущее состояние и следующие изменения
    @strawberry.subscription(graphql_type=Order)
    async def order_status_changed(self, order_id: strawberry.ID):
        oid = services.parse_id(order_id, "Заказ")
        #регистрируем очередь до чтения заказа
        queue = events.subscribe(oid)
        try:
            row = await db.get_order(oid)
            if row is None:
                raise services.NotFound(f"Заказ {oid} не найден")
            order = to_order(row)
            yield order
            while order.status not in FINAL_STATES:
                event = await queue.get()
                #пропускаем событие, если его состояние уже отразилось в первом чтении
                if STATUS_ORDER.index(event.status) <= STATUS_ORDER.index(order.status):
                    continue
                order = replace(order, status=event.status, cancel_reason=event.cancel_reason)
                yield order
        finally:
            events.unsubscribe(oid, queue)


#преобразуем ошибки приложения в ошибки graphql
class OrderErrors(MaskErrors):
    #применяем обработчик к ошибкам выполнения
    def __init__(self):
        super().__init__(should_mask_error=lambda error: error.original_error is not None)

    #выбираем сообщение и код ошибки для клиента
    def anonymise_error(self, error: GraphQLError):
        codes = {
            services.NotFound: "NOT_FOUND",
            services.TransitionNotAllowed: "TRANSITION_NOT_ALLOWED",
            services.OrderValidationError: "VALIDATION_ERROR",
        }
        code = codes.get(type(error.original_error))
        return GraphQLError(
            str(error.original_error) if code else "Internal error",
            nodes=error.nodes, source=error.source, positions=error.positions, path=error.path,
            extensions={"code": code or "INTERNAL_ERROR"},
        )


#собираем схему graphql из запросов, мутаций и подписок
schema = strawberry.Schema(
    query=Query, mutation=Mutation, subscription=Subscription, extensions=[OrderErrors],
)
