import logging
from typing import Any

from langchain_core.tools import tool

from .service import ReactAgentService

logger = logging.getLogger(__name__)


def tool_result_ok(data: Any) -> dict[str, Any]:
    """构造成功的统一 tool 返回结果。"""
    return {"success": True, "data": data, "error": None}


def tool_result_fail(error: str) -> dict[str, Any]:
    """构造失败的统一 tool 返回结果。"""
    return {"success": False, "data": None, "error": error}


@tool
async def faq_query(collection_names: list, query: str):
    """
    查询 FAQ 知识库，产品相关的咨询问题。
    collection_names: 知识库名称，可选范围 [domestic, overseas]，中文用户选择 domestic，非中文用户选择 overseas
    query: 查询关键词
    """
    logger.info(f"--- [TOOL] 查询 FAQ: {collection_names} {query} ---")
    try:
        data = await ReactAgentService.faq_query(collection_names, query)
        return tool_result_ok(data)
    except Exception as e:
        exc_info = f"{e.__class__.__name__}: {e}"
        logger.warning(f"--- [TOOL] 查询 FAQ 失败: {exc_info} ---")
        return tool_result_fail(exc_info)


@tool
async def graph_query(query: str):
    """
    查询图谱，产品相关的图片、视频等素材内容。
    """
    logger.info(f"--- [TOOL] 查询图谱: {query} ---")
    try:
        data = await ReactAgentService.graph_query(query)
        return tool_result_ok(data)
    except Exception as e:
        exc_info = f"{e.__class__.__name__}: {e}"
        logger.warning(f"--- [TOOL] 查询图谱失败: {exc_info} ---")
        return tool_result_fail(exc_info)


@tool
async def send_wechat_notification(reason: str, user: str, platform: str):
    """
    遇到无法解决的问题，或用户主动要求转人工，发送微信通知。
    """
    content = f"用户：{user}\n平台：{platform}\n原因：{reason}"

    logger.info(f"--- [TOOL] 发送微信通知: \n{content} ---")
    try:
        data = await ReactAgentService.send_wechat_notification(content)
        return tool_result_ok(data)
    except Exception as e:
        exc_info = f"{e.__class__.__name__}: {e}"
        logger.warning(f"--- [TOOL] 发送微信通知失败: {exc_info} ---")
        return tool_result_fail(exc_info)


@tool
async def get_product_price(index_name: str, query: str):
    """
    查询各个平台的产品价格
    index_name: 平台索引名称，可选范围 [tm_product, jd_product, overseas_product]
                中文用户选择 tm_product 和 jd_product
                非中文用户选择 overseas_product
    query: 查询关键词，可能包含产品名称、型号、类型、颜色、材质、价格范围等
    """
    logger.info(f"--- [TOOL] 查询平台的产品价格: {index_name} {query} ---")
    try:
        data = await ReactAgentService.get_product_price(index_name, query)
        return tool_result_ok(data)
    except Exception as e:
        exc_info = f"{e.__class__.__name__}: {e}"
        logger.warning(f"--- [TOOL] 查询产品价格失败: {exc_info} ---")
        return tool_result_fail(exc_info)


TOOLS = [faq_query, graph_query, send_wechat_notification, get_product_price]
