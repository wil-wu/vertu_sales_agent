"""Referee Agent依赖注入模块"""

from .agent import RefereeAgent
from .shared import chat_model


def get_referee_agent() -> RefereeAgent:
    """获取RefereeAgent实例"""
    return RefereeAgent(
        chat_model=chat_model,
    )
