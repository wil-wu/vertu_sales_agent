import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
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
        """构建评估提示词 - 销售与用户体验维度"""
        history_str = ""
        if conversation_history:
            history_str = "\n对话历史:\n"
            for h in conversation_history[-5:]:  # 只取最近5轮
                history_str += f"用户: {h.get('user', '')}\n"
                history_str += f"助手: {h.get('assistant', '')}\n\n"
        
        return f"""
你是一位专业的销售客服质量评估专家。请评估以下 VERTU 奢侈品手机客服对话的质量。

请从以下5个维度进行评估：

1. 拟人程度评分 (anthropomorphism_score):
   - 评估客服回复是否自然流畅，像真人客服而非机器
   - 0.0-0.3分: 明显机械，模板化严重
   - 0.4-0.6分: 有一定自然度，但仍有机器痕迹
   - 0.7-0.8分: 比较自然，接近真人
   - 0.9-1.0分: 非常自然，完全像专业真人客服

2. 购买意愿变化 (purchase_intent_change):
   - 评估这轮对话后，用户的购买意愿相比之前如何变化
   - 选项: "improved"(提升), "unchanged"(不变), "declined"(下降)
   - purchase_intent_reason: 说明判断依据

3. 问题解决情况 (problem_resolved):
   - 用户当前提出的问题是否得到了满意的解答
   - true: 问题已解决, false: 未解决
   - problem_resolve_reason: 说明判断依据

4. 销售话术质量 (sales_script_quality):
   - 评估客服的销售技巧和专业话术水平
   - "excellent"(优秀): 专业、有说服力、体现品牌价值
   - "good"(良好): 较为专业，基本达到销售标准
   - "poor"(差): 不专业、生硬、可能损害品牌形象
   - sales_script_reason: 说明评价依据

5. 用户体验评价 (user_experience):
   - 评估用户在这轮对话中的整体感受
   - "excellent"(优): 满意、愉悦、愿意继续交流
   - "good"(良): 基本满意，无明显不满
   - "poor"(差): 不满意、 frustrated、可能流失
   - user_experience_reason: 说明评价依据

对话内容:
用户消息: {user_message}
客服回复: {agent_response}
{history_str}

请以JSON格式提供评估结果，包含以下字段：
{{
    "anthropomorphism_score": 0.85,
    "purchase_intent_change": "improved",
    "purchase_intent_reason": "客服详细介绍了产品独特工艺，增强了用户购买兴趣",
    "problem_resolved": true,
    "problem_resolve_reason": "明确回答了用户关于保修期的问题",
    "sales_script_quality": "excellent",
    "sales_script_reason": "话术专业，适时强调品牌价值和稀缺性",
    "user_experience": "excellent",
    "user_experience_reason": "回复耐心细致，态度亲切",
    "feedback": "总体评价和改进建议"
}}

注意:
- anthropomorphism_score 必须是0-1之间的数字
- purchase_intent_change 只能是: improved/unchanged/declined
- sales_script_quality 只能是: excellent/good/poor
- user_experience 只能是: excellent/good/poor
- problem_resolved 必须是: true 或 false
"""
    
    def _system_prompt(self) -> str:
        """系统提示词 - 销售客服质量评估专家"""
        return """你是 VERTU 奢侈品手机的专业销售客服质量评估专家。

你的任务是从销售和用户体验角度，评估客服对话的质量。VERTU 是高端奢侈品牌，客服回复应当：
- 体现品牌的高端定位和专业形象
- 使用自然、亲切而非机械的话术
- 在解答问题的同时，适时传递品牌价值
- 提升用户的购买意愿，而非仅仅被动回答

评估时请注意：
1. 拟人程度：奢侈品客服应当像专业私人顾问，而非机器
2. 销售导向：评估对话是否有助于促成销售
3. 用户体验：客户感受直接影响购买决策
4. 问题解决：在保持品牌形象的前提下解决用户疑问

请严格按照评分标准进行评估，确保评价的客观性和一致性。"""
    
    def _parse_evaluation_response(self, response: str, user_message: str = "", agent_response: str = "") -> Dict[str, Any]:
        """解析LLM评估响应 - 新评估维度"""
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 如果无法提取JSON，使用默认值
                data = {}
            
            # 解析新维度的评估结果
            result = {
                # 1. 拟人程度评分 (0-1)
                "anthropomorphism_score": float(data.get('anthropomorphism_score', 0.5)),
                
                # 2. 购买意愿变化
                "purchase_intent_change": data.get('purchase_intent_change', 'unchanged'),
                "purchase_intent_reason": data.get('purchase_intent_reason', '未提供'),
                
                # 3. 问题解决情况
                "problem_resolved": data.get('problem_resolved', False),
                "problem_resolve_reason": data.get('problem_resolve_reason', '未提供'),
                
                # 4. 销售话术质量
                "sales_script_quality": data.get('sales_script_quality', 'good'),
                "sales_script_reason": data.get('sales_script_reason', '未提供'),
                
                # 5. 用户体验
                "user_experience": data.get('user_experience', 'good'),
                "user_experience_reason": data.get('user_experience_reason', '未提供'),
                
                # 反馈
                "feedback": data.get('feedback', response),
            }
            
            return result
        except Exception as e:
            # 解析失败时使用默认值
            return {
                "anthropomorphism_score": 0.5,
                "purchase_intent_change": 'unchanged',
                "purchase_intent_reason": f'解析失败: {str(e)}',
                "problem_resolved": False,
                "problem_resolve_reason": '解析失败',
                "sales_script_quality": 'good',
                "sales_script_reason": '解析失败',
                "user_experience": 'good',
                "user_experience_reason": '解析失败',
                "feedback": f'评估解析失败: {str(e)}',
            }
    
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
        """评估单轮对话 - 新评估维度 (供router使用)"""

        class AssessmentResult:
            def __init__(self):
                self.turn_number = turn_number
                
                # 1. 拟人程度
                self.anthropomorphism_score = 0.75
                
                # 2. 购买意愿变化
                self.purchase_intent_change = "unchanged"
                self.purchase_intent_reason = "暂无变化"
                
                # 3. 问题解决
                self.problem_resolved = True
                self.problem_resolve_reason = "问题已解答"
                
                # 4. 销售话术质量
                self.sales_script_quality = "good"
                self.sales_script_reason = "话术较为专业"
                
                # 5. 用户体验
                self.user_experience = "good"
                self.user_experience_reason = "体验良好"
                
                # 终止条件
                self.should_terminate = False
                self.termination_reason = None
                self.feedback = "评估完成"

        # 构建评估提示词并调用LLM
        prompt = self._build_evaluation_prompt(question, answer, conversation_history)
        
        try:
            llm_response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            evaluation_text = llm_response.choices[0].message.content
            assessment_data = self._parse_evaluation_response(evaluation_text, question, answer)
            
            # 创建结果对象
            result = AssessmentResult()
            result.anthropomorphism_score = assessment_data['anthropomorphism_score']
            result.purchase_intent_change = assessment_data['purchase_intent_change']
            result.purchase_intent_reason = assessment_data['purchase_intent_reason']
            result.problem_resolved = assessment_data['problem_resolved']
            result.problem_resolve_reason = assessment_data['problem_resolve_reason']
            result.sales_script_quality = assessment_data['sales_script_quality']
            result.sales_script_reason = assessment_data['sales_script_reason']
            result.user_experience = assessment_data['user_experience']
            result.user_experience_reason = assessment_data['user_experience_reason']
            result.feedback = assessment_data['feedback']
            
        except Exception as e:
            # LLM调用失败时使用默认值
            result = AssessmentResult()
            result.feedback = f"LLM评估失败，使用默认评分: {str(e)}"
        
        # 终止条件检测
        # 1. 转人工关键词
        human_keywords = ["转人工", "人工客服", "投诉", "人工"]
        if any(kw in answer for kw in human_keywords):
            result.should_terminate = True
            result.termination_reason = "human_escalation"
        
        # 2. 用户体验极差
        if result.user_experience == "poor":
            result.should_terminate = True
            result.termination_reason = "poor_user_experience"
        
        # 3. 购买意愿持续下降（这里简化处理，实际需要追踪多轮）
        if result.purchase_intent_change == "declined":
            result.should_terminate = True
            result.termination_reason = "purchase_intent_declined"
        
        # 4. 无法解决问题且话术差
        if not result.problem_resolved and result.sales_script_quality == "poor":
            result.should_terminate = True
            result.termination_reason = "unresolved_and_poor_service"

        return result

    async def generate_session_summary(self, session_data: dict) -> dict:
        """生成会话摘要 - 包含详细评估 (供router使用)"""
        conversation = session_data.get("conversation", [])
        session_id = session_data.get("session_id", "")
        
        # 提取对话轮次
        turns = []
        for i, msg in enumerate(conversation):
            if msg.get("role") == "user_agent":
                # 找到对应的客服回复
                answer = ""
                if i + 1 < len(conversation) and conversation[i + 1].get("role") == "target_bot":
                    answer = conversation[i + 1].get("content", "")
                turns.append({
                    "turn_number": len(turns) + 1,
                    "question": msg.get("content", ""),
                    "answer": answer
                })
        
        # 对每一轮进行详细评估
        turn_assessments = []
        for turn in turns:
            assessment = await self.assess_turn(
                turn_number=turn["turn_number"],
                question=turn["question"],
                answer=turn["answer"],
                conversation_history=[]
            )
            turn_assessments.append({
                "turn_number": assessment.turn_number,
                "anthropomorphism_score": assessment.anthropomorphism_score,
                "purchase_intent_change": assessment.purchase_intent_change,
                "purchase_intent_reason": assessment.purchase_intent_reason,
                "problem_resolved": assessment.problem_resolved,
                "problem_resolve_reason": assessment.problem_resolve_reason,
                "sales_script_quality": assessment.sales_script_quality,
                "sales_script_reason": assessment.sales_script_reason,
                "user_experience": assessment.user_experience,
                "user_experience_reason": assessment.user_experience_reason,
                "should_terminate": assessment.should_terminate,
                "termination_reason": assessment.termination_reason,
                "feedback": assessment.feedback,
            })
        
        # 计算平均拟人程度分数
        avg_anthropomorphism = sum(a["anthropomorphism_score"] for a in turn_assessments) / len(turn_assessments) if turn_assessments else 0
        
        # 统计购买意愿变化
        purchase_improved = sum(1 for a in turn_assessments if a["purchase_intent_change"] == "improved")
        purchase_declined = sum(1 for a in turn_assessments if a["purchase_intent_change"] == "declined")
        
        # 统计问题解决率
        problems_resolved = sum(1 for a in turn_assessments if a["problem_resolved"])
        
        # 统计话术质量分布
        excellent_scripts = sum(1 for a in turn_assessments if a["sales_script_quality"] == "excellent")
        poor_scripts = sum(1 for a in turn_assessments if a["sales_script_quality"] == "poor")
        
        # 统计用户体验分布
        excellent_experience = sum(1 for a in turn_assessments if a["user_experience"] == "excellent")
        poor_experience = sum(1 for a in turn_assessments if a["user_experience"] == "poor")

        return {
            "session_id": session_id,
            "persona": session_data.get("persona", "unknown"),
            "finish_reason": session_data.get("finish_reason", "unknown"),
            "total_turns": len(turns),
            # 汇总指标
            "summary": {
                "avg_anthropomorphism_score": round(avg_anthropomorphism, 2),
                "purchase_intent": {
                    "improved": purchase_improved,
                    "unchanged": len(turn_assessments) - purchase_improved - purchase_declined,
                    "declined": purchase_declined
                },
                "problem_resolution_rate": f"{problems_resolved}/{len(turn_assessments)}",
                "sales_script_quality": {
                    "excellent": excellent_scripts,
                    "good": len(turn_assessments) - excellent_scripts - poor_scripts,
                    "poor": poor_scripts
                },
                "user_experience": {
                    "excellent": excellent_experience,
                    "good": len(turn_assessments) - excellent_experience - poor_experience,
                    "poor": poor_experience
                }
            },
            # 每轮详细评估
            "turn_assessments": turn_assessments
        }


# 全局实例
referee_agent = RefereeAgent()
