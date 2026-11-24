from app import db, events
from app.db import OrderStatus


#ошибки, которые может вернуть операция с заказом
class NotFound(Exception):
    pass


class TransitionNotAllowed(Exception):
    pass


class OrderValidationError(Exception):
    pass


#допустимые переходы между состояниями
transitions = {
    "accept": ({OrderStatus.CREATED}, OrderStatus.ACCEPTED),
    "mark_ready": ({OrderStatus.ACCEPTED}, OrderStatus.READY),
    "mark_delivered": ({OrderStatus.READY}, OrderStatus.DELIVERED),
    "cancel": ({OrderStatus.CREATED, OrderStatus.ACCEPTED}, OrderStatus.CANCELLED),
}


#проверяем идентификатор перед обращением к базе
def parse_id(value: str, entity: str):
    try:
        number = int(value)
    except ValueError:
        raise NotFound(f"{entity} с идентификатором {value} не найден") from None
    if not 1 <= number <= 2_147_483_647:
        raise NotFound(f"{entity} с идентификатором {value} не найден")
    return number


#проверяем данные заказа и сохраняем его вместе с позициями
async def create_order(restaurant_id: str, customer_name: str, delivery_address: str,
                       items: list[tuple[str, int]]):
    #проверяем имя, адрес и количество порций
    if not 1 <= len(items) <= 10:
        raise OrderValidationError("В заказе должно быть от 1 до 10 позиций")
    if not customer_name.strip() or not delivery_address.strip():
        raise OrderValidationError("Укажите имя клиента и адрес доставки")
    if any(not 1 <= quantity <= 20 for _, quantity in items):
        raise OrderValidationError("Количество порций должно быть от 1 до 20")

    #проверяем ресторан и его меню
    rid = parse_id(restaurant_id, "Ресторан")
    if await db.get_restaurant(rid) is None:
        raise NotFound(f"Ресторан {rid} не найден")

    dish_ids = [parse_id(dish_id, "Блюдо") for dish_id, _ in items]
    dishes = await db.get_dishes(dish_ids)
    positions = []
    for dish_id, (_, quantity) in zip(dish_ids, items):
        dish = dishes.get(dish_id)
        if dish is None:
            raise NotFound(f"Блюдо {dish_id} не найдено")
        if dish.restaurant_id != rid:
            raise OrderValidationError(f"Блюдо {dish_id} не принадлежит ресторану {rid}")
        #сохраняем цену блюда на момент оформления
        positions.append(db.OrderItem(dish_id=dish_id, quantity=quantity, price=dish.price))

    order = db.Order(
        restaurant_id=rid,
        customer_name=customer_name.strip(),
        delivery_address=delivery_address.strip(),
        status=OrderStatus.CREATED,
        total=sum(item.price * item.quantity for item in positions),
    )
    #сохраняем заказ и позиции в одной транзакции
    async with db.Session() as session:
        session.add(order)
        await session.flush()
        for item in positions:
            item.order_id = order.id
        session.add_all(positions)
        await session.commit()
    events.publish(events.OrderStatusChanged(order.id, order.status))
    return order


#проверяем переход, сохраняем состояние и отправляем событие
async def change_status(order_id: str, action: str, reason: str | None = None):
    order_id = parse_id(order_id, "Заказ")
    allowed, new_status = transitions[action]
    async with db.Session() as session:
        #блокируем строку до завершения изменения состояния
        order = await session.get(db.Order, order_id, with_for_update=True)
        if order is None:
            raise NotFound(f"Заказ {order_id} не найден")
        if order.status not in allowed:
            raise TransitionNotAllowed(f"Событие {action} недопустимо в состоянии {order.status.value}")
        if action == "cancel":
            reason = (reason or "").strip()
            if not 3 <= len(reason) <= 200:
                raise OrderValidationError("Причина отмены должна содержать от 3 до 200 символов")
            order.cancel_reason = reason
        order.status = new_status
        await session.commit()
        events.publish(events.OrderStatusChanged(order.id, order.status, order.cancel_reason))
    return order


#принимаем созданный заказ
async def accept(order_id: str):
    return await change_status(order_id, "accept")


#отмечаем принятый заказ готовым
async def mark_ready(order_id: str):
    return await change_status(order_id, "mark_ready")


#отмечаем готовый заказ доставленным
async def mark_delivered(order_id: str):
    return await change_status(order_id, "mark_delivered")


#отменяем заказ с указанием причины
async def cancel(order_id: str, reason: str):
    return await change_status(order_id, "cancel", reason)
