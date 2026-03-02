"""用户智能体依赖注入模块"""

from .agent import UserAgent
from .shared import chat_model
from .prompts import USER_AGENT_SYSTEM_PROMPT


def get_user_agent() -> UserAgent:
    """获取用户智能体实例"""
    return UserAgent(
        chat_model=chat_model,
        system_prompt=USER_AGENT_SYSTEM_PROMPT,
    )
