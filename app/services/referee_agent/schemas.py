from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ============ 详细评估指标模型 ============

class UserAnthropomorphismMetrics(BaseModel):
    """用户智能体(user_agent)拟人化体验指标 - 评估模拟用户的逼真程度"""
    language_naturalness: float = Field(0.0, description="语言自然度评分 (0-1)，评估用户提问是否流畅、口语化，像真实用户")
    personality_deviation_count: int = Field(0, description="用户人设偏离次数")
    humor_warmth: float = Field(0.0, description="幽默/温度感评分 (0-1)，评估用户表达是否有真实情感温度")
    rhythm_pacing: float = Field(0.0, description="停顿/节奏感评分 (0-1)，评估用户提问节奏是否像真人")
    response_length_distribution: Optional[Dict[str, int]] = Field(None, description="用户回复字数分布统计")


class AgentAnthropomorphismMetrics(BaseModel):
    """客服智能体(react_agent)拟人化体验指标 - 评估客服回复的拟人化程度"""
    language_naturalness: float = Field(0.0, description="语言自然度评分 (0-1)，评估客服回复是否流畅、口语化，避免机械感")
    personality_deviation_count: int = Field(0, description="客服人设偏离次数")
    humor_warmth: float = Field(0.0, description="幽默/温度感评分 (0-1)，评估适当使用轻松语气的能力")
    rhythm_pacing: float = Field(0.0, description="停顿/节奏感评分 (0-1)，评估回复长度和节奏是否像真人")
    response_length_distribution: Optional[Dict[str, int]] = Field(None, description="客服回复字数分布统计")


class PurchaseIntentMetrics(BaseModel):
    """购买意愿驱动指标"""
    needs_discovery_rate: float = Field(0.0, description="需求挖掘率 (0-1)，成功识别用户潜在需求的比率")
    product_recommendation_accuracy: float = Field(0.0, description="产品推荐精准度 (0-1)，推荐产品与需求的匹配程度")


class ProblemSolvingMetrics(BaseModel):
    """问题解决能力指标"""
    first_contact_resolution: bool = Field(False, description="首次解决率，本轮是否一次性解决问题")
    intent_recognition_accuracy: float = Field(0.0, description="意图识别准确率 (0-1)，正确理解用户问题的比率")
    fallback_rate: float = Field(0.0, description="兜底率 (0-1)，无法回答而需要转人工的频率")


class SalesScriptMetrics(BaseModel):
    """销售话术质量指标"""
    fab_completeness: float = Field(0.0, description="FAB 结构完整度 (0-1)，特性→优势→利益的表达完整性")
    feature_mentioned: bool = Field(False, description="是否提及产品特性 (Feature)")
    advantage_mentioned: bool = Field(False, description="是否提及产品优势 (Advantage)")
    objection_handling_success: Optional[bool] = Field(None, description="异议处理是否成功，对价格/质量异议的化解")
    objection_handling_score: float = Field(0.0, description="异议处理能力评分 (0-1)")
    cross_sell_triggered: bool = Field(False, description="是否触发交叉销售，主动推荐关联产品")
    script_compliance: float = Field(0.0, description="话术合规率 (0-1)，是否存在违规承诺/夸大宣传")
    personalization_rate: float = Field(0.0, description="个性化表达率 (0-1)，根据用户画像定制话术的比例")


class UserExperienceMetrics(BaseModel):
    """用户体验指标"""
    csat_score: float = Field(0.0, description="对话满意度评分 (0-1)，用户主观满意评分")
    negative_feedback_triggered: bool = Field(False, description="是否触发负面反馈/投诉")


class TraditionalScriptMetrics(BaseModel):
    """传统话术质量指标 - 评估专业名词通俗化解释能力"""
    technical_term_simplification: float = Field(0.0, description="专业名词通俗化解释评分 (0-1)，评估是否将专业术语转化为通俗易懂的白话描述")


class LanguageConsistencyMetrics(BaseModel):
    """语言一致性指标 - 评估用户-sales_agent问答中的语言一致性"""
    language_match: bool = Field(True, description="语言一致性，评估客服回复语言是否与用户提问语言一致")


