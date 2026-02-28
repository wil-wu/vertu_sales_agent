"""Mock用户智能体实现模块 - 用于对话仿真测试"""

import asyncio
import json
import logging
import random
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
    preset_prompt: Optional[str] = Field(default=None)

class UserAgent:
    """仿真测试用户代理智能体"""

    def __init__(
        self,
        chat_model=None,
        system_prompt: str = "",
        target_bot_url: str = "http://localhost:8000/api/v1/react/chat"
    ):
        self.chat_model = chat_model or chat_model
        self.system_prompt = system_prompt
        self.target_bot_url = target_bot_url
        self.human_escalation_keywords = ["转人工", "人工客服", "人工帮助", "人工", "客服", "投诉"]
        self.invalid_response_keywords = ["无法回答", "不知道", "不清楚", "我不懂", "无法找到", "没有找到"]

    async def load_question_pool(self, csv_file: str = "jd_tm_qa_filtered.csv") -> List[Dict[str, Any]]:
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

    async def start_simulation(self, persona: str, scenario: str, max_turns: int = 20) -> Dict[str, Any]:
        """启动仿真测试"""
        logger.info(f"=== [AGENT] 启动仿真测试 - 人格: {persona}, 场景: {scenario} ===")

        # 初始化状态
        state = ConversationState(
            session_id=str(uuid.uuid4()),
            max_turns=max_turns,
            persona=persona,
            preset_prompt=f"模拟{self._get_persona_description(persona)}用户{scenario}"
        )

        # 加载问题池
        state.question_pool = await self.load_question_pool()

        # 开始多轮对话
        await self._run_conversation_loop(state)

        # 保存会话数据
        return await self._save_session_data(state)

    def _get_persona_description(self, persona: str) -> str:
        """获取人格描述"""
        persona_desc = {
            "professional": "专业人士",
            "novice": "技术小白",
            "confrontational": "杠精",
            "anxious": "焦虑客户",
            "bilingual": "双语用户"
        }
        return persona_desc.get(persona, "中性")

    async def _run_conversation_loop(self, state: ConversationState):
        """运行多轮对话循环"""
        logger.info(f"=== [AGENT] 开始多轮对话 - 会话ID: {state.session_id} ===")

        # 选择初始问题
        initial_question = self._select_initial_question(state.persona, state.question_pool)
        current_question = initial_question

        # 创建客户端
        async with httpx.AsyncClient() as client:
            while state.turn_count < state.max_turns:
                state.turn_count += 1
                logger.info(f"=== [AGENT] 第 {state.turn_count} 轮对话 ===")

                try:
                    # 调用Target Bot API
                    response = await self._call_target_bot(client, current_question, state.session_id)
                    bot_answer = response.message

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
                    break

        if not state.finish_reason:
            state.finish_reason = "max_turns"
            logger.info(f"=== [AGENT] 达到最大轮数限制: {state.max_turns} ===")

    async def _call_target_bot(self, client: httpx.AsyncClient, question: str, thread_id: str) -> Any:
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
                        "thread_id": thread_id
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
        """检查终止条件"""
        # 条件1: 转人工信息
        if any(keyword in bot_answer for keyword in self.human_escalation_keywords):
            return "human_escalation"

        # 条件2: 无效回答
        if any(keyword in bot_answer for keyword in self.invalid_response_keywords):
            state.invalid_response_count += 1
            if state.invalid_response_count >= 3:
                return "invalid_responses"
        elif state.invalid_response_count > 0:
            state.invalid_response_count = 0  # 重置计数

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

                基于上述对话，请生成下一个问题，考虑以下要素:
                1. 如果问题已解决，表示感谢
                2. 如果回答不满意，继续追问
                3. 根据你的{state.persona}人格特点调整提问方式
                4. 避免与已问问题重复
            """)
        ]

        try:
            response = await self.chat_model.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(f"=== [AGENT] 生成问题失败: {e} ===")
            return self._get_fallback_question(state)

    def _build_agent_prompt(self, state: ConversationState) -> str:
        """构建代理提示词"""
        return f"""
            你正在模拟一个{self._get_persona_description(state.persona)}的电商客户。
            你必须根据{state.persona}的客户行为特点来提问:
            - 如果你认为问题已解决，可以说"谢谢"结束会话
            - 如果回答不满意，继续提出有针对性的问题
            - 避免重复之前问过的问题

            {state.preset_prompt}
        """

    def _get_system_prompt(self, persona: str) -> str:
        """获取系统提示词"""
        # 这里可以结合 prompts.py 中的定义
        return f"""
            你是Vertu手机的专业客服评估员。正在模拟{persona}类型的客户进行对话测试。
            你的任务是根据{persona}的客户特征，自然地提出相关问题并评估客服答复。
        """

    def _get_fallback_question(self, state: ConversationState) -> str:
        """获取备用问题"""
        if state.question_pool:
            return random.choice([q['question'] for q in state.question_pool])
        else:
            return "请介绍一下VERTU手机的主要特点"

    def _select_initial_question(self, persona: str, questions: List[Dict[str, Any]]) -> str:
        """根据人格选择初始问题"""
        if not questions:
            return self._get_fallback_question(ConversationState())

        # 根据人格选择合适的分类
        if persona == "professional":
            tech_questions = [q for q in questions if q.get('category', '') in ["技术支持", "系统更新"]]
            return random.choice(tech_questions).get('question', questions[0]['question']) if tech_questions else questions[0]['question']
        elif persona == "anxious":
            support_questions = [q for q in questions if q.get('category', '') in ["技术支持", "安全隐私"]]
            return random.choice(support_questions).get('question', questions[0]['question']) if support_questions else questions[0]['question']
        else:
            return random.choice(questions)['question']

    async def _save_session_data(self, state: ConversationState) -> Dict[str, Any]:
        """保存会话数据"""
        logger.info(f"=== [AGENT] 保存会话数据 - 会话ID: {state.session_id} ===")

        session_data = {
            "session_id": state.session_id,
            "prompt": state.preset_prompt,
            "finish_reason": state.finish_reason,
            "persona": state.persona,
            "metadata": {
                "start_time": state.conversation_history[0]["timestamp"] if state.conversation_history else datetime.now().isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_turns": state.turn_count
            },
            "conversation": [
                {
                    "role": msg["role"],
                    "content": msg["content"],
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
