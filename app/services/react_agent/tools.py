import logging

from langchain_core.tools import tool

from app.core.shared import httpx_async_client
from .config import react_agent_settings

logger = logging.getLogger(__name__)


@tool
async def faq_query(query: str):
    """
    查询 FAQ 知识库，产品相关的咨询问题。
    """
    logger.info(f"--- [TOOL] 查询 FAQ: {query} ---")
    response = await httpx_async_client.post(
        react_agent_settings.faq_url, json={"query": query}
    )
    
    return [
        item["answer"]
        for item in response.json()["categories"][0]["items"][
            : react_agent_settings.faq_top_n
        ]
    ]


@tool
async def graph_query(query: str):
    """
    查询图谱，产品相关的图片、视频等素材内容。
    """
    logger.info(f"--- [TOOL] 查询图谱: {query} ---")
    response = await httpx_async_client.post(
        react_agent_settings.graph_url, json={"query": query}, timeout=20
    )
    return response.json()["result"]


@tool
async def send_wechat_notification(reason: str, user: str, platform: str) -> str:
    """
    遇到无法解决的问题，或用户主动要求转人工，发送微信通知。
    """
    content = f"用户：{user} 平台：{platform} 原因：{reason}"

    logger.info(f"--- [TOOL] 发送微信通知: {content} ---")

    url = react_agent_settings.wechat_push_url
    headers = {
        "Authorization": f"Bearer {react_agent_settings.wechat_push_token}",
        "X-API-Key": react_agent_settings.wechat_push_api_key,
    }

    payload = {"content": content, "ats": ""}

    params = {"nickName": react_agent_settings.wechat_push_group_name}

    try:
        await httpx_async_client.post(
            url, json=payload, headers=headers, params=params, timeout=10
        )
        return "微信通知发送成功。"
    except Exception as e:
        logger.error(f"--- [TOOL] 发送微信通知失败: {e} ---")
        return "微信通知发送失败，请稍后再试。"


TOOLS = [faq_query, graph_query, send_wechat_notification]
