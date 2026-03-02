from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class TurnAssessment(BaseModel):
    """对话回合评估模型"""
    
    turn_id: str = Field(..., description="回合标识符")
    user_message: str = Field(..., description="用户消息")
    agent_response: str = Field(..., description="智能体回复")
    relevance: float = Field(..., description="相关性评分 (0-1)")
    helpfulness: float = Field(..., description="有用性评分 (0-1)")
    empathy: float = Field(..., description="同理心评分 (0-1)")
    overall_score: float = Field(..., description="综合评分")
    feedback: Optional[str] = Field(None, description="评估反馈")
    flags: Optional[Dict[str, Any]] = Field(None, description="特殊标识")
    timestamp: datetime = Field(default_factory=datetime.now)


class SessionRecord(BaseModel):
    """会话记录模型"""
    
    session_id: str = Field(..., description="会话标识符")
    start_time: datetime = Field(..., description="会话开始时间")
    end_time: Optional[datetime] = Field(None, description="会话结束时间")
    turns: list[TurnAssessment] = Field(default_factory=list, description="评估回合列表")
    final_score: Optional[float] = Field(None, description="最终评分")
    termination_reason: Optional[str] = Field(None, description="终止原因")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    
    def add_turn(self, turn: TurnAssessment):
        """添加回合评估"""
        self.turns.append(turn)
    
    def calculate_final_score(self):
        """计算最终评分"""
        if self.turns:
            scores = [turn.overall_score for turn in self.turns]
            self.final_score = sum(scores) / len(scores)
        return self.final_score


class RefereeRequest(BaseModel):
    """裁判员请求模型"""
    
    session_id: str = Field(..., description="会话ID")
    user_message: str = Field(..., description="用户消息")
    agent_response: str = Field(..., description="智能体回复")
    conversation_history: Optional[list[dict]] = Field(None, description="对话历史")


class RefereeResponse(BaseModel):
    """裁判员响应模型"""

    assessment: TurnAssessment = Field(..., description="回合评估")
    should_terminate: bool = Field(False, description="是否应终止会话")
    termination_reason: Optional[str] = Field(None, description="终止原因")


class AssessmentRequest(BaseModel):
    """评估请求模型"""

    session_id: str = Field(..., description="会话ID")
    turn_number: int = Field(..., description="回合编号")
    question: str = Field(..., description="用户问题")
    answer: str = Field(..., description="机器人回答")
    conversation_history: Optional[list[dict]] = Field(None, description="对话历史")


class AssessmentResponse(BaseModel):
    """评估响应模型 - 销售与用户体验维度"""

    session_id: str = Field(..., description="会话ID")
    turn_number: int = Field(..., description="回合编号")
    
    # 1. 拟人程度评分 (0-1)
    anthropomorphism_score: float = Field(..., description="拟人程度评分 (0-1)，评估回复是否自然、像真人客服")
    
    # 2. 购买意愿评估
    purchase_intent_change: str = Field(..., description="购买意愿变化: improved(提升)/unchanged(不变)/declined(下降)")
    purchase_intent_reason: str = Field(..., description="购买意愿变化的判断依据")
    
    # 3. 问题解决情况
    problem_resolved: bool = Field(..., description="用户问题是否得到解决")
    problem_resolve_reason: str = Field(..., description="问题是否解决的判断依据")
    
    # 4. 销售话术质量 (优秀/良好/差)
    sales_script_quality: str = Field(..., description="销售话术质量: excellent(优秀)/good(良好)/poor(差)")
    sales_script_reason: str = Field(..., description="话术质量评价依据")
    
    # 5. 用户体验评价 (优/良/差)
    user_experience: str = Field(..., description="用户体验: excellent(优)/good(良)/poor(差)")
    user_experience_reason: str = Field(..., description="用户体验评价依据")
    
    # 是否终止会话
    should_terminate: bool = Field(..., description="是否应终止")
    termination_reason: Optional[str] = Field(None, description="终止原因")
    
    # 总体反馈建议
    feedback: Optional[str] = Field(None, description="总体评估反馈与改进建议")


class BatchAssessmentRequest(BaseModel):
    """批量评估请求模型"""

    session_ids: list[str] = Field(..., description="会话ID列表")


class SessionInfo(BaseModel):
    """会话信息模型"""

    session_id: str = Field(..., description="会话ID")
    persona: str = Field(..., description="人格类型")
    finish_reason: str = Field(..., description="结束原因")
    total_turns: int = Field(..., description="总轮数")
    created_at: str = Field(..., description="创建时间")


class SessionListResponse(BaseModel):
    """会话列表响应模型"""

    total: int = Field(..., description="总会话数")
    sessions: list[SessionInfo] = Field(..., description="会话列表")
