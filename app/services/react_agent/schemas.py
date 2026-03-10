import uuid
from enum import Enum

from pydantic import BaseModel, Field


class Region(Enum):
    domestic = "国内"
    overseas = "海外"


class ReactAgentRequest(BaseModel):
    message: str = Field(..., description="输入消息")
    user_id: str = Field(..., description="用户ID")
    platform: str = Field(..., description="沟通平台")
    region: Region = Field(..., description="用户所在地区")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="会话 ID"
    )
    debug: bool = Field(False, description="是否调试模式")


class ReactAgentResponse(BaseModel):
    message: str = Field(..., description="回复消息")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="会话 ID"
    )
    debug_info: list = Field(..., description="调试信息")
