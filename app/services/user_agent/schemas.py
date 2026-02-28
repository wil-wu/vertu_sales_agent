import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field


class UserSimulationRequest(BaseModel):
    """仿真测试请求模型"""

    persona: str = Field(..., description="用户人格类型：professional/novice/confrontational/anxious/bilingual")
    scenario: str = Field(..., description="测试场景描述，例如：VERTU手机技术支持咨询")
    max_turns: int = Field(default=20, description="最大对话轮数，默认20轮")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="会话 ID，用于跟踪对话上下文"
    )


class ConversationMessage(BaseModel):
    """对话消息模型"""
    role: str = Field(..., description="消息角色：user_agent 或 target_bot")
    content: str = Field(..., description="消息内容")
    timestamp: str = Field(..., description="时间戳")


class SessionMetadata(BaseModel):
    """会话元数据"""
    start_time: str = Field(..., description="会话开始时间")
    end_time: str = Field(..., description="会话结束时间")
    total_turns: int = Field(..., description="总对话轮数")


class UserSimulationResponse(BaseModel):
    """仿真测试响应模型"""

    session_id: str = Field(..., description="会话ID")
    finish_reason: str = Field(..., description="结束原因: max_turns/human_escalation/invalid_responses")
    persona: str = Field(..., description="使用的人格类型")
    prompt: Optional[str] = Field(None, description="预设提示")
    conversation: List[Dict[str, Any]] = Field(..., description="完整对话记录")
    metadata: SessionMetadata = Field(..., description="会话元数据")
