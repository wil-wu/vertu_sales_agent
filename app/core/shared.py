from httpx import AsyncClient, Client
from apscheduler.schedulers.background import BackgroundScheduler

httpx_async_client = AsyncClient()
httpx_sync_client = Client()

scheduler = BackgroundScheduler()
