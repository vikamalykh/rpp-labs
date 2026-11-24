# Лабораторная работа № 6 «Реализация GraphQL-интерфейса»

Сервис доставки еды на FastAPI, Strawberry и PostgreSQL. Команды выполняются из папки, в которой лежит `docker-compose.yml`.

```sh
docker compose up --build -d
docker compose run --rm api python -m app.seed
```

Откройте [GraphiQL](http://localhost:8000/graphql). Запросы, мутации и примеры ответов приведены в отчёте. Команда app.seed заполняет пустую базу 5 ресторанами, 50 блюдами и 100 заказами. Идентификаторы заказов, которые создаёте при проверке, берите из ответа `createOrder`.

## Сравнение числа SQL-запросов

На свежих демонстрационных данных сначала запустите API без загрузчиков.

```sh
USE_DATALOADER=0 docker compose up -d api
```

В PowerShell вместо этой команды выполните:

```powershell
$env:USE_DATALOADER = "0"
docker compose up -d api
```

В GraphiQL выполните запрос А трижды. В поле Variables последовательно введите `{"status":"CANCELLED"}`, `{"status":"READY"}` и `{}`.

```graphql
query A($status: OrderStatus) {
  orders(status: $status) {
    id status total customerName
    restaurant { name }
    items { quantity price dish { name } }
  }
}
```

Откройте журнал командой `docker compose logs -f api`. Для каждого запуска считайте строки SQLAlchemy с `SELECT`. Служебные строки транзакций, запросы при старте и строки с параметрами пропускайте.

Включите загрузчики и повторите те же три запуска.

```sh
USE_DATALOADER=1 docker compose up -d api
```

В PowerShell установите `$env:USE_DATALOADER = "1"`, затем выполните `docker compose up -d api`. По умолчанию загрузчики включены.

## Подписка

Создайте заказ и откройте GraphiQL в двух вкладках. В первой вкладке запустите подписку с идентификатором заказа, полученным при создании.

```graphql
subscription Watch($id: ID!) {
  orderStatusChanged(orderId: $id) { id status }
}
```

Дождитесь `CREATED`. Во второй вкладке выполните по очереди `acceptOrder`, `markOrderReady` и `markOrderDelivered` для того же заказа. Подписка получает `ACCEPTED`, `READY`, `DELIVERED` и завершается.

Для остановки проекта выполните `docker compose down`. Данные сохраняются в томе PostgreSQL.
