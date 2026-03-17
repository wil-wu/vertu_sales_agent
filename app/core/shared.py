from httpx import AsyncClient, Client
from apscheduler.schedulers.background import BackgroundScheduler
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings

httpx_async_client = AsyncClient()
httpx_sync_client = Client()

scheduler = BackgroundScheduler()

postgres_async_pool = AsyncConnectionPool(
    conninfo=settings.postgres_url,
    min_size=1,
    max_size=10,
    open=False,
    kwargs={"autocommit": True},
)

postgres_checkpointer = AsyncPostgresSaver(postgres_async_pool)