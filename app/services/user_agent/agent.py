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
from .user_config import get_persona_config, PLATFORM_API_CONFIG

logger = logging.getLogger(__name__)

class ConversationState(BaseModel):
    """对话状态"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn_count: int = Field(default=0)
    max_turns: int = Field(default=20)
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    persona: str = Field(default="neutral")
    scenario: Optional[str] = Field(default=None)
    question_pool: List[Dict[str, Any]] = Field(default_factory=list)
    invalid_response_count: int = Field(default=0)
    finish_reason: Optional[str] = Field(default=None)
    finish_reason_description: Optional[str] = Field(default=None)
    preset_prompt: Optional[str] = Field(default=None)
    user_id: str = Field(default="simulation_user")
    platform: Optional[str] = Field(default=None)
    channel_param: Optional[str] = Field(default=None)
    language: str = Field(default="zh")
    region: str = Field(default="国内")
    llm_call_stats: Dict[str, Any] = Field(default_factory=lambda: {
        "calls": [],  # 每次调用的详细信息
        "total_calls": 0,
        "total_duration": 0.0,
        "avg_duration": 0.0,
        "min_duration": float('inf'),
        "max_duration": 0.0
    })
    initial_question: str = Field(default="")
    original_question: str = Field(default="")  # 从问题池选择的原始问题
    original_query_results: Dict[str, Any] = Field(default_factory=dict)  # 使用原始问题查询的结果
    knowledge_pool: Dict[str, Any] = Field(default_factory=dict)  # 知识池: {"faq": [...], "price": [...], "graph": [...]}

class UserAgent:
    """仿真测试用户代理智能体"""

    def __init__(
        self,
        chat_model=None,
        system_prompt: str = "",
        target_bot_url: str = "http://localhost:8000/api/v1/react/chat",
        faq_url: str = "http://192.168.151.84:8888/query",
        price_url: str = "http://192.168.151.84:8030/api/v1/semantic/product/search"
    ):
        self.chat_model = chat_model
        self.system_prompt = system_prompt
        self.target_bot_url = target_bot_url
        self.faq_url = faq_url
        self.price_url = price_url
        self.human_escalation_keywords = ["转人工", "人工客服", "人工帮助", "人工", "客服", "投诉"]
        self.invalid_response_keywords = ["无法回答", "不知道", "不清楚", "我不懂", "无法找到", "没有找到"]

    async def _fetch_faq(self, query: str, collection_name: str = "domestic_e_commerce", top_k: int = 5) -> List[dict]:
        """获取 FAQ 数据"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.faq_url,
                json={"query": query, "collection_names": [collection_name], "top_k": top_k},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()

        items = []
        for category in data.get("categories", []):
            for item in category.get("items", []):
                items.append({
                    "question": item.get("question", ""),
                    "answer": item.get("answer", "")
                })
        return items[:top_k]

    async def _fetch_price(self, query: str, index_name: str = "jd_product", hits_per_page: int = 5) -> List[dict]:
        """获取价格数据"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.price_url,
                json={"query": query, "index_name": index_name, "hits_per_page": hits_per_page, "page": 1},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()

        items = []
        for hit in data.get("hits", [])[:hits_per_page]:
            items.append({
                "name": hit.get("name", ""),
                "price": hit.get("price", 0)
            })
        return items

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
                    "category": self._categorize_question(row.get('question', '')),
                    "platform": row.get('generate_source', '') if pd.notna(row.get('generate_source')) else ''
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

    async def start_simulation(
        self,
        persona: str,
        scenario: str,
        max_turns: int = 20,
        platform: Optional[str] = None,
        knowledge_pool: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """启动仿真测试

        Args:
            persona: 用户人格类型
            scenario: 测试场景描述
            max_turns: 最大对话轮数
            platform: 用户来源平台
            knowledge_pool: 知识池数据 {"faq": [...], "price": [...], "graph": [...]}
        """
        logger.info(f"=== [AGENT] 启动仿真测试 - 人格: {persona}, 场景: {scenario} ===")

        # 初始化状态
        state = ConversationState(
            session_id=str(uuid.uuid4()),
            max_turns=max_turns,
            persona=persona,
            scenario=scenario,
            platform=platform,
            preset_prompt=f"模拟{self._get_persona_description(persona)}用户{scenario}",
            knowledge_pool=knowledge_pool or {}
        )

        # 如果传入了知识池，从知识池生成初始问题；否则从CSV问题池加载
        initial_expected_answer = None
        initial_knowledge_used = None
        if knowledge_pool and (knowledge_pool.get("faq") or knowledge_pool.get("price") or knowledge_pool.get("graph")):
            logger.info(f"=== [AGENT] 从知识池生成初始问题 ===")
            qa_result = await self._generate_initial_question_from_knowledge_pool(state)
            initial_question = qa_result["question"]
            initial_expected_answer = qa_result["expected_answer"]
            initial_knowledge_used = qa_result["knowledge_used"]
            state.initial_question = initial_question
            # 使用知识池作为查询结果
            state.original_query_results = {
                "faq": knowledge_pool.get("faq", []),
                "price": knowledge_pool.get("price", []),
                "graph": knowledge_pool.get("graph", []),
                "query_time": datetime.now().isoformat(),
                "source": "knowledge_pool",
                "expected_answer": initial_expected_answer,
                "knowledge_used": initial_knowledge_used
            }
            faq_count = len(knowledge_pool.get("faq", []))
            price_count = len(knowledge_pool.get("price", []))
            graph_count = len(knowledge_pool.get("graph", []))
            logger.info(f"=== [AGENT] 使用知识池 - FAQ: {faq_count}条, 价格: {price_count}条, 图谱: {graph_count}条 ===")
        else:
            # 加载CSV问题池
            state.question_pool = await self.load_question_pool()
            # 选择并改写初始问题（根据场景生成）
            initial_question = await self._select_initial_question(persona, scenario, state.question_pool, state)
            state.initial_question = initial_question

            # 根据平台确定查询参数
            platform_config = PLATFORM_API_CONFIG.get(platform, PLATFORM_API_CONFIG["domestic_jd"])
            faq_collection = platform_config["faq_collection"]
            price_index = platform_config["price_index"]

            # 使用原始问题查询 FAQ 和价格 API
            query_for_search = state.original_question if state.original_question else initial_question
            logger.info(f"=== [AGENT] 使用原始问题查询 FAQ 和价格数据 - 问题: {query_for_search[:50]}... ===")
            faq_results = await self._fetch_faq(query_for_search, faq_collection, top_k=5)
            price_results = await self._fetch_price(query_for_search, price_index, hits_per_page=5)

            state.original_query_results = {
                "faq": faq_results,
                "price": price_results,
                "query_time": datetime.now().isoformat(),
                "source": "api_query"
            }
            logger.info(f"=== [AGENT] FAQ 查询到 {len(faq_results)} 条，价格查询到 {len(price_results)} 条 ===")

        # 开始多轮对话
        await self._run_conversation_loop(
            state,
            initial_question,
            initial_expected_answer=initial_expected_answer,
            initial_knowledge_used=initial_knowledge_used
        )

        # 保存会话数据
        return await self._save_session_data(state)

    def _get_persona_description(self, persona: str) -> str:
        """获取人格描述"""
        config = get_persona_config(persona)
        return config.description if config else "中性"

    async def _run_conversation_loop(
        self,
        state: ConversationState,
        initial_question: str,
        initial_expected_answer: Optional[str] = None,
        initial_knowledge_used: Optional[List[str]] = None
    ):
        """运行多轮对话循环

        Args:
            state: 对话状态
            initial_question: 初始问题
            initial_expected_answer: 初始问题的预期答案
            initial_knowledge_used: 初始问题使用的知识
        """
        logger.info(f"=== [AGENT] 开始多轮对话 - 会话ID: {state.session_id} ===")

        current_question = initial_question
        current_expected_answer = initial_expected_answer
        current_knowledge_used = initial_knowledge_used

        # 创建客户端
        async with httpx.AsyncClient() as client:
            while state.turn_count < state.max_turns:
                state.turn_count += 1
                logger.info(f"=== [AGENT] 第 {state.turn_count} 轮对话 ===")

                try:
                    # 调用Target Bot API
                    platform_info = state.platform if state.platform else "任意平台"
                    response = await self._call_target_bot(client, current_question, state.session_id, state.user_id, platform_info, state.region)
                    bot_answer = response["message"]

                    # 记录对话历史（包含预期答案）
                    user_message = {
                        "role": "user_agent",
                        "content": current_question,
                        "timestamp": datetime.now().isoformat()
                    }
                    if current_expected_answer:
                        user_message["expected_answer"] = current_expected_answer
                    if current_knowledge_used:
                        user_message["knowledge_used"] = current_knowledge_used

                    state.conversation_history.append(user_message)
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
                        qa_result = await self._generate_next_question_with_answer(
                            state, bot_answer, current_question
                        )
                        current_question = qa_result["question"]
                        current_expected_answer = qa_result.get("expected_answer")
                        current_knowledge_used = qa_result.get("knowledge_used")

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

    async def _call_target_bot(self, client: httpx.AsyncClient, question: str, thread_id: str, user_id: str = "simulation_user", platform: str = "simulation", region: str = "国内") -> Any:
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
                        "platform": platform,
                        "region": region
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

    def _format_knowledge_pool(self, knowledge_pool: Dict[str, Any]) -> str:
        """格式化知识池为提示词文本"""
        if not knowledge_pool:
            return ""

        sections = []

        # FAQ 知识
        faq_items = knowledge_pool.get("faq", [])
        if faq_items:
            faq_text = "\n".join([
                f"- Q: {item.get('question', '')}\n  A: {item.get('answer', '')[:100]}..."
                for item in faq_items[:5]  # 最多显示5条
            ])
            sections.append(f"### FAQ 知识\n{faq_text}")

        # 价格信息
        price_items = knowledge_pool.get("price", [])
        if price_items:
            price_text = "\n".join([
                f"- {item.get('name', '')}: {item.get('price', 'N/A')}"
                for item in price_items[:5]
            ])
            sections.append(f"### 价格信息\n{price_text}")

        # 图谱知识
        graph_items = knowledge_pool.get("graph", [])
        if graph_items:
            graph_text = "\n".join([
                f"- {item.get('subject', '')} -> {item.get('predicate', '')} -> {item.get('object', '')}"
                for item in graph_items[:5]
            ])
            sections.append(f"### 图谱知识\n{graph_text}")

        if not sections:
            return ""

        return "\n\n".join([
            "## 参考知识池",
            "你在生成问题时可以参考以下知识（但不要直接复制）：",
            "",
            *sections,
            "",
            "### 使用说明",
            "- 以上知识仅供参考，帮助你生成更真实、准确的用户问题",
            "- 基于这些知识提出相关问题，但用自己的话表达",
            "- 保持自然真实的对话风格"
        ])

    async def _generate_initial_question_from_knowledge_pool(self, state: ConversationState) -> Dict[str, Any]:
        """从知识池生成初始问题和预期答案

        基于知识池内容、用户画像和场景，生成第一个问题及其预期答案

        Returns:
            Dict包含:
            - question: 生成的用户问题
            - expected_answer: 基于知识池的预期答案
            - knowledge_used: 使用的知识项
        """
        logger.info(f"=== [AGENT] 基于知识池生成初始问题和预期答案 (人格: {state.persona}, 场景: {state.scenario}) ===")

        config = get_persona_config(state.persona)
        knowledge_pool = state.knowledge_pool

        # 格式化知识池
        knowledge_context = self._format_knowledge_pool(knowledge_pool)

        # 获取系统提示词
        system_prompt = self._get_system_prompt(state)

        # 构建用户提示词
        scenario_desc = state.scenario or "咨询"
        persona_desc = config.description if config else "普通客户"

        # 根据平台确定语言
        language_req = "English" if state.platform == "overseas" else "中文"

        user_prompt = f"""## 你的任务
