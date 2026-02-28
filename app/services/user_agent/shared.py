"""用户智能体共享资源模块"""

import logging

from langchain_openai import ChatOpenAI

from .config import user_agent_settings

logger = logging.getLogger(__name__)

# 聊天模型实例
chat_model = ChatOpenAI(
    api_key=user_agent_settings.openai_api_key,
    base_url=user_agent_settings.openai_base_url,
    model=user_agent_settings.llm_model,
    temperature=0.7,
    max_tokens=4000,
)
