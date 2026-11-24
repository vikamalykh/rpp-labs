import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app import db


#тестовые меню пяти ресторанов
menus = {
    "Север": "Борщ,Грибной суп,Винегрет,Пельмени,Котлета,Картофельное пюре,Гречка,Блины,Сырники,Морс",
    "Базилик": "Маргарита,Пепперони,Четыре сыра,Карбонара,Паста с грибами,Лазанья,Ризотто,Брускетта,Тирамису,Лимонад",
    "Лотос": "Том ям,Рамен,Удон,Курица терияки,Рис с овощами,Гёдза,Спринг-роллы,Салат с тофу,Моти,Зелёный чай",
    "Сад": "Тыквенный суп,Овощной салат,Хумус,Фалафель,Запечённые овощи,Паста с томатами,Булгур,Овощной боул,Кекс,Компот",
    "Уголь": "Куриный шашлык,Люля-кебаб,Стейк,Куриные крылья,Бургер,Картофель,Овощи гриль,Коулслоу,Лепёшка,Чай",
}


#добавляем тестовые рестораны, блюда и заказы
async def seed():
    await db.create_tables()
    async with db.Session() as session:
        #пропускаем заполнение, если рестораны уже добавлены
        if await session.scalar(select(db.Restaurant.id).limit(1)) is not None:
            print("Рестораны уже есть в базе. Повторное заполнение пропущено.")
            return

        #добавляем рестораны и получаем их id
        restaurants = [
            db.Restaurant(name=name, address=f"ул. Центральная, {number}")
            for number, name in enumerate(menus, start=1)
        ]
        session.add_all(restaurants)
        await session.flush()

        #заполняем меню каждого ресторана
        dishes_by_restaurant = []
        for restaurant in restaurants:
            dishes = [
                db.Dish(restaurant_id=restaurant.id, name=name, price=Decimal(250 + 30 * index))
                for index, name in enumerate(menus[restaurant.name].split(","))
            ]
            dishes_by_restaurant.append(dishes)
            session.add_all(dishes)
        await session.flush()

        #распределяем заказы поровну между пятью состояниями
        statuses = list(db.OrderStatus)
        start = datetime.now(timezone.utc) - timedelta(minutes=100)
        orders = []
        order_dishes = []
        for index in range(100):
            restaurant_index = index % 5
            status = statuses[(index + index // 5) % len(statuses)]
            menu = dishes_by_restaurant[restaurant_index]
            first = (index // 5) % len(menu)
            dishes = [menu[first], menu[(first + 1) % len(menu)]]
            orders.append(db.Order(
                restaurant_id=restaurants[restaurant_index].id,
                customer_name=f"Клиент {index + 1:03d}",
                delivery_address=f"ул. Садовая, {index + 1}",
                status=status,
                cancel_reason="Изменились планы" if status == db.OrderStatus.CANCELLED else None,
                total=dishes[0].price + 2 * dishes[1].price,
                created_at=start + timedelta(minutes=index),
            ))
            order_dishes.append(dishes)
        session.add_all(orders)
        await session.flush()

        #сохраняем позиции и их цены для каждого заказа
        for order, dishes in zip(orders, order_dishes):
            session.add_all([
                db.OrderItem(order_id=order.id, dish_id=dish.id, quantity=quantity, price=dish.price)
                for quantity, dish in enumerate(dishes, start=1)
            ])
        await session.commit()
    print("Добавлены 5 ресторанов, 50 блюд и 100 заказов.")


if __name__ == "__main__":
    asyncio.run(seed())