class DetailedMetrics(BaseModel):
    """详细评估指标汇总（7大维度，每个维度满分100分）"""
    # 维度综合评分（0-100分）
    anthropomorphism_score: int = Field(0, description="拟人化体验维度综合评分（0-100分），基于user和agent的拟人化表现")
    purchase_intent_score: int = Field(0, description="购买意愿驱动维度综合评分（0-100分）")
    problem_solving_score: int = Field(0, description="问题解决能力维度综合评分（0-100分）")
    sales_script_score: int = Field(0, description="销售话术质量维度综合评分（0-100分）")
    user_experience_score: int = Field(0, description="用户体验维度综合评分（0-100分）")
    traditional_script_score: int = Field(0, description="传统话术质量维度综合评分（0-100分），评估专业名词通俗化解释能力，等于 technical_term_simplification * 100")
    language_consistency_score: int = Field(0, description="语言一致性维度综合评分（0-100分），评估用户-sales_agent问答中的语言一致性")
    
    # 各维度详细指标
    user_anthropomorphism: UserAnthropomorphismMetrics = Field(default_factory=UserAnthropomorphismMetrics, description="用户智能体拟人化体验指标")
    agent_anthropomorphism: AgentAnthropomorphismMetrics = Field(default_factory=AgentAnthropomorphismMetrics, description="客服智能体拟人化体验指标")
    purchase_intent: PurchaseIntentMetrics = Field(default_factory=PurchaseIntentMetrics, description="购买意愿驱动指标")
    problem_solving: ProblemSolvingMetrics = Field(default_factory=ProblemSolvingMetrics, description="问题解决能力指标")
    sales_script: SalesScriptMetrics = Field(default_factory=SalesScriptMetrics, description="销售话术质量指标")
    user_experience: UserExperienceMetrics = Field(default_factory=UserExperienceMetrics, description="用户体验指标")
    traditional_script: TraditionalScriptMetrics = Field(default_factory=TraditionalScriptMetrics, description="传统话术质量指标")
    language_consistency: LanguageConsistencyMetrics = Field(default_factory=LanguageConsistencyMetrics, description="语言一致性指标")


class TurnAssessment(BaseModel):
    """对话回合评估模型"""
    
    turn_id: str = Field(..., description="回合标识符")
    user_message: str = Field(..., description="用户消息")
    agent_response: str = Field(..., description="智能体回复")
    relevance: float = Field(..., description="相关性评分 (0-1)")
    helpfulness: float = Field(..., description="有用性评分 (0-1)")
    empathy: float = Field(..., description="同理心评分 (0-1)")
    overall_score: float = Field(..., description="综合评分")
    
    # 详细评估指标（新增）
    detailed_metrics: Optional[DetailedMetrics] = Field(None, description="详细评估指标")
    
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
    """评估响应模型 - 销售与用户体验维度（兼容旧版 + 新增详细指标）"""

    session_id: str = Field(..., description="会话ID")
    turn_number: int = Field(..., description="回合编号")
    
    # ========== 基础评估指标（保留兼容）==========
    # 1. 拟人程度评分 (0-1)
    agent_anthropomorphism_score: float = Field(..., description="客服拟人程度评分 (0-1)，评估客服回复是否自然、像真人客服")
    user_anthropomorphism_score: float = Field(..., description="用户拟人程度评分 (0-1)，评估用户提问是否自然、像真人用户")
    
    # 2. 购买意愿评估
    purchase_intent_change: str = Field(..., description="购买意愿变化: improved(提升)/unchanged(不变)/declined(下降)")
    
    # 3. 问题解决情况
    problem_resolved: bool = Field(..., description="用户问题是否得到解决")
    
    # 4. 销售话术质量 (优秀/良好/差)
    sales_script_quality: str = Field(..., description="销售话术质量: excellent(优秀)/good(良好)/poor(差)")
    
    # 5. 用户体验评价 (优/良/差)
    user_experience: str = Field(..., description="用户体验: excellent(优)/good(良)/poor(差)")
    
    # ========== 详细评估指标（新增）==========
    detailed_metrics: Optional[DetailedMetrics] = Field(None, description="详细评估指标，包含6大维度20+细分指标")
    should_terminate: bool = Field(..., description="是否应终止")
    termination_reason: Optional[str] = Field(None, description="终止原因")
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