你正在扮演一个{persona_desc}，准备咨询VERTU手机的{scenario_desc}相关问题。

## 参考知识池
{knowledge_context}

## 场景描述
场景：{scenario_desc}
人格：{persona_desc}

## 生成要求
1. 从知识池中选择1-2个感兴趣的信息点
2. 基于这些信息生成一个自然、口语化的{scenario_desc}问题
3. 同时生成这个问题的预期答案（基于知识池中的信息）
4. 问题必须符合你的{state.persona}人格特征
5. 使用具体产品名称，禁止使用"这款手机""它"等代词
6. 语言要求：使用{language_req}

## 输出格式
请严格按照以下JSON格式输出，不要添加任何其他内容：
{{
    "question": "生成的用户问题",
    "expected_answer": "基于知识池生成的预期答案",
    "knowledge_used": ["使用的知识项1", "使用的知识项2"]
}}"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        try:
            start_time = time.time()
            response = await self.chat_model.ainvoke(messages)
            duration = time.time() - start_time

            self._record_llm_call(state, "initial_question_from_knowledge", duration, f"从知识池生成初始问题和预期答案")

            # 解析JSON响应
            result_text = response.content.strip()
            # 清理可能的markdown代码块
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            result = json.loads(result_text)
            question = result.get("question", "").strip().strip('"').strip("'")
            expected_answer = result.get("expected_answer", "").strip()
            knowledge_used = result.get("knowledge_used", [])

            logger.info(f"=== [AGENT] 从知识池生成的初始问题: {question[:60]}... ===")
            logger.info(f"=== [AGENT] 预期答案: {expected_answer[:60]}... ===")

            return {
                "question": question,
                "expected_answer": expected_answer,
                "knowledge_used": knowledge_used
            }
        except Exception as e:
            logger.error(f"=== [AGENT] 从知识池生成初始问题失败: {e} ===")
            # 如果生成失败，从知识池中找一个FAQ问题作为备选
            faq_items = knowledge_pool.get("faq", [])
            if faq_items:
                fallback = random.choice(faq_items)
                question = fallback.get("question", "请介绍一下VERTU手机")
                expected_answer = fallback.get("answer", "")
                logger.info(f"=== [AGENT] 使用知识池中的FAQ作为备选: {question[:50]}... ===")
                return {
                    "question": question,
                    "expected_answer": expected_answer,
                    "knowledge_used": ["faq_fallback"]
                }
            return {
                "question": "请介绍一下VERTU手机的主要特点",
                "expected_answer": "VERTU手机采用高端材质，提供私人管家服务...",
                "knowledge_used": []
            }

    def _format_conversation_context(self, state: ConversationState, bot_answer: str) -> str:
        """格式化对话上下文"""
        if not state.conversation_history:
            return f"这是对话的第一轮，客服刚刚回复：{bot_answer}"

        # 构建完整的对话历史
        history_lines = []
        for i, msg in enumerate(state.conversation_history[-6:], 1):  # 保留最后3轮（6条消息）
            role = "你" if msg['role'] == 'user_agent' else "客服"
            history_lines.append(f"{role}: {msg['content']}")

        context = "\n".join(history_lines)

        return f"""### 对话上下文（最近{len(state.conversation_history[-6:])}条消息）
{context}

### 客服最新回复
{bot_answer}

### 上下文理解要点
- 仔细阅读上述对话历史，理解当前讨论的主题和进展
- 注意客服已经回答了什么，还有哪些问题没有解决
- 基于上下文逻辑，决定是追问、转换话题还是结束对话"""

    async def _generate_next_question(self, state: ConversationState, bot_answer: str, last_question: str) -> str:
        """根据推理行动策略生成下一个问题

        生成问题时同时参考：
        1. 对话上下文 - 确保问题与当前对话主题连贯
        2. 知识池 - 提供背景知识支持，生成更准确的问题
        """
        logger.info(f"=== [AGENT] 生成第 {state.turn_count + 1} 轮问题 (人格: {state.persona}) ===")

        # 构建提示词
        prompt = self._build_agent_prompt(state)

        # 获取系统提示词
        system_prompt = self._get_system_prompt(state)

        # 构建知识池上下文
        knowledge_context = self._format_knowledge_pool(state.knowledge_pool)

        # 构建对话上下文
        conversation_context = self._format_conversation_context(state, bot_answer)

        # 组合完整的用户提示
        user_prompt_parts = [
            "## 你的任务",
            prompt,
            "",
            "## 参考信息",
        ]

        # 添加对话上下文
        user_prompt_parts.extend([
            conversation_context,
            ""
        ])

        # 添加知识池（如果有）
        if knowledge_context:
            user_prompt_parts.extend([
                knowledge_context,
                ""
            ])

        user_prompt_parts.extend([
            "## 决策指引",
            "基于上述【对话上下文】和【知识池】，请决定下一步：",
            "",
            "### 选项A：结束对话",
            "- 如果你的问题已经得到满意解答",
            "- 如果客服提供了足够的信息帮助你做出决定",
            '- 回复格式：直接说"谢谢"或"好的，了解了"等结束语',
            "",
            "### 选项B：继续提问",
            "- 如果还有疑问需要澄清",
            "- 如果想深入了解某个方面",
            "- 可以基于对话上下文进行追问",
            "- 可以参考知识池中的信息提出更深入的问题",
            "- 保持问题的连贯性和逻辑性",
            "",
            "### 选项C：转换话题",
            "- 如果想询问与当前话题相关但不同的方面",
            "- 确保转换自然，不要突兀",
            "",
            "## 生成要求",
            "1. 必须结合对话上下文，保持话题连贯",
            "2. 可以参考知识池中的信息，但不要直接复制",
            "3. 符合你的用户画像特征，语言风格一致",
            "4. 保持口语化、自然的表达方式",
            "5. 单轮回复简洁，符合人设的字数限制",
            "",
            "请直接生成你的回复（结束语或新问题）："
        ])

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="\n".join(user_prompt_parts))
        ]

        try:
            start_time = time.time()
            response = await self.chat_model.ainvoke(messages)
            duration = time.time() - start_time

            self._record_llm_call(state, "generate_question", duration, f"生成第{state.turn_count + 1}轮问题")

            generated_text = response.content.strip()

            # 检查是否是结束语
            ending_keywords = ["谢谢", "了解了", "再见", "好的", "没问题", "end", "thanks", "bye"]
            is_ending = any(keyword in generated_text for keyword in ending_keywords) and len(generated_text) < 30

            if is_ending:
                logger.info(f"=== [AGENT] 用户选择结束对话: {generated_text} ===")

            return generated_text
        except Exception as e:
            logger.error(f"=== [AGENT] 生成问题失败: {e} ===")
            return self._get_fallback_question(state)

    async def _generate_next_question_with_answer(
        self,
        state: ConversationState,
        bot_answer: str,
        last_question: str
    ) -> Dict[str, Any]:
        """生成下一个问题及其预期答案

        生成问题时同时参考：
        1. 对话上下文 - 确保问题与当前对话主题连贯
        2. 知识池 - 提供背景知识支持，生成更准确的问题和预期答案

        Returns:
            Dict包含:
            - question: 生成的用户问题（或结束语）
            - expected_answer: 基于知识池的预期答案
            - knowledge_used: 使用的知识项列表
        """
        logger.info(f"=== [AGENT] 生成第 {state.turn_count + 1} 轮问题及预期答案 (人格: {state.persona}) ===")

        # 构建提示词
        prompt = self._build_agent_prompt(state)

        # 获取系统提示词
        system_prompt = self._get_system_prompt(state)

        # 构建知识池上下文
        knowledge_context = self._format_knowledge_pool(state.knowledge_pool)

        # 构建对话上下文
        conversation_context = self._format_conversation_context(state, bot_answer)

        # 组合完整的用户提示
        user_prompt_parts = [
            "## 你的任务",
            prompt,
            "",
            "## 参考信息",
        ]

        # 添加对话上下文
        user_prompt_parts.extend([
            conversation_context,
            ""
        ])

        # 添加知识池（如果有）
        if knowledge_context:
            user_prompt_parts.extend([
                knowledge_context,
                ""
            ])

        user_prompt_parts.extend([
            "## 决策指引",
            "基于上述【对话上下文】和【知识池】，请决定下一步：",
            "",
            "### 选项A：结束对话",
            "- 如果你的问题已经得到满意解答",
            "- 如果客服提供了足够的信息帮助你做出决定",
            "- 回复格式：直接说\"谢谢\"或\"好的，了解了\"等结束语",
            "- 此时 expected_answer 设为 null",
            "",
            "### 选项B：继续提问",
            "- 如果还有疑问需要澄清",
            "- 如果想深入了解某个方面",
            "- 可以基于对话上下文进行追问",
            "- 可以参考知识池中的信息提出更深入的问题",
            "- 同时生成这个问题的预期答案（基于知识池）",
            "",
            "### 选项C：转换话题",
            "- 如果想询问与当前话题相关但不同的方面",
            "- 确保转换自然，不要突兀",
            "- 同时生成新话题的预期答案",
            "",
            "## 生成要求",
            "1. 必须结合对话上下文，保持话题连贯",
            "2. 可以参考知识池中的信息，但不要直接复制",
            "3. 符合你的用户画像特征，语言风格一致",
            "4. 保持口语化、自然的表达方式",
            "5. 单轮回复简洁，符合人设的字数限制",
            "",
            "## 输出格式",
            "请严格按照以下JSON格式输出：",
            "{",
            '    "question": "生成的用户问题或结束语",',
            '    "expected_answer": "基于知识池生成的预期答案（结束对话时为null）",',
            '    "knowledge_used": ["使用的知识项1", "使用的知识项2"]',
            "}",
            "",
            "请生成："
        ])

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="\n".join(user_prompt_parts))
        ]

        try:
            start_time = time.time()
            response = await self.chat_model.ainvoke(messages)
            duration = time.time() - start_time

            self._record_llm_call(state, "generate_question_with_answer", duration, f"生成第{state.turn_count + 1}轮问题及预期答案")

            # 解析JSON响应
            result_text = response.content.strip()
            # 清理可能的markdown代码块
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            result = json.loads(result_text)
            question = result.get("question", "").strip()
            expected_answer = result.get("expected_answer")
            knowledge_used = result.get("knowledge_used", [])

            # 检查是否是结束语
            ending_keywords = ["谢谢", "了解了", "再见", "好的", "没问题", "end", "thanks", "bye"]
            is_ending = any(keyword in question for keyword in ending_keywords) and len(question) < 30

            if is_ending:
                logger.info(f"=== [AGENT] 用户选择结束对话: {question} ===")
                return {
                    "question": question,
                    "expected_answer": None,
                    "knowledge_used": []
                }

            logger.info(f"=== [AGENT] 生成的问题: {question[:60]}... ===")
            
            # 确保 expected_answer 和 knowledge_used 都有值
            if not expected_answer:
                logger.warning(f"=== [AGENT] 警告: LLM 返回的 expected_answer 为空，使用默认值 ===")
                expected_answer = ""
            if not knowledge_used:
                knowledge_used = []
                
            logger.info(f"=== [AGENT] 预期答案: {expected_answer[:60] if expected_answer else '(空)'}... ===")
            logger.info(f"=== [AGENT] 使用知识: {knowledge_used} ===")

            return {
                "question": question,
                "expected_answer": expected_answer,
                "knowledge_used": knowledge_used
            }
        except Exception as e:
            logger.error(f"=== [AGENT] 生成问题及预期答案失败: {e} ===")
            # 使用备用问题
            fallback_question = self._get_fallback_question(state)
            return {
                "question": fallback_question,
                "expected_answer": None,
                "knowledge_used": ["fallback"]
            }

    def _build_agent_prompt(self, state: ConversationState) -> str:
        """构建代理提示词"""
        config = get_persona_config(state.persona)

        # 语言规则提示
        language_hint = f"""
【平台与语言】
当前平台: {state.platform or 'domestic_jd'}
语言要求: {'英文' if state.platform == 'overseas' else '中文'}
请确保你的回复使用 {'English' if state.platform == 'overseas' else '中文'}。"""

        if config:
            return config.agent_prompt_template + f"\n\n{state.preset_prompt}" + language_hint
        else:
            return f"你正在模拟一个电商客户。\n\n{state.preset_prompt}" + language_hint
    def _get_system_prompt(self, state: ConversationState) -> str:
        """获取系统提示词"""
        config = get_persona_config(state.persona)

        # 语言规则
        language_rule = f"""

【语言规则】
- 当前平台: {state.platform or 'domestic_jd'}
- 如果平台是 "overseas"，所有回复必须使用英文
- 如果平台是 "domestic_jd" 或 "domestic_tm"，使用中文
- 保持人格特征不变，仅切换语言"""

        if config:
            return config.system_prompt_template + language_rule + """

重要提醒：
- 这是一个真实的线上客服对话场景
- 保持自然真实的对话风格，不要表演化
- 根据你的真实需求提出问题，不要过度纠缠细节
- 如果信息足够，及时结束对话表示感谢"""
        else:
            return "你是Vertu手机的用户，正在进行真实的客服对话。" + language_rule

    def _get_fallback_question(self, state: ConversationState) -> str:
        """获取备用问题"""
        if state.question_pool:
            selected = random.choice(state.question_pool)
            # 从备用问题中获取 platform
            question_platform = selected.get('platform', '')
            if question_platform:
                state.platform = question_platform
                logger.info(f"=== [AGENT] 从备用问题设置 platform: {question_platform} ===")
            return selected['question']
        else:
            return "请介绍一下VERTU手机的主要特点"

    async def _select_initial_question(self, persona: str, scenario: str, questions: List[Dict[str, Any]], state: ConversationState) -> str:
        """根据人格和场景选择并生成初始问题"""
        if not questions:
            return self._get_fallback_question(ConversationState())

        config = get_persona_config(persona)
        if config:
            filtered_questions = [q for q in questions if q.get('category', '') in config.preferred_categories]
            if filtered_questions:
                selected = random.choice(filtered_questions)
            else:
                selected = random.choice(questions)
        else:
            selected = random.choice(questions)
        
        selected_question = selected['question']
        # 从问题中获取 platform 并设置到 state
        question_platform = selected.get('platform', '')
        if question_platform:
            state.platform = question_platform
            logger.info(f"=== [AGENT] 从问题池设置 platform: {question_platform} ===")

        # 保存原始问题到状态
        state.original_question = selected_question
        logger.info(f"=== [AGENT] 从问题池选择原始问题: {selected_question[:50]}... ===")

        # 使用大模型改写问题
        try:
            generated_question = await self._generate_scenario_question(selected_question, persona, scenario, config, state)
            logger.info(f"=== [AGENT] 改写后的问题: {generated_question[:50]}... ===")
            return generated_question
        except Exception as e:
            logger.warning(f"场景问题生成失败，使用改写后问题: {e}")
            return await self._rewrite_question_with_llm(selected_question, config, state)

    async def _generate_scenario_question(self, reference_question: str, persona: str, scenario: str, config=None, state: ConversationState = None) -> str:
        """根据场景生成符合的初始问题"""

        # 场景提示词映射
        scenario_prompts = {
            "咨询": "你是咨询场景的客户，想了解VERTU手机的产品信息、功能配置。请基于参考问题，生成一个自然、口语化的咨询问题。",
            "售后": "你是已购买VERTU手机的客户，手机出现了问题或使用上有疑问，需要售后支持。请基于参考问题，生成一个自然、口语化的售后咨询问题。",
            "犹豫": "你对VERTU手机感兴趣但还在犹豫是否购买，关心价格、性价比、优惠活动。请基于参考问题，生成一个试探性的询问问题。",
            "竞品对比": "你正在对比VERTU和其他品牌手机（如华为、三星、苹果），想了解VERTU的优势差异。请基于参考问题，生成一个对比咨询问题。",
            "闲聊": "你与客服闲聊，语气轻松随意，可能顺便问问VERTU手机的情况。请基于参考问题，生成一个自然、随意的闲聊问题。"
        }

        scenario_desc = scenario_prompts.get(scenario, scenario_prompts["咨询"])
        persona_desc = config.description if config else "普通客户"

        # 根据平台确定语言
        platform = state.platform if state else None
        language_req = "English" if platform == "overseas" else "中文"

        prompt = f"""{scenario_desc}

你的人格特征：{persona_desc}

参考问题（仅作为灵感参考，不要直接复制）：
{reference_question}

语言要求：请使用{language_req}生成问题

要求：
1. 必须符合"{scenario}"场景的特征
2. 必须使用具体产品名称（如"VERTU Agent Q"），禁止使用"这款手机""它"等代词
3. 语气要符合你的人格特征
4. 问题要口语化、自然，像真实客户会问的
5. 只输出问题本身，不要任何解释

生成的问题："""

        messages = [{"role": "user", "content": prompt}]
        
        start_time = time.time()
        response = await self.chat_model.ainvoke(messages)
        duration = time.time() - start_time
        
        if state:
            self._record_llm_call(state, "scenario_question", duration, f"场景[{scenario}]生成问题")
        
        return response.content.strip().strip('"')

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
            "platform": state.platform,
            "scenario": state.scenario,
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
                    "timestamp": msg["timestamp"],
                    **({"expected_answer": msg["expected_answer"]} if "expected_answer" in msg else {}),
                    **({"knowledge_used": msg["knowledge_used"]} if "knowledge_used" in msg else {})
                }
                for msg in state.conversation_history
            ],
            "original_question": state.original_question,  # 从问题池选择的原始问题
            "initial_question": state.initial_question,  # LLM改写后实际使用的问题
            "original_query_results": state.original_query_results  # 使用原始问题查询的结果
        }

        sessions_dir = Path("mock_sessions")
        sessions_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{state.session_id}_{timestamp}.json"
        filepath = sessions_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        logger.info(f"会话数据已保存到: {filepath}")
        return session_data
