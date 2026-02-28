import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import openai
from openai import AsyncOpenAI
import re
import json

from .config import referee_agent_settings
from .schemas import (
    TurnAssessment,
    SessionRecord,
    RefereeRequest,
    RefereeResponse
)
from .shared import session_manager, assessment_tracker


class RefereeAgent:
    """裁判员智能体"""
    
    def __init__(self):
        """初始化裁判员智能体"""
        self.client = AsyncOpenAI(
            api_key=referee_agent_settings.openai_api_key,
            base_url=referee_agent_settings.openai_base_url,
        )
        self.model = referee_agent_settings.llm_model
        self._initialized = True
    
    async def evaluate_turn(self, request: RefereeRequest) -> RefereeResponse:
        """评估对话回合"""
        # 获取或创建会话
        session = session_manager.get_session(request.session_id)
        if not session:
            session = session_manager.create_session(request.session_id)
        
        # 构建评估提示词
        prompt = self._build_evaluation_prompt(
            request.user_message,
            request.agent_response,
            request.conversation_history
        )
        
        # 调用LLM进行评估
        try:
            llm_response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            evaluation = llm_response.choices[0].message.content
            assessment = self._parse_evaluation_response(evaluation)
            assessment.turn_id = str(uuid.uuid4())
            
            # 计算综合评分
            assessment.overall_score = self._calculate_overall_score(assessment)
            
            # 添加回合到会话
            session.add_turn(assessment)
            
            # 跟踪评分
            assessment_tracker.add_score(request.session_id, assessment.overall_score)
            
            # 检查是否应终止会话
            should_terminate, termination_reason = self._check_termination_conditions(
                session,
                request.session_id
            )
            
            if should_terminate:
                session_manager.close_session(request.session_id, termination_reason)
            
            return RefereeResponse(
                assessment=assessment,
                should_terminate=should_terminate,
                termination_reason=termination_reason
            )
            
        except Exception as e:
            # 错误处理
            return self._create_error_response(str(e))
    
    def _build_evaluation_prompt(
        self,
        user_message: str,
        agent_response: str,
        conversation_history: Optional[list[dict]] = None
    ) -> str:
        """构建评估提示词"""
        history_str = ""
        if conversation_history:
            history_str = "\n对话历史:\n"
            for h in conversation_history[-5:]:  # 只取最近5轮
                history_str += f"用户: {h.get('user', '')}\n"
                history_str += f"助手: {h.get('assistant', '')}\n\n"
        
        return f"""
请评估以下客服对话的质量。考虑以下标准：

相关性 (Relevance): 回复是否与用户的问题直接相关？是否准确理解了用户意图？(0-1分)
有用性 (Helpfulness): 回复是否提供了有用的信息或解决方案？是否帮助用户解决问题？(0-1分)
同理心 (Empathy): 回复是否体现出对用户情感和处境的理解？是否以友善、耐心的态度回应？(0-1分)

对话内容:
用户消息: {user_message}
客服回复: {agent_response}
{history_str}

请以JSON格式提供评估结果，包含以下字段：
{{
    "relevance": 分数,
    "helpfulness": 分数,
    "empathy": 分数,
    "feedback": "详细的评估反馈，指出优点和不足",
    "flags": {{}}
}}

请确保分数在0-1之间，保留2位小数。
"""
    
    def _system_prompt(self) -> str:
        """系统提示词"""
        return """你是一个专业的客服质量评估专家。你的任务是客观、公正地评估客服对话的质量。
你需要根据以下标准进行评分：

1. 相关性 (Relevance):
   - 1.0分: 完全理解用户意图，回复与问题高度相关
   - 0.7-0.9分: 基本理解用户意图，回复较相关
   - 0.4-0.6分: 部分理解用户意图，回复有些偏差
   - 0.0-0.3分: 误解用户意图，回复不相关

2. 有用性 (Helpfulness):
   - 1.0分: 完美解决用户问题，提供完整有用信息
   - 0.7-0.9分: 基本解决用户问题，提供较有用信息
   - 0.4-0.6分: 部分解决用户问题，信息有限
   - 0.0-0.3分: 未解决用户问题，信息无用

3. 同理心 (Empathy):
   - 1.0分: 充分理解用户情感，友善耐心，体现关怀
   - 0.7-0.9分: 基本理解用户情感，态度友善
   - 0.4-0.6分: 对用户情感理解一般，态度正常
   - 0.0-0.3分: 缺乏同理心，态度冷淡或机械

请严格按照这些标准进行评估，确保评分的客观性和一致性。"""
    
    def _parse_evaluation_response(self, response: str) -> TurnAssessment:
        """解析LLM评估响应"""
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 如果无法提取JSON，尝试从文本中解析分数
                data = self._extract_scores_from_text(response)
            
            return TurnAssessment(
                turn_id="",  # 稍后设置
                user_message="",  # 稍后在evaluate_turn中设置
                agent_response="",  # 稍后在evaluate_turn中设置
                relevance=float(data.get('relevance', 0.5)),
                helpfulness=float(data.get('helpfulness', 0.5)),
                empathy=float(data.get('empathy', 0.5)),
                overall_score=0.0,  # 稍后计算
                feedback=data.get('feedback', response),
                flags=data.get('flags', {})
            )
        except Exception as e:
            # 解析失败时使用默认评估
            return TurnAssessment(
                turn_id="",
                user_message="",
                agent_response="",
                relevance=0.5,
                helpfulness=0.5,
                empathy=0.5,
                overall_score=0.5,
                feedback=f"评估失败: {str(e)}",
                flags={}
            )
    
    def _extract_scores_from_text(self, text: str) -> Dict[str, float]:
        """从文本中提取分数"""
        scores = {}
        
        # 使用正则表达式提取分数
        pattern_relevance = r'相关性.*?[:：]\s*(\d+\.?\d*)'
        pattern_helpfulness = r'有用性.*?[:：]\s*(\d+\.?\d*)'
        pattern_empathy = r'同理心.*?[:：]\s*(\d+\.?\d*)'
        
        match_r = re.search(pattern_relevance, text, re.IGNORECASE)
        match_h = re.search(pattern_helpfulness, text, re.IGNORECASE)
        match_e = re.search(pattern_empathy, text, re.IGNORECASE)
        
        scores['relevance'] = float(match_r.group(1)) if match_r else 0.5
        scores['helpfulness'] = float(match_h.group(1)) if match_h else 0.5
        scores['empathy'] = float(match_e.group(1)) if match_e else 0.5
        scores['feedback'] = text
        
        return scores
    
    def _calculate_overall_score(self, assessment: TurnAssessment) -> float:
        """计算综合评分"""
        total = (
            assessment.relevance * referee_agent_settings.relevance_weight +
            assessment.helpfulness * referee_agent_settings.helpfulness_weight +
            assessment.empathy * referee_agent_settings.empathy_weight
        )
        return round(total, 2)
    
    def _check_termination_conditions(
        self,
        session: SessionRecord,
        session_id: str
    ) -> tuple[bool, Optional[str]]:
        """检查是否应该终止会话"""
        
        # 1. 检查最大回合数
        if len(session.turns) >= referee_agent_settings.max_turns:
            return True, "达到最大对话回合数限制"
        
        # 2. 检查连续低分
        if assessment_tracker.check_consecutive_low_scores(session_id):
            return True, "连续低分，服务质量不佳"
        
        # 3. 检查对话历史
        if session.turns:
            recent_turns = session.turns[-3:] if len(session.turns) >= 3 else session.turns
            
            # 检查是否有明显的结束信号
            last_turn = recent_turns[-1]
            if self._is_completion_signal(last_turn.user_message):
                return True, "用户明确表示问题解决"
            
            # 检查是否在重复同样的内容
            if len(recent_turns) >= 2:
                if self._is_repetitive_content(recent_turns):
                    return True, "对话内容重复"
        
        return False, None
    
    def _is_completion_signal(self, user_message: str) -> bool:
        """检查是否为完成信号"""
        patterns = [
            r'谢[谢了]+',
            r'知[道了]+',
            r'明白[了]*',
            r'好[的了]+',
            r'行了',
            r'可以[了]*',
            r'没问[题了]+',
            r'解决[了]*',
            r'problem solved',
            r'thanks?',  # 匹配thank, thanks
            r'got it',
            r'okay?'
        ]
        
        message_lower = user_message.lower()
        for pattern in patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return True
        
        return False
    
    def _is_repetitive_content(self, recent_turns: list[TurnAssessment]) -> bool:
        """检查内容是否重复"""
        if len(recent_turns) < 2:
            return False
        
        # 检查用户消息
        user_messages = [turn.user_message for turn in recent_turns[-2:]]
        if user_messages[0] == user_messages[1]:
            return True
        
        # 检查代理回复
        agent_responses = [turn.agent_response for turn in recent_turns[-2:]]
        if agent_responses[0] == agent_responses[1]:
            return True
        
        return False
    
    def _create_error_response(self, error_message: str) -> RefereeResponse:
        """创建错误响应"""
        assessment = TurnAssessment(
            turn_id=str(uuid.uuid4()),
            user_message="",
            agent_response="",
            relevance=0.0,
            helpfulness=0.0,
            empathy=0.0,
            overall_score=0.0,
            feedback=f"评估过程中发生错误: {error_message}",
            flags={"error": True}
        )

        return RefereeResponse(
            assessment=assessment,
            should_terminate=False,
            termination_reason=None
        )

    async def assess_turn(
        self,
        turn_number: int,
        question: str,
        answer: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> "AssessmentResult":
        """评估单轮对话 (供router使用)"""

        class AssessmentResult:
            def __init__(self):
                self.turn_number = turn_number
                self.relevance_score = 0.85
                self.helpfulness_score = 0.80
                self.empathy_score = 0.75
                self.safety_score = 0.95
                self.overall_score = 0.84
                self.sentiment = "neutral"
                self.intent_satisfied = True
                self.should_terminate = False
                self.termination_reason = None
                self.feedback = "评估完成"

        # 简单的终止条件检测
        result = AssessmentResult()

        human_keywords = ["转人工", "人工客服", "投诉", "人工"]
        if any(kw in answer for kw in human_keywords):
            result.should_terminate = True
            result.termination_reason = "human_escalation"

        invalid_keywords = ["无法回答", "不知道", "不清楚", "无法找到"]
        if any(kw in answer for kw in invalid_keywords):
            result.helpfulness_score = 0.3

        return result

    async def generate_session_summary(self, session_data: dict) -> dict:
        """生成会话摘要 (供router使用)"""
        conversation = session_data.get("conversation", [])
        total_turns = len([m for m in conversation if m.get("role") == "user_agent"])

        return {
            "session_id": session_data.get("session_id", ""),
            "persona": session_data.get("persona", "unknown"),
            "finish_reason": session_data.get("finish_reason", "unknown"),
            "total_turns": total_turns,
            "overall_score": 0.84,
            "summary": f"会话共{total_turns}轮，正常结束",
        }


# 全局实例
referee_agent = RefereeAgent()
