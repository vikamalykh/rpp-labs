import os
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


#возможные состояния заказа
class OrderStatus(str, Enum):
    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    READY = "READY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


#общая основа для моделей таблиц
class Base(DeclarativeBase):
    pass


#таблица ресторанов
class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    address: Mapped[str]


#таблица блюд и их цен
class Dish(Base):
    __tablename__ = "dishes"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"), index=True)
    name: Mapped[str]
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


#таблица заказов и их состояний
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id"))
    customer_name: Mapped[str]
    delivery_address: Mapped[str]
    status: Mapped[OrderStatus] = mapped_column(index=True)
    cancel_reason: Mapped[str | None]
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


#таблица позиций заказа с сохранённой ценой
class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    quantity: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


#выводим sql в журнал для подсчёта запросов
engine = create_async_engine(os.environ["DATABASE_URL"], echo=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


#создаём недостающие таблицы
async def create_tables():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


#получаем ресторан по одному id
async def get_restaurant(id: int):
    async with Session() as session:
        return await session.get(Restaurant, id)


#получаем блюдо по одному id
async def get_dish(id: int):
    async with Session() as session:
        return await session.get(Dish, id)


#получаем заказ по одному id
async def get_order(id: int):
    async with Session() as session:
        return await session.get(Order, id)


#получаем позиции одного заказа
async def get_items(order_id: int):
    async with Session() as session:
        rows = await session.scalars(
            select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
        )
        return rows.all()


#загружаем рестораны по списку id одним запросом
async def get_restaurants(ids: list[int]):
    async with Session() as session:
        rows = await session.scalars(select(Restaurant).where(Restaurant.id.in_(ids)))
        return {row.id: row for row in rows}


#загружаем блюда по списку id одним запросом
async def get_dishes(ids: list[int]):
    async with Session() as session:
        rows = await session.scalars(select(Dish).where(Dish.id.in_(ids)))
        return {row.id: row for row in rows}


#загружаем позиции нескольких заказов одним запросом
async def get_items_by_orders(order_ids: list[int]):
    async with Session() as session:
        rows = await session.scalars(
            select(OrderItem).where(OrderItem.order_id.in_(order_ids)).order_by(OrderItem.id)
        )
        #группируем позиции по заказам после одного запроса
        items = {order_id: [] for order_id in order_ids}
        for row in rows:
            items[row.order_id].append(row)
        return items


#выводим заказы от новых к старым с фильтром по состоянию
async def list_orders(status: OrderStatus | None = None):
    query = select(Order).order_by(Order.created_at.desc(), Order.id.desc())
    if status is not None:
        query = query.where(Order.status == status)
    async with Session() as session:
        return (await session.scalars(query)).all()


#получаем список всех ресторанов
async def list_restaurants():
    async with Session() as session:
        return (await session.scalars(select(Restaurant).order_by(Restaurant.id))).all()


#получаем меню одного ресторана
async def list_restaurant_dishes(restaurant_id: int):
    async with Session() as session:
        rows = await session.scalars(
            select(Dish).where(Dish.restaurant_id == restaurant_id).order_by(Dish.id)
        )
        return rows.all()
