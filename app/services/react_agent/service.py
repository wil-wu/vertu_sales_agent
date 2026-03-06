import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log
)

from app.core.shared import httpx_async_client
from .config import react_agent_settings

logger = logging.getLogger(__name__)

_retry = retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, max=10),
    retry=retry_if_exception_type(httpx.RequestError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class ReactAgentService:

    @staticmethod
    @_retry
    async def faq_query(query: str) -> Any:
        """查询 FAQ 知识库。"""
        response = await httpx_async_client.post(
            react_agent_settings.faq_url, json={"query": query}
        )
        items = response.json()["categories"][0]["items"][: react_agent_settings.faq_top_n]
        return [item["answer"] for item in items]

    @staticmethod
    @_retry
    async def graph_query(query: str) -> Any:
        """查询图谱素材。"""    
        response = await httpx_async_client.post(
            react_agent_settings.graph_url,
            json={"query": query},
            timeout=20,
        )
        return response.json()["data"]["result"]

    @staticmethod
    @_retry
    async def send_wechat_notification(content: str) -> Any:
        """发送微信通知。"""
        url = react_agent_settings.wechat_push_url
        headers = {
            "Authorization": f"Bearer {react_agent_settings.wechat_push_token}",
            "X-API-Key": react_agent_settings.wechat_push_api_key,
        }
        payload = {"content": content, "ats": ""}
        params = {"nickName": react_agent_settings.wechat_push_group_name}

        await httpx_async_client.post(
            url, json=payload, headers=headers, params=params
        )
        return "微信通知发送成功。"

    @staticmethod
    @_retry
    async def get_product_price(index_name: str, query: str) -> Any:
        """查询平台产品价格。"""
        response = await httpx_async_client.post(
            react_agent_settings.product_info_url,
            json={"query": query, "index_name": index_name},
        )
        return response.json()
