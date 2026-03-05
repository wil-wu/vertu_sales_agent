"""Mock用户智能体实现模块 - 用于对话仿真测试"""

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from .shared import chat_model
from .user_config import get_persona_config

logger = logging.getLogger(__name__)

class ConversationState(BaseModel):
    """对话状态"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn_count: int = Field(default=0)
    max_turns: int = Field(default=20)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    persona: str = Field(default="neutral")
    question_pool: List[Dict[str, Any]] = Field(default_factory=list)
    invalid_response_count: int = Field(default=0)
    finish_reason: Optional[str] = Field(default=None)
    finish_reason_description: Optional[str] = Field(default=None)
    preset_prompt: Optional[str] = Field(default=None)
    user_id: str = Field(default="simulation_user")
    platform: Optional[str] = Field(default=None)
    llm_call_stats: Dict[str, Any] = Field(default_factory=lambda: {
        "calls": [],  # 每次调用的详细信息
        "total_calls": 0,
        "total_duration": 0.0,
        "avg_duration": 0.0,
        "min_duration": float('inf'),
        "max_duration": 0.0
    })

class UserAgent:
    """仿真测试用户代理智能体"""

    def __init__(
        self,
        chat_model=None,
        system_prompt: str = "",
        target_bot_url: str = "http://localhost:8000/api/v1/react/chat"
    ):
        self.chat_model = chat_model
        self.system_prompt = system_prompt
        self.target_bot_url = target_bot_url
        self.human_escalation_keywords = ["转人工", "人工客服", "人工帮助", "人工", "客服", "投诉"]
        self.invalid_response_keywords = ["无法回答", "不知道", "不清楚", "我不懂", "无法找到", "没有找到"]

    def _record_llm_call(self, state: ConversationState, call_type: str, duration: float, details: str = ""):
        """记录LLM调用统计"""
        call_record = {
            "type": call_type,
            "duration": round(duration, 3),
            "timestamp": datetime.now().isoformat(),
            "details": details
        }

        state.llm_call_stats["calls"].append(call_record)
        state.llm_call_stats["total_calls"] += 1
        state.llm_call_stats["total_duration"] += duration

        # 更新统计信息
        state.llm_call_stats["min_duration"] = min(state.llm_call_stats["min_duration"], duration)
        state.llm_call_stats["max_duration"] = max(state.llm_call_stats["max_duration"], duration)

        if state.llm_call_stats["total_calls"] > 0:
            state.llm_call_stats["avg_duration"] = round(
                state.llm_call_stats["total_duration"] / state.llm_call_stats["total_calls"], 3
            )

        # 处理无穷大的情况
        if state.llm_call_stats["min_duration"] == float('inf'):
            state.llm_call_stats["min_duration"] = 0.0

    async def load_question_pool(self, csv_file: str = "simulation/jd_tm_qa_filtered.csv") -> List[Dict[str, Any]]:
        """加载问题池"""
        logger.info(f"=== [AGENT] 加载问题池: {csv_file} ===")
        try:
            df = pd.read_csv(csv_file)
            questions = []
            for idx, row in df.iterrows():
                questions.append({
                    "id": idx + 1,
                    "question": row.get('question', ''),
                    "category": self._categorize_question(row.get('question', ''))
                })

            # 保存mock_questions.json
            mock_questions = {
                "source_file": csv_file,
                "total_count": len(questions),
                "questions": questions,
                "generated_at": datetime.now().isoformat(),
                "categories": list(set(q["category"] for q in questions))
            }

            with open("mock_questions.json", "w", encoding="utf-8") as f:
                json.dump(mock_questions, f, ensure_ascii=False, indent=2)

            logger.info(f"=== [AGENT] 问题池已生成: {len(questions)} 个问题 ===")
            return questions
        except Exception as e:
            logger.error(f"=== [AGENT] 加载问题池失败: {e} ===")
            raise

    def _categorize_question(self, question: str) -> str:
        """根据问题内容分类"""
        question = question.lower()
        if "价格" in question or "多少钱" in question:
            return "价格"
        elif "技术" in question or "功能" in question or "怎么用" in question:
            return "技术支持"
        elif "系统" in question or "更新" in question:
            return "系统更新"
        elif "安全" in question or "隐私" in question or "保密" in question:
            return "安全隐私"
        else:
            return "一般"

    async def start_simulation(self, persona: str, scenario: str, max_turns: int = 20, platform: Optional[str] = None) -> Dict[str, Any]:
        """启动仿真测试"""
        logger.info(f"=== [AGENT] 启动仿真测试 - 人格: {persona}, 场景: {scenario} ===")

        # 初始化状态
        state = ConversationState(
            session_id=str(uuid.uuid4()),
            max_turns=max_turns,
            persona=persona,
            platform=platform,
            preset_prompt=f"模拟{self._get_persona_description(persona)}用户{scenario}"
        )

        # 加载问题池
        state.question_pool = await self.load_question_pool()

        # 选择并改写初始问题
        initial_question = await self._select_initial_question(persona, state.question_pool, state)

        # 开始多轮对话
        await self._run_conversation_loop(state, initial_question)

        # 保存会话数据
        return await self._save_session_data(state)

    def _get_persona_description(self, persona: str) -> str:
        """获取人格描述"""
        config = get_persona_config(persona)
        return config.description if config else "中性"

    async def _run_conversation_loop(self, state: ConversationState, initial_question: str):
        """运行多轮对话循环"""
        logger.info(f"=== [AGENT] 开始多轮对话 - 会话ID: {state.session_id} ===")

        current_question = initial_question

        # 创建客户端
        async with httpx.AsyncClient() as client:
            while state.turn_count < state.max_turns:
                state.turn_count += 1
                logger.info(f"=== [AGENT] 第 {state.turn_count} 轮对话 ===")

                try:
                    # 调用Target Bot API
                    platform_info = state.platform if state.platform else "任意平台"
                    response = await self._call_target_bot(client, current_question, state.session_id, state.user_id, platform_info)
                    bot_answer = response["message"]

                    # 记录对话历史
                    state.conversation_history.append({
                        "role": "user_agent",
                        "content": current_question,
                        "timestamp": datetime.now().isoformat()
                    })
                    state.conversation_history.append({
                        "role": "target_bot",
                        "content": bot_answer,
                        "timestamp": datetime.now().isoformat()
                    })

                    # 检查终止条件
                    reason = await self._check_termination_conditions(state, bot_answer)
                    if reason:
                        state.finish_reason = reason
                        logger.info(f"=== [AGENT] 对话结束 - 原因: {reason} ===")
                        break

                    # 根据推理行动策略生成下一轮问题
                    if state.turn_count < state.max_turns:
                        current_question = await self._generate_next_question(
                            state, bot_answer, current_question
                        )

                    await asyncio.sleep(0.5)  # 避免过快请求

                except Exception as e:
                    logger.error(f"=== [AGENT] 第 {state.turn_count} 轮对话失败: {e} ===")
                    state.finish_reason = f"error_{e}"
                    state.finish_reason_description = f"第{state.turn_count}轮对话出现错误: {str(e)}"
                    break

        if not state.finish_reason:
            state.finish_reason = "max_turns"
            state.finish_reason_description = f"对话达到最大轮数限制({state.max_turns}轮)"
            logger.info(f"=== [AGENT] 达到最大轮数限制: {state.max_turns} ===")

    async def _call_target_bot(self, client: httpx.AsyncClient, question: str, thread_id: str, user_id: str = "simulation_user", platform: str = "simulation") -> Any:
        """调用Target Bot API"""
        logger.info(f"=== [AGENT] 向目标机器人提问: {question[:50]}... ===")

        max_retries = 3
        retry_delay = 5.0

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.post(
                    self.target_bot_url,
                    json={
                        "message": question,
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "platform": platform
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (503, 502, 504) and attempt < max_retries:
                    logger.warning(f"=== [AGENT] 目标机器人暂时不可用 ({e.response.status_code})，第 {attempt} 次重试，等待 {retry_delay}s ===")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"=== [AGENT] 调用目标机器人失败: {e} ===")
                    raise
            except Exception as e:
                logger.error(f"=== [AGENT] 调用目标机器人失败: {e} ===")
                raise

    async def _check_termination_conditions(self, state: ConversationState, bot_answer: str) -> Optional[str]:
        """使用LLM分析用户意图，判断是否应该终止对话"""
        # 获取最近几轮对话历史
        recent_messages = state.conversation_history[-8:] if len(state.conversation_history) >= 8 else state.conversation_history

        # 构建对话历史文本
        conversation_text = "\n".join([
            f"{'用户' if msg['role'] == 'user_agent' else '客服'}: {msg['content']}"
            for msg in recent_messages
        ])

        analysis_prompt = f"""
        分析以下对话，判断是否应该终止对话：

        对话历史（最近几轮）:
        {conversation_text}

        客服最新回复: {bot_answer}

        对话轮数: {state.turn_count}
        用户人格: {state.persona}

        请从语义角度分析：
        1. 用户是否表达了明确的结束对话意愿？
        2. 用户是否连续多次表达相似的结束意图？
        3. 用户是否明确表示拒绝或不感兴趣？
        4. 客服回复是否有问题？（完全无法回答、答非所问等）

        终止条件：
        - 用户连续表达结束意愿（2次以上）
        - 用户明确拒绝购买
        - 客服连续提供无效回答（3次以上）
        - 客服建议转接人工

        返回JSON格式：
        {{
            "should_terminate": true/false,
            "reason": "user_satisfied|user_rejection|invalid_response|human_escalation|continue",
            "confidence": 0.0-1.0,
            "analysis": "简要分析说明"
        }}
        """

        messages = [
            SystemMessage(content="你是一个对话分析师，专门分析用户客服对话，判断对话是否应该结束。基于语义理解而不是简单关键词匹配。返回JSON格式。"),
            HumanMessage(content=analysis_prompt)
        ]

        try:
            start_time = time.time()
            response = await self.chat_model.ainvoke(messages)
            duration = time.time() - start_time

            self._record_llm_call(state, "termination_check", duration, f"检查第{state.turn_count}轮终止条件")

            result_text = response.content.strip()

            # 清理可能的markdown代码块标记
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            result_text = result_text.strip()

            result = json.loads(result_text)
            should_terminate = result.get("should_terminate", False)
            reason = result.get("reason", "continue")
            confidence = result.get("confidence", 0.0)
            analysis = result.get("analysis", "")

            if should_terminate and confidence > 0.75:
                reason_descriptions = {
                    "user_satisfied": "用户表达满意并准备结束对话",
                    "user_rejection": "用户明确表示不感兴趣或拒绝",
                    "invalid_response": "客服连续提供无效回答",
                    "human_escalation": "客服建议转接人工客服"
                }
                state.finish_reason_description = reason_descriptions.get(reason, f"对话终止: {reason}")

                if reason == "invalid_response":
                    state.invalid_response_count += 1
                    if state.invalid_response_count >= 3:
                        return "invalid_responses"
                elif reason in ["human_escalation", "user_satisfied", "user_rejection"]:
                    return reason

        except Exception as e:
            pass

        return None

    async def _generate_next_question(self, state: ConversationState, bot_answer: str, last_question: str) -> str:
        """根据推理行动策略生成下一个问题"""
        logger.info(f"=== [AGENT] 生成第 {state.turn_count + 1} 轮问题 (人格: {state.persona}) ===")

        # 构建提示词
        prompt = self._build_agent_prompt(state)

        # 获取系统提示词
        system_prompt = self._get_system_prompt(state.persona)

        # 构建会话历史
        conversation_history = "\n".join([
            f"用户: {msg['content']}" if msg['role'] == 'user_agent' else f"客服: {msg['content']}"
            for msg in state.conversation_history[-6:]  # 保留最后3轮
        ])

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"""
                {prompt}

                会话历史:
                {conversation_history}

                上一轮客服回答: {bot_answer}

                基于上述对话，请决定下一步行动：
                1. 如果你的主要疑问已经得到满意解答，礼貌地结束对话
                2. 如果还需要了解更多信息，提出一个相关的新问题
                3. 保持自然真实的对话节奏，不要过度追问细枝末节
                4. 符合你的{state.persona}人格特征，但不要表演化
            """)
        ]

        try:
            start_time = time.time()
            response = await self.chat_model.ainvoke(messages)
            duration = time.time() - start_time

            self._record_llm_call(state, "generate_question", duration, f"生成第{state.turn_count + 1}轮问题")

            return response.content.strip()
        except Exception as e:
            logger.error(f"=== [AGENT] 生成问题失败: {e} ===")
            return self._get_fallback_question(state)

    def _build_agent_prompt(self, state: ConversationState) -> str:
        """构建代理提示词"""
        config = get_persona_config(state.persona)
        if config:
            return config.agent_prompt_template + f"\n\n{state.preset_prompt}"
        else:
            return f"你正在模拟一个电商客户。\n\n{state.preset_prompt}"

    def _get_system_prompt(self, persona: str) -> str:
        """获取系统提示词"""
        config = get_persona_config(persona)
        if config:
            return config.system_prompt_template + """

            重要提醒：
            - 这是一个真实的线上客服对话场景
            - 保持自然真实的对话风格，不要表演化
            - 根据你的真实需求提出问题，不要过度纠缠细节
            - 如果信息足够，及时结束对话表示感谢"""
        else:
            return "你是Vertu手机的用户，正在进行真实的客服对话。"

    def _get_fallback_question(self, state: ConversationState) -> str:
        """获取备用问题"""
        if state.question_pool:
            return random.choice([q['question'] for q in state.question_pool])
        else:
            return "请介绍一下VERTU手机的主要特点"

    async def _select_initial_question(self, persona: str, questions: List[Dict[str, Any]], state: ConversationState) -> str:
        """根据人格选择并改写初始问题"""
        if not questions:
            return self._get_fallback_question(ConversationState())

        config = get_persona_config(persona)
        if config:
            filtered_questions = [q for q in questions if q.get('category', '') in config.preferred_categories]
            if filtered_questions:
                selected_question = random.choice(filtered_questions)['question']
            else:
                selected_question = random.choice(questions)['question']
        else:
            selected_question = random.choice(questions)['question']

        # 使用大模型改写问题
        try:
            rewritten_question = await self._rewrite_question_with_llm(selected_question, config, state)
            return rewritten_question
        except Exception as e:
            logger.warning(f"问题改写失败，使用原问题: {e}")
            return selected_question

    async def _rewrite_question_with_llm(self, original_question: str, config=None, state: ConversationState = None) -> str:
        """使用LLM改写问题"""
        prompt = f"请将这个问题改写成更自然的口语化表达：{original_question}"

        messages = [
            SystemMessage(content="将技术问题改写成自然的用户咨询语气。"),
            HumanMessage(content=prompt)
        ]

        try:
            
            start_time = time.time()
            response = await self.chat_model.ainvoke(messages)
            duration = time.time() - start_time

            if state:
                self._record_llm_call(state, "question_rewrite", duration, f"改写问题: {original_question[:50]}...")

            return response.content.strip()
        except Exception:
            return original_question

    async def _save_session_data(self, state: ConversationState) -> Dict[str, Any]:
        """保存会话数据"""
        logger.info(f"=== [AGENT] 保存会话数据 - 会话ID: {state.session_id} ===")

        session_data = {
            "session_id": state.session_id,
            "prompt": state.preset_prompt,
            "finish_reason": state.finish_reason,
            "finish_reason_description": state.finish_reason_description,
            "persona": state.persona,
            "llm_call_stats": {
                "total_calls": state.llm_call_stats["total_calls"],
                "total_duration": round(state.llm_call_stats["total_duration"], 3),
                "avg_duration": state.llm_call_stats["avg_duration"],
                "min_duration": round(state.llm_call_stats["min_duration"], 3) if state.llm_call_stats["min_duration"] != float('inf') else 0.0,
                "max_duration": round(state.llm_call_stats["max_duration"], 3),
                "calls": state.llm_call_stats["calls"]
            },
            "metadata": {
                "start_time": state.conversation_history[0]["timestamp"] if state.conversation_history else datetime.now().isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_turns": state.turn_count
            },
            "conversation": [
                {
                    "role": msg["role"],
                    "content": msg["content"].replace('\n', ' ').replace('\r', ' ').strip(),
                    "timestamp": msg["timestamp"]
                }
                for msg in state.conversation_history
            ]
        }

        try:
            # 创建mock_sessions目录
            sessions_dir = Path("mock_sessions")
            sessions_dir.mkdir(exist_ok=True)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{state.session_id}_{timestamp}.json"
            filepath = sessions_dir / filename

            # 保存文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

            logger.info(f"会话数据已保存到: {filepath}")
            return session_data
        except Exception as e:
            logger.error(f"保存会话数据失败: {e}")
            raise
