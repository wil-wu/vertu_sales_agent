"""用户智能体依赖注入模块"""

from .agent import UserAgent
from .prompts import USER_AGENT_SYSTEM_PROMPT


def get_user_agent() -> UserAgent:
    """获取用户智能体实例"""
    return UserAgent(
        system_prompt=USER_AGENT_SYSTEM_PROMPT,
    )
