from contextlib import asynccontextmanager

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from app import db
from app.graphql import get_context, schema


#создаём таблицы при старте и закрываем соединения при остановке
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.create_tables()
    try:
        yield
    finally:
        await db.engine.dispose()


#подключаем graphql и редактор graphiql по адресу /graphql
app = FastAPI(lifespan=lifespan)
app.include_router(
    GraphQLRouter(schema, context_getter=get_context, graphql_ide="graphiql"),
    prefix="/graphql",
)
