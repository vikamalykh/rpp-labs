import asyncio
from collections import defaultdict
from dataclasses import dataclass

from app.db import OrderStatus


#данные события об изменении заказа
@dataclass(frozen=True)
class OrderStatusChanged:
    order_id: int
    status: OrderStatus
    cancel_reason: str | None = None


#у одного заказа может быть несколько подписчиков
queues: dict[int, set[asyncio.Queue[OrderStatusChanged]]] = defaultdict(set)


#создаём очередь для нового подписчика
def subscribe(order_id: int):
    queue = asyncio.Queue()
    queues[order_id].add(queue)
    return queue


#убираем очередь отключившегося подписчика
def unsubscribe(order_id: int, queue: asyncio.Queue):
    queues[order_id].discard(queue)
    if not queues[order_id]:
        del queues[order_id]


#передаём событие всем подписчикам этого заказа
def publish(event: OrderStatusChanged):
    for queue in queues.get(event.order_id, ()):
        queue.put_nowait(event)
