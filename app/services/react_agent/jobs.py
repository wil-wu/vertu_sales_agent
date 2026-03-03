import logging

from apscheduler.triggers.cron import CronTrigger

from app.core.shared import httpx_sync_client, scheduler
from .config import react_agent_settings
from .shared import data_manager

logger = logging.getLogger(__name__)


def update_product_realtime_info_job():
    """
    更新产品实时信息
    """
    logger.info("--- [JOB] 更新产品实时信息 ---")

    all_products = []
    page = 1
    per_page = 50

    while True:
        response = httpx_sync_client.get(
            f"{react_agent_settings.product_info_url}/products",
            headers={"Authorization": f"Basic {react_agent_settings.product_info_token}"},
            params={"page": page, "per_page": per_page},
            timeout=20,
        )
        products = [
            {
                "id": product.get("id"),
                "sku": product.get("sku"),
                "name": product.get("name"),
                "price": product.get("price"),
                "regular_price": product.get("regular_price"),
                "currency": "USD",
                "stock_status": product.get("stock_status"),
                "stock_quantity": product.get("stock_quantity"),
            }
            for product in response.json()
        ]

        all_products.extend(products)
        logger.info(f"--- [JOB] 更新产品实时信息: {len(products)} 条 ---")

        if len(products) < per_page:
            break
        page += 1
    
    data_manager.update_data({"products": all_products})
    logger.info("--- [JOB] 更新产品实时信息完成 ---")


update_product_realtime_info_job()

scheduler.add_job(update_product_realtime_info_job, CronTrigger.from_crontab(react_agent_settings.product_info_crontab))
