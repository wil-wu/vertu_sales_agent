"""问题池生成服务共享资源模块"""

import logging

from langchain_openai import ChatOpenAI

from .config import question_pool_settings

logger = logging.getLogger(__name__)

# 聊天模型实例
chat_model = ChatOpenAI(
    api_key=question_pool_settings.openai_api_key,
    base_url=question_pool_settings.openai_base_url,
    model=question_pool_settings.llm_model,
    temperature=0.7,
    max_tokens=4000,
)
