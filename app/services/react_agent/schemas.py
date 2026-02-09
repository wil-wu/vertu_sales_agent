import uuid

from pydantic import BaseModel, Field


class ReactAgentRequest(BaseModel):
    message: str = Field(..., description="输入消息")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="会话 ID"
    )


class ReactAgentResponse(BaseModel):
    message: str = Field(..., description="回复消息")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="会话 ID"
    )
