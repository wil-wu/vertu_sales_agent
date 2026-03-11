import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import csv
import logging

from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import re
import json

from .config import referee_agent_settings
from .schemas import (
    TurnAssessment,
    SessionRecord,
    RefereeRequest,
    RefereeResponse,
    DetailedMetrics,
    UserAnthropomorphismMetrics,
    AgentAnthropomorphismMetrics,
    PurchaseIntentMetrics,
    ProblemSolvingMetrics,
    SalesScriptMetrics,
    UserExperienceMetrics,
    TraditionalScriptMetrics,
    LanguageConsistencyMetrics,
)
from .shared import session_manager, assessment_tracker
from . import prompts


def load_qa_csv(csv_path: str = None) -> Dict[str, str]:
    """加载 QA CSV 文件，建立问题-答案映射"""
    if csv_path is None:
        # 默认在项目根目录查找
        csv_path = Path(__file__).parent.parent.parent.parent / "jd_tm_qa_filtered.csv"
    else:
        csv_path = Path(csv_path)
    
    qa_mapping = {}
    if csv_path.exists():
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    question = row.get('question') or ''
                    answer = row.get('answer') or ''
                    question = question.strip()
                    answer = answer.strip()
                    if question and answer:
                        qa_mapping[question] = answer
            print(f"[RefereeAgent] 已加载 {len(qa_mapping)} 条 QA 数据")
        except Exception as e:
            print(f"[RefereeAgent] 加载 QA CSV 失败: {e}")
    else:
        print(f"[RefereeAgent] QA CSV 文件不存在: {csv_path}")
    
    return qa_mapping


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
        # 加载 QA 数据
        self.qa_mapping = load_qa_csv()
    
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
            
            # 记录 token 使用情况
            if llm_response.usage:
                input_tokens = llm_response.usage.prompt_tokens
                output_tokens = llm_response.usage.completion_tokens
                logging.info(f"[RefereeAgent] Token 使用 - 输入: {input_tokens}, 输出: {output_tokens}, 总计: {input_tokens + output_tokens}")
            
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
        conversation_history: Optional[list[dict]] = None,
        expected_answer: Optional[str] = None,
        is_first_turn: bool = False,
    ) -> str:
        """构建评估提示词 - 销售与用户体验维度
        
        Args:
            user_message: 用户消息
            agent_response: 客服回复
            conversation_history: 对话历史
            expected_answer: 预期答案（用于首轮对话评估）
            is_first_turn: 是否为首轮对话
        """
        history_str = ""
        if conversation_history:
            history_items = ""
            for h in conversation_history[-5:]:  # 只取最近5轮
                history_items += prompts.HISTORY_ITEM_TEMPLATE.format(
                    user_msg=h.get('user', ''),
                    assistant_msg=h.get('assistant', '')
                )
            history_str = prompts.HISTORY_TEMPLATE.format(history_items=history_items)
        
        # 使用详细评估模板
        return prompts.DETAILED_EVALUATION_PROMPT_TEMPLATE.format(
            user_message=user_message,
            agent_response=agent_response,
            history_str=history_str,
            expected_answer=expected_answer if expected_answer else "",
            is_first_turn=str(is_first_turn).lower()
        )
    
    def _system_prompt(self) -> str:
        """系统提示词 - 销售客服质量评估专家"""
        return prompts.SYSTEM_PROMPT
    
    def _parse_evaluation_response(self, response: str, user_message: str = "", agent_response: str = "") -> Dict[str, Any]:
        """解析LLM评估响应 - 包含详细6大维度指标"""
        try:
            # 尝试提取JSON - 使用更精确的正则表达式
            # 先尝试提取完整的JSON对象
            json_match = re.search(r'\{[\s\S]*\}', response.strip())
            if json_match:
                json_str = json_match.group()
                # 尝试修复常见的JSON格式问题
                # 移除行内注释（// 开头到行尾的内容）
                json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)
                data = json.loads(json_str)
            else:
                # 如果无法提取JSON，使用默认值
                data = {}
            
            # 解析详细指标（如果存在）
            detailed_metrics_data = data.get('detailed_metrics', {})
            
            # 构建详细指标对象（5大维度，维度综合评分由子指标自动计算）
            detailed_metrics = DetailedMetrics(
                # 各维度详细指标（0-1分）
                user_anthropomorphism=UserAnthropomorphismMetrics(
                    language_naturalness=self._get_float(detailed_metrics_data, ['user_anthropomorphism', 'language_naturalness'], 0.5),
                    personality_deviation_count=self._get_int(detailed_metrics_data, ['user_anthropomorphism', 'personality_deviation_count'], 0),
                    humor_warmth=self._get_float(detailed_metrics_data, ['user_anthropomorphism', 'humor_warmth'], 0.5),
                    rhythm_pacing=self._get_float(detailed_metrics_data, ['user_anthropomorphism', 'rhythm_pacing'], 0.5),
                ),
                agent_anthropomorphism=AgentAnthropomorphismMetrics(
                    language_naturalness=self._get_float(detailed_metrics_data, ['agent_anthropomorphism', 'language_naturalness'], 0.5),
                    personality_deviation_count=self._get_int(detailed_metrics_data, ['agent_anthropomorphism', 'personality_deviation_count'], 0),
                    humor_warmth=self._get_float(detailed_metrics_data, ['agent_anthropomorphism', 'humor_warmth'], 0.5),
                    rhythm_pacing=self._get_float(detailed_metrics_data, ['agent_anthropomorphism', 'rhythm_pacing'], 0.5),
                ),
                purchase_intent=PurchaseIntentMetrics(
                    needs_discovery_rate=self._get_float(detailed_metrics_data, ['purchase_intent', 'needs_discovery_rate'], 0.5),
                    product_recommendation_accuracy=self._get_float(detailed_metrics_data, ['purchase_intent', 'product_recommendation_accuracy'], 0.5),
                ),
                problem_solving=ProblemSolvingMetrics(
                    first_contact_resolution=self._get_bool(detailed_metrics_data, ['problem_solving', 'first_contact_resolution'], False),
                    intent_recognition_accuracy=self._get_float(detailed_metrics_data, ['problem_solving', 'intent_recognition_accuracy'], 0.5),
                    fallback_rate=self._get_float(detailed_metrics_data, ['problem_solving', 'fallback_rate'], 0.0),
                ),
                sales_script=SalesScriptMetrics(
                    fab_completeness=self._get_float(detailed_metrics_data, ['sales_script', 'fab_completeness'], 0.5),
                    feature_mentioned=self._get_bool(detailed_metrics_data, ['sales_script', 'feature_mentioned'], False),
                    advantage_mentioned=self._get_bool(detailed_metrics_data, ['sales_script', 'advantage_mentioned'], False),
                    objection_handling_success=self._get_optional_bool(detailed_metrics_data, ['sales_script', 'objection_handling_success']),
                    objection_handling_score=self._get_float(detailed_metrics_data, ['sales_script', 'objection_handling_score'], 0.5),
                    cross_sell_triggered=self._get_bool(detailed_metrics_data, ['sales_script', 'cross_sell_triggered'], False),
                    script_compliance=self._get_float(detailed_metrics_data, ['sales_script', 'script_compliance'], 0.8),
                    personalization_rate=self._get_float(detailed_metrics_data, ['sales_script', 'personalization_rate'], 0.5),
                ),
                user_experience=UserExperienceMetrics(
                    csat_score=self._get_float(detailed_metrics_data, ['user_experience', 'csat_score'], 0.5),
                    negative_feedback_triggered=self._get_bool(detailed_metrics_data, ['user_experience', 'negative_feedback_triggered'], False),
                ),
                traditional_script=TraditionalScriptMetrics(
                    technical_term_simplification=self._get_float(detailed_metrics_data, ['traditional_script', 'technical_term_simplification'], 0.5),
                ),
                language_consistency=LanguageConsistencyMetrics(
                    language_match=self._get_bool(detailed_metrics_data, ['language_consistency', 'language_match'], True),
                ),
            )
            
            # 根据子指标自动计算维度综合评分（0-100分）
            self._calculate_dimension_scores(detailed_metrics)
            
            # 解析新维度的评估结果
            result = {
                # 1. 拟人程度评分 (0-1) - 分别评估客服和用户
                "agent_anthropomorphism_score": float(data.get('agent_anthropomorphism_score', 0.5)),
                "user_anthropomorphism_score": float(data.get('user_anthropomorphism_score', 0.5)),
                
                # 2. 购买意愿变化
                "purchase_intent_change": data.get('purchase_intent_change', 'unchanged'),
                
                # 3. 问题解决情况
                "problem_resolved": data.get('problem_resolved', False),
                
                # 4. 销售话术质量
                "sales_script_quality": data.get('sales_script_quality', 'good'),
                
                # 5. 用户体验
                "user_experience": data.get('user_experience', 'good'),
                
                # 详细指标
                "detailed_metrics": detailed_metrics,
                
                # 反馈
                "feedback": data.get('feedback', response),
            }
            
            return result
        except Exception as e:
            # 解析失败时使用默认值
            return {
                "agent_anthropomorphism_score": 0.5,
                "user_anthropomorphism_score": 0.5,
                "purchase_intent_change": 'unchanged',
                "problem_resolved": False,
                "sales_script_quality": 'good',
                "user_experience": 'good',
                "detailed_metrics": None,
                "feedback": f'评估解析失败: {str(e)}',
            }
    
    def _get_float(self, data: dict, keys: list, default: float) -> float:
        """安全获取嵌套float值"""
        try:
            for key in keys:
                data = data.get(key, {})
            if isinstance(data, (int, float)):
                return float(data)
            return default
        except:
            return default
    
    def _get_optional_float(self, data: dict, keys: list) -> Optional[float]:
        """安全获取嵌套optional float值"""
        try:
            for key in keys:
                data = data.get(key, {})
            if data is None:
                return None
            if isinstance(data, (int, float)):
                return float(data)
            return None
        except:
            return None
    
    def _get_int(self, data: dict, keys: list, default: int) -> int:
        """安全获取嵌套int值"""
        try:
            for key in keys:
                data = data.get(key, {})
            if isinstance(data, int):
                return data
            return default
        except:
            return default
    
    def _get_bool(self, data: dict, keys: list, default: bool) -> bool:
        """安全获取嵌套bool值"""
        try:
            for key in keys:
                data = data.get(key, {})
            if isinstance(data, bool):
                return data
            return default
        except:
            return default
    
    def _get_optional_bool(self, data: dict, keys: list) -> Optional[bool]:
        """安全获取嵌套optional bool值"""
        try:
            for key in keys:
                data = data.get(key, {})
            if data is None:
                return None
            if isinstance(data, bool):
                return data
            return None
        except:
            return None
    
    def _get_list(self, data: dict, keys: list, default: list) -> list:
        """安全获取嵌套list值"""
        try:
            for key in keys:
                data = data.get(key, {})
            if isinstance(data, list):
                return data
            return default
        except:
            return default
    
    def _calculate_dimension_scores(self, dm: DetailedMetrics):
        """根据子指标自动计算7大维度综合评分（0-100分）
        
        计算逻辑：
        1. 拟人化体验 = (user语言自然度 + user温度感 + user节奏感 + agent语言自然度 + agent温度感 + agent节奏感) / 6 * 100
           - 人设偏离扣分：user和agent各最多扣10分（每次偏离扣5分，上限10分）
        
        2. 购买意愿 = (需求挖掘率 + 推荐精准度) / 2 * 100
        
        3. 问题解决 = (首次解决 + 意图识别准确率 + 兜底率) / 3 * 100
           - 首次解决: true=1, false=0
           - 兜底率: 1.0=完全解决(好), 0.0=必须转人工(差)
        
        4. 销售话术 = (FAB完整度 + 异议处理得分 + 交叉销售触发 + 话术合规率 + 个性化率) / 5 * 100
           - 交叉销售触发: true=1, false=0
           - 异议处理：如有异议且处理成功得1分，处理失败得0分，无异议得0.5分
        
        5. 用户体验 = CSAT评分 * 100，如有负面反馈则最高60分
        
        6. 传统话术 = 专业名词通俗化解释 * 100
           - 评估客服是否将专业术语转化为通俗易懂的白话描述
        
        7. 语言一致性 = 语言一致性判断 × 100
           - 语言一致性: true=100分(一致), false=0分(不一致)
        """
        # 1. 拟人化体验维度（0-100分）
        user_anthro = dm.user_anthropomorphism
        agent_anthro = dm.agent_anthropomorphism
        
        anthro_score = (
            user_anthro.language_naturalness + 
            user_anthro.humor_warmth + 
            user_anthro.rhythm_pacing +
            agent_anthro.language_naturalness + 
            agent_anthro.humor_warmth + 
            agent_anthro.rhythm_pacing
        ) / 6 * 100
        
        # 人设偏离扣分（每次扣5分，最多扣10分）
        user_deviation_penalty = min(user_anthro.personality_deviation_count * 5, 10)
        agent_deviation_penalty = min(agent_anthro.personality_deviation_count * 5, 10)
        anthro_score = max(0, anthro_score - user_deviation_penalty - agent_deviation_penalty)
        
        dm.anthropomorphism_score = round(anthro_score)
        
        # 2. 购买意愿驱动维度（0-100分）
        purchase = dm.purchase_intent
        
        purchase_score = (
            purchase.needs_discovery_rate + 
            purchase.product_recommendation_accuracy
        ) / 2 * 100
        
        dm.purchase_intent_score = round(purchase_score)
        
        # 3. 问题解决能力维度（0-100分）
        problem = dm.problem_solving
        fcr_score = 1.0 if problem.first_contact_resolution else 0.0
        
        problem_score = (
            fcr_score + 
            problem.intent_recognition_accuracy + 
            problem.fallback_rate  # fallback_rate 越高越好（1.0=完全解决，0.0=必须转人工）
        ) / 3 * 100
        
        dm.problem_solving_score = round(problem_score)
        
        # 4. 销售话术质量维度（0-100分）
        sales = dm.sales_script
        cross_sell_score = 1.0 if sales.cross_sell_triggered else 0.0
        
        # 异议处理评分：成功=1，失败=0，无异议=0.5
        if sales.objection_handling_success is None:
            objection_score = 0.5  # 无异议，给中等分
        elif sales.objection_handling_success:
            objection_score = 1.0  # 处理成功
        else:
            objection_score = 0.0  # 处理失败
        
        sales_score = (
            sales.fab_completeness + 
            objection_score + 
            cross_sell_score + 
            sales.script_compliance + 
            sales.personalization_rate
        ) / 5 * 100
        
        dm.sales_script_score = round(sales_score)
        
        # 5. 用户体验维度（0-100分）
        ux = dm.user_experience
        ux_score = ux.csat_score * 100
        
        # 如有负面反馈，最高60分
        if ux.negative_feedback_triggered:
            ux_score = min(ux_score, 60)
        
        dm.user_experience_score = round(ux_score)
        
        # 6. 传统话术质量维度（0-100分）
        traditional = dm.traditional_script
        traditional_score = traditional.technical_term_simplification * 100
        
        dm.traditional_script_score = round(traditional_score)
        
        # 7. 语言一致性维度（0-100分）
        language = dm.language_consistency
        
        # 语言一致性：true=100分，false=0分
        language_score = 100.0 if language.language_match else 0.0
        
        dm.language_consistency_score = round(language_score)
    
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
        """评估单轮对话 - 包含6大维度37项详细指标 (供router使用)"""

        class AssessmentResult:
            def __init__(self):
                self.turn_number = turn_number
                
                # 1. 拟人程度 - 分别评估客服和用户
                self.agent_anthropomorphism_score = 0.75
                self.user_anthropomorphism_score = 0.75
                
                # 2. 购买意愿变化
                self.purchase_intent_change = "unchanged"
                
                # 3. 问题解决
                self.problem_resolved = True
                
                # 4. 销售话术质量
                self.sales_script_quality = "good"
                
                # 5. 用户体验
                self.user_experience = "good"
                
                # 6. 详细指标（新增）
                self.detailed_metrics: Optional[DetailedMetrics] = None
                
                # 终止条件
                self.should_terminate = False
                self.termination_reason = None
                self.feedback = "评估完成"

        # 为首轮对话查找预期答案
        expected_answer = None
        is_first_turn = (turn_number == 1)
        if is_first_turn and hasattr(self, 'qa_mapping'):
            expected_answer = self.qa_mapping.get(question.strip())
            if expected_answer:
                print(f"[RefereeAgent] 首轮对话找到预期答案，问题: {question[:50]}...")
        
        # 构建评估提示词并调用LLM
        prompt = self._build_evaluation_prompt(question, answer, conversation_history, expected_answer, is_first_turn)
        
        try:
            llm_response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000  # 增加token以容纳详细指标
            )
            
            evaluation_text = llm_response.choices[0].message.content
            
            # 记录 token 使用情况
            if llm_response.usage:
                input_tokens = llm_response.usage.prompt_tokens
                output_tokens = llm_response.usage.completion_tokens
                logging.info(f"[RefereeAgent] Token 使用 - 输入: {input_tokens}, 输出: {output_tokens}, 总计: {input_tokens + output_tokens}")
            
            assessment_data = self._parse_evaluation_response(evaluation_text, question, answer)
            
            # 创建结果对象
            result = AssessmentResult()
            result.agent_anthropomorphism_score = assessment_data['agent_anthropomorphism_score']
            result.user_anthropomorphism_score = assessment_data['user_anthropomorphism_score']
            result.purchase_intent_change = assessment_data['purchase_intent_change']
            result.problem_resolved = assessment_data['problem_resolved']
            result.sales_script_quality = assessment_data['sales_script_quality']
            result.user_experience = assessment_data['user_experience']
            result.detailed_metrics = assessment_data.get('detailed_metrics')
            result.feedback = assessment_data['feedback']
            
        except Exception as e:
            # LLM调用失败时使用默认值
            result = AssessmentResult()
            result.feedback = f"LLM评估失败，使用默认评分: {str(e)}"
        
        # 终止条件检测（基于详细指标增强）
        await self._enhanced_termination_check(result, question, answer)

        return result
    
    async def _enhanced_termination_check(self, result: "AssessmentResult", question: str, answer: str):
        """基于详细指标的增强终止条件检测"""
        
        # 1. 转人工关键词
        human_keywords = ["转人工", "人工客服", "投诉", "人工"]
        if any(kw in answer for kw in human_keywords):
            result.should_terminate = True
            result.termination_reason = "human_escalation"
            return
        
        # 2. 基于详细指标的智能终止检测
        if result.detailed_metrics:
            dm = result.detailed_metrics
            
            # 2.1 用户体验极差（CSAT < 0.3 或 负面反馈触发）
            if dm.user_experience.csat_score < 0.3 or dm.user_experience.negative_feedback_triggered:
                result.should_terminate = True
                result.termination_reason = "poor_user_experience"
                return
            
            # 2.2 购买意愿持续下降且问题解决率低
            if (result.purchase_intent_change == "declined" and 
                not dm.problem_solving.first_contact_resolution):
                result.should_terminate = True
                result.termination_reason = "purchase_intent_declined_and_unresolved"
                return
            
            # 2.3 无法解决问题且话术差且不合规
            if (not result.problem_resolved and 
                result.sales_script_quality == "poor" and 
                dm.sales_script.script_compliance < 0.5):
                result.should_terminate = True
                result.termination_reason = "unresolved_poor_service_non_compliant"
                return
            
            # 2.4 兜底率过高（需要转人工）
            if dm.problem_solving.fallback_rate > 0.7:
                result.should_terminate = True
                result.termination_reason = "high_fallback_rate"
                return
        
        # 3. 基础终止条件（兼容旧版）
        if result.user_experience == "poor":
            result.should_terminate = True
            result.termination_reason = "poor_user_experience"
        elif result.purchase_intent_change == "declined":
            result.should_terminate = True
            result.termination_reason = "purchase_intent_declined"
        elif not result.problem_resolved and result.sales_script_quality == "poor":
            result.should_terminate = True
            result.termination_reason = "unresolved_and_poor_service"

    async def generate_session_summary(self, session_data: dict) -> dict:
        """生成会话摘要 - 包含6大维度37项详细指标汇总 (供router使用)"""
        conversation = session_data.get("conversation", [])
        session_id = session_data.get("session_id", "")
        
        # 从 calls 中提取 question_rewrite 类型的原问题（用于查找预期答案）
        original_questions = {}
        llm_call_stats = session_data.get("llm_call_stats", {})
        calls = llm_call_stats.get("calls", [])
        for call in calls:
            if call.get("type") == "question_rewrite":
                details = call.get("details", "")
                # 解析 "改写问题: 原问题..." 格式
                if "改写问题:" in details:
                    original_question = details.replace("改写问题:", "").strip()
                    # 使用轮次作为键（假设 question_rewrite 按顺序对应每轮）
                    turn_num = len(original_questions) + 1
                    original_questions[turn_num] = original_question
        
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
        detailed_metrics_list = []
        
        # 记录首轮对话的预期回答和实际回答（用于 first_contact_resolution 评估）
        first_turn_qa = {}
        
        for turn in turns:
            # 为首轮对话查找预期答案（使用 calls 中的原问题）
            expected_answer = None
            if turn["turn_number"] == 1:
                # 优先使用 calls 中的原问题，如果没有则使用 conversation 中的问题
                original_question = original_questions.get(1, turn["question"])
                if hasattr(self, 'qa_mapping'):
                    # 首先尝试精确匹配
                    expected_answer = self.qa_mapping.get(original_question.strip())
                    
                    # 如果精确匹配失败，尝试前缀匹配（处理截断的情况）
                    if not expected_answer:
                        for qa_question, qa_answer in self.qa_mapping.items():
                            # 检查 CSV 中的问题是否以提取的问题开头（去除可能的...）
                            clean_original = original_question.strip().rstrip('.').rstrip('...')
                            if qa_question.startswith(clean_original):
                                expected_answer = qa_answer
                                print(f"[RefereeAgent] 使用前缀匹配找到预期答案")
                                break
                            # 或者反过来，检查提取的问题是否以 CSV 中的问题开头
                            if clean_original.startswith(qa_question[:50]):
                                expected_answer = qa_answer
                                print(f"[RefereeAgent] 使用反向前缀匹配找到预期答案")
                                break
                
                # 无论是否找到预期答案，都记录问答对比
                first_turn_qa = {
                    "question": original_question,
                    "conversation_question": turn["question"],
                    "expected_answer": expected_answer if expected_answer else "",
                    "actual_answer": turn["answer"]
                }
                
                if expected_answer:
                    print(f"[RefereeAgent] 首轮对话找到预期答案，原问题: {original_question[:50]}...")
                else:
                    print(f"[RefereeAgent] 首轮对话未找到预期答案，原问题: {original_question[:50]}...")
            
            assessment = await self.assess_turn(
                turn_number=turn["turn_number"],
                question=turn["question"],
                answer=turn["answer"],
                conversation_history=[]
            )
            
            assessment_dict = {
                "turn_number": assessment.turn_number,
                "agent_anthropomorphism_score": assessment.agent_anthropomorphism_score,
                "user_anthropomorphism_score": assessment.user_anthropomorphism_score,
                "feedback": assessment.feedback,
            }
            
            # 添加详细指标（如果存在）
            if assessment.detailed_metrics:
                assessment_dict["detailed_metrics"] = assessment.detailed_metrics.model_dump()
                detailed_metrics_list.append(assessment.detailed_metrics)
                
                # 为首轮对话添加 first_contact_resolution
                if turn["turn_number"] == 1:
                    assessment_dict["first_contact_resolution"] = assessment.detailed_metrics.problem_solving.first_contact_resolution
            
            # 为首轮对话添加问答对比（无论 detailed_metrics 是否存在）
            if turn["turn_number"] == 1 and first_turn_qa:
                assessment_dict["qa_comparison"] = first_turn_qa
            
            turn_assessments.append(assessment_dict)
        
        # ========== 详细指标汇总 ==========
        detailed_summary = self._calculate_detailed_summary(detailed_metrics_list, turn_assessments) if detailed_metrics_list else {}

        return {
            "session_id": session_id,
            "persona": session_data.get("persona", "unknown"),
            "finish_reason": session_data.get("finish_reason", "unknown"),
            "total_turns": len(turns),
            # 详细指标汇总
            "detailed_summary": detailed_summary,
            # 每轮详细评估
            "turn_assessments": turn_assessments
        }
    
    def _calculate_detailed_summary(self, metrics_list: List[DetailedMetrics], turn_assessments: List[Dict] = None) -> dict:
        """计算详细指标的会话级汇总（5大维度，含维度综合评分）"""
        if not metrics_list:
            return {}
        
        n = len(metrics_list)
        
        def avg(values):
            return round(sum(values) / len(values), 2) if values else 0
        
        # 维度综合评分汇总（0-100分）
        dimension_scores = {
            "anthropomorphism_score": avg([m.anthropomorphism_score for m in metrics_list]),
            "purchase_intent_score": avg([m.purchase_intent_score for m in metrics_list]),
            "problem_solving_score": avg([m.problem_solving_score for m in metrics_list]),
            "sales_script_score": avg([m.sales_script_score for m in metrics_list]),
            "user_experience_score": avg([m.user_experience_score for m in metrics_list]),
            "traditional_script_score": avg([m.traditional_script_score for m in metrics_list]),
            "language_consistency_score": avg([m.language_consistency_score for m in metrics_list]),
        }
        
        # 一、拟人化体验指标汇总 - 分别汇总user和agent
        user_anthro = {
            "language_naturalness": avg([m.user_anthropomorphism.language_naturalness for m in metrics_list]),
            "total_personality_deviations": sum([m.user_anthropomorphism.personality_deviation_count for m in metrics_list]),
            "humor_warmth": avg([m.user_anthropomorphism.humor_warmth for m in metrics_list]),
            "rhythm_pacing": avg([m.user_anthropomorphism.rhythm_pacing for m in metrics_list]),
        }
        
        agent_anthro = {
            "language_naturalness": avg([m.agent_anthropomorphism.language_naturalness for m in metrics_list]),
            "total_personality_deviations": sum([m.agent_anthropomorphism.personality_deviation_count for m in metrics_list]),
            "humor_warmth": avg([m.agent_anthropomorphism.humor_warmth for m in metrics_list]),
            "rhythm_pacing": avg([m.agent_anthropomorphism.rhythm_pacing for m in metrics_list]),
        }
        
        # 二、购买意愿驱动指标汇总
        purchase = {
            "avg_needs_discovery_rate": avg([m.purchase_intent.needs_discovery_rate for m in metrics_list]),
            "avg_recommendation_accuracy": avg([m.purchase_intent.product_recommendation_accuracy for m in metrics_list]),
        }
        
        # 三、问题解决能力指标汇总
        # 统计整个 session 中 fallback_rate < 0.3（表示完全无法回答，必须转人工）的轮次数量
        fallback_count = sum([1 for m in metrics_list if m.problem_solving.fallback_rate < 0.3])
        
        # 根据兜底次数计算得分：>2 次=0.0，=2 次=0.6，=1 次=0.8，=0 次=1.0
        if fallback_count > 2:
            fallback_score = 0.0
        elif fallback_count == 2:
            fallback_score = 0.6
        elif fallback_count == 1:
            fallback_score = 0.8
        else:  # fallback_count == 0
            fallback_score = 1.0
        
        # 计算 first_contact_resolution_rate - 只计算首轮对话
        # 从 turn_assessments 中找到首轮对话的 first_contact_resolution
        first_contact_resolution_rate = 0.0
        if turn_assessments:
            first_turn = next((t for t in turn_assessments if t.get("turn_number") == 1), None)
            if first_turn:
                first_contact_resolution_rate = 1.0 if first_turn.get("first_contact_resolution") else 0.0
        
        problem = {
            "first_contact_resolution_rate": first_contact_resolution_rate,
            "avg_intent_recognition_accuracy": avg([m.problem_solving.intent_recognition_accuracy for m in metrics_list]),
            "fallback_count": fallback_count,
            "fallback_score": fallback_score,
        }
        
        # 四、销售话术质量指标汇总
        sales = {
            "avg_fab_completeness": avg([m.sales_script.fab_completeness for m in metrics_list]),
            "feature_mention_rate": round(sum([1 for m in metrics_list if m.sales_script.feature_mentioned]) / n, 2),
            "advantage_mention_rate": round(sum([1 for m in metrics_list if m.sales_script.advantage_mentioned]) / n, 2),
            "cross_sell_trigger_count": sum([1 for m in metrics_list if m.sales_script.cross_sell_triggered]),
            "avg_script_compliance": avg([m.sales_script.script_compliance for m in metrics_list]),
            "avg_personalization_rate": avg([m.sales_script.personalization_rate for m in metrics_list]),
        }
        
        # 五、用户体验指标汇总
        ux = {
            "avg_csat_score": avg([m.user_experience.csat_score for m in metrics_list]),
            "negative_feedback_count": sum([1 for m in metrics_list if m.user_experience.negative_feedback_triggered]),
        }
        
        return {
            "dimension_scores": dimension_scores,  # 维度综合评分（0-100）
            "user_anthropomorphism": user_anthro,
            "agent_anthropomorphism": agent_anthro,
            "purchase_intent": purchase,
            "problem_solving": problem,
            "sales_script": sales,
            "user_experience": ux,
        }


# 全局实例
referee_agent = RefereeAgent()
