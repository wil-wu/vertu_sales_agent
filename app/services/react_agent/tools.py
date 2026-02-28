import logging

from langchain_core.tools import tool

from app.core.shared import httpx_client
from .config import react_agent_settings

logger = logging.getLogger(__name__)


@tool
async def faq_query(query: str):
    """
    查询 FAQ 知识库，产品相关的咨询问题。
    """
    logger.info(f"--- [TOOL] 查询 FAQ: {query} ---")
    response = await httpx_client.post(
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
    response = await httpx_client.post(
        react_agent_settings.graph_url, json={"query": query}, timeout=20
    )
    return response.json()["result"]


@tool
async def escalate_to_human(content: str) -> str:
    """
    遇到无法解决的问题，或用户主动要求转人工服务。
    """
    logger.info(f"--- [TOOL] 转人工: {content} ---")

    url = react_agent_settings.wechat_push_url
    headers = {
        "Authorization": f"Bearer {react_agent_settings.wechat_push_token}",
        "X-API-Key": react_agent_settings.wechat_push_api_key,
    }

    payload = {"content": content, "ats": ""}

    params = {"nickName": react_agent_settings.wechat_push_group_name}

    try:
        await httpx_client.post(
            url, json=payload, headers=headers, params=params, timeout=10
        )
        return "正在为您转接人工客服，请稍候。"
    except Exception as e:
        logger.error(f"--- [TOOL] 转人工失败: {e} ---")
        return "转接人工客服失败，请稍后再试。"


TOOLS = [faq_query, graph_query, escalate_to_human]
