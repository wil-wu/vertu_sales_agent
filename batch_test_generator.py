#!/usr/bin/env python3
"""
批量对话生成与评估系统

功能：
- 为五个人格批量生成对话session
- 使用 Referee Agent 评估所有对话
- 汇总结果并分类保存

使用方法:
    python batch_test_generator.py
    
可选参数:
    --sessions-per-persona: 每个人格生成的对话数 (默认: 200)
    --max-turns: 每轮对话最大轮数 (默认: 10)
    --output-dir: 输出文件夹路径 (默认: batch_test_results_YYYYMMDD_HHMMSS/)
    --parallel: 并行执行的对话数 (默认: 3)
    --knowledge-pool: 知识池 JSON 文件路径 (可选，用于替代 mock 数据)

示例:
    python batch_test_generator.py --sessions-per-persona 50 --max-turns 8
    python batch_test_generator.py --parallel 5 --output-dir my_results
    python batch_test_generator.py --knowledge-pool knowledge_pool.json
"""

import json
import asyncio
import sys
import argparse
import logging
import traceback
from pathlib import Path 
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import functools

# 异步函数专用的 retry 装饰器
def retry_async(tries=3, delay=1, backoff=2, logger=None):
    """
    异步函数重试装饰器
    
    Args:
        tries: 最大尝试次数
        delay: 初始延迟秒数
        backoff: 延迟倍数
        logger: 日志记录器
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, tries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < tries:
                        if logger:
                            logger.warning(f"[RETRY] {func.__name__} 第 {attempt}/{tries} 次尝试失败: {type(e).__name__}: {e}，{current_delay}秒后重试...")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        if logger:
                            logger.error(f"[RETRY FAILED] {func.__name__} 所有 {tries} 次尝试均失败，最终异常: {type(e).__name__}: {e}")
                        raise last_exception
            
            raise last_exception
        
        return wrapper
    return decorator

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入三个 Agent
from app.services.referee_agent.agent import referee_agent
from app.services.user_agent.agent import UserAgent
from app.services.user_agent.shared import chat_model as user_chat_model
from app.services.user_agent.user_config import get_persona_config, get_all_persona_names
from app.services.react_agent.agent import ReActAgent
from app.services.react_agent.shared import chat_model as react_chat_model
from app.services.react_agent.tools import TOOLS
from app.services.react_agent.prompts import REACT_AGENT_SYSTEM_PROMPT
from app.services.react_agent.utils import MarkdownHelper
from langchain_core.messages import AIMessage, ToolMessage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'batch_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DirectReactAgentAdapter:
    """ReactAgent 适配器 - 提供与 HTTP API 相同的接口"""
    
    def __init__(self, agent: ReActAgent):
        self.agent = agent
        self.current_platform = "simulation"
        
    async def chat(self, message: str, thread_id: str, user_id: str = "simulation_user", platform: str = "simulation", region: str = "国内") -> dict:
        """调用 ReActAgent，将 platform 等信息追加到消息中（支持流式输出和链接提取）"""
        try:
            # 保存当前 platform，供工具使用
            self.current_platform = platform
            
            # 将 platform 等信息追加到消息中，与 HTTP API 保持一致
            # 在消息开头明确声明用户平台，让 LLM 更清楚地知道
            enhanced_message = f"【用户来源平台：{platform}】\n{message}\n\n严格遵循用户输入的语种进行回复！！！\n用户id：{user_id}\n平台：{platform}\n地区：{region}\n\n重要提示：当需要调用发送微信通知工具时，platform 参数必须使用 '{platform}'，不要自行编造其他值。"
            
            # 使用流式输出并提取 graph_query 链接（与 HTTP API 保持一致）
            agent_content = ""
            graph_query_links = []
            
            async for event in self.agent.astream(enhanced_message, thread_id, stream_mode="updates"):
                if "agent" in event:
                    msgs = event["agent"].get("messages", [])
                    if msgs:
                        last_msg = msgs[-1]
                        if isinstance(last_msg, AIMessage) and last_msg.content:
                            content = (
                                last_msg.content
                                if isinstance(last_msg.content, str)
                                else str(last_msg.content)
                            )
                            agent_content = MarkdownHelper.remove_markdown_links(content)
                
                if "tools" in event:
                    msgs = event["tools"].get("messages", [])
                    for msg in msgs:
                        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == "graph_query":
                            content = msg.content
                            if isinstance(content, list):
                                content = "\n".join(str(item) for item in content)
                            else:
                                content = content if isinstance(content, str) else str(content)
                            graph_query_links.extend(MarkdownHelper.extract_markdown_links(content))
            
            # 如果有 graph_query 链接，追加到消息中
            if graph_query_links:
                response = f"{agent_content}\n\n" + "\n".join(graph_query_links)
            else:
                response = agent_content
            
            return {
                "message": response,
                "status": "success",
                "thread_id": thread_id
            }
        except Exception as e:
            return {
                "message": f"抱歉，服务暂时不可用: {str(e)}",
                "status": "error",
                "error": str(e),
                "thread_id": thread_id
            }


class DirectUserAgent(UserAgent):
    """直接连接版本的 UserAgent"""
    
    def __init__(self, chat_model=None, system_prompt: str = "", react_agent=None):
        super().__init__(chat_model, system_prompt, "")
        self.direct_react_agent = react_agent
    
    async def _generate_next_question(self, state, bot_answer, last_question):
        """生成问题（带重试）"""
        return await super()._generate_next_question(state, bot_answer, last_question)
    
    async def _call_target_bot(self, client, question: str, thread_id: str, user_id: str = "simulation_user", platform: str = "simulation", region: str = "国内") -> Any:
        """直接调用 ReActAgent 而不是 HTTP API（带重试）"""
        try:
            # 传递 platform 参数给 ReAct Agent
            response = await self.direct_react_agent.chat(question, thread_id, user_id, platform, region)
            return response
        except Exception as e:
            logger.error(f"ReAct Agent 调用失败: {e}")
            raise


@dataclass
class TestResult:
    """单个测试会话的结果"""
    session_id: str
    persona: str
    scenario: str
    finish_reason: str
    total_turns: int
    duration_seconds: float
    
    # 评估结果
    dimension_scores: Dict[str, float]
    user_anthropomorphism: Dict[str, Any]
    agent_anthropomorphism: Dict[str, Any]
    purchase_intent: Dict[str, Any]
    problem_solving: Dict[str, Any]
    sales_script: Dict[str, Any]
    user_experience: Dict[str, Any]
    traditional_script: Dict[str, Any]
    language_consistency: Dict[str, Any]
    
    # 每轮评估
    turn_assessments: List[Dict[str, Any]]
    
    # 首轮问答对比（用于 first_contact_resolution 评估）
    first_turn_qa_comparison: Optional[Dict[str, Any]] = None
    
    # 错误信息（如果有）
    error: Optional[str] = None


@dataclass
class PersonaSummary:
    """单个人格的汇总统计"""
    persona: str
    description: str
    total_sessions: int
    successful_evaluations: int
    failed_evaluations: int
    
    # 平均维度评分
    avg_dimension_scores: Dict[str, float]
    
    # 结束原因分布
    finish_reason_distribution: Dict[str, int]
    
    # 平均轮数
    avg_turns: float
    
    # 总耗时
    total_duration: float
    
    # 首次解决率统计
    first_contact_resolution_stats: Dict[str, Any] = None
    
    # 语言一致性统计
    language_consistency_stats: Dict[str, Any] = None
    
    # 评估状态分布（新增）
    evaluation_status: Dict[str, int] = None
    
    # 评估失败的 session 信息（新增）
    failed_sessions: List[Dict[str, Any]] = None


class BatchTestRunner:
    """批量测试运行器"""
    
    def __init__(self, max_parallel: int = 3, output_dir: str = "", knowledge_pool_file: str = ""):
        self.max_parallel = max_parallel
        self.output_dir = output_dir
        self.knowledge_pool_file = knowledge_pool_file
        self.react_adapter = None
        self.referee = referee_agent
        self.results: List[TestResult] = []
        self._knowledge_pool_cache: Optional[Dict[str, Any]] = None
        
    def initialize_agents(self):
        """初始化 Agent"""
        logger.info("初始化 ReAct Agent (客服机器人)...")
        agent = ReActAgent(
            chat_model=react_chat_model,
            tools=TOOLS,
            system_prompt=REACT_AGENT_SYSTEM_PROMPT
        )
        self.react_adapter = DirectReactAgentAdapter(agent)
        logger.info("ReAct Agent 初始化完成")
        
        # 如果指定了知识池文件，加载它
        if self.knowledge_pool_file:
            self._load_knowledge_pool()
    
    def _load_knowledge_pool(self) -> Dict[str, Any]:
        """从 JSON 文件加载知识池
        
        Returns:
            知识池数据 {"faq": [...], "price": [...], "graph": [...]}
        """
        if self._knowledge_pool_cache is not None:
            return self._knowledge_pool_cache
            
        if not self.knowledge_pool_file:
            logger.warning("未指定知识池文件，将使用 mock 数据")
            return {}
            
        try:
            file_path = Path(self.knowledge_pool_file)
            if not file_path.exists():
                logger.error(f"知识池文件不存在: {self.knowledge_pool_file}")
                return {}
                
            with open(file_path, 'r', encoding='utf-8') as f:
                knowledge_pool = json.load(f)
                
            # 验证知识池结构
            if not isinstance(knowledge_pool, dict):
                logger.error("知识池文件格式错误，应该是一个 JSON 对象")
                return {}
                
            faq_count = len(knowledge_pool.get('faq', []))
            price_count = len(knowledge_pool.get('price', []))
            graph_count = len(knowledge_pool.get('graph', []))
            
            logger.info(f"成功加载知识池 - FAQ: {faq_count}条, 价格: {price_count}条, 图谱: {graph_count}条")
            
            self._knowledge_pool_cache = knowledge_pool
            return knowledge_pool
            
        except json.JSONDecodeError as e:
            logger.error(f"知识池文件 JSON 解析错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"加载知识池文件失败: {e}")
            return {}
    
    def _generate_knowledge_pool(self, persona: str, scenario: str) -> Dict[str, Any]:
        """根据人格和场景筛选知识池内容
        
        Args:
            persona: 人格名称
            scenario: 测试场景描述
        
        Returns:
            筛选后的知识池数据 {"faq": [...], "price": [...], "graph": [...]}
        """
        # 获取人格配置
        persona_config = get_persona_config(persona)
        preferred_categories = persona_config.preferred_categories if persona_config else []
        
        # 场景到意图类别的映射（使用知识池中实际存在的 intent 值）
        scenario_to_intent = {
            "咨询VERTU手机的产品特性和价格": ["产品&功能咨询", "Product & Feature Inquiry"],
            "了解VERTU售后服务和保修政策": ["After-sales & Warranty Inquiry", "产品&功能咨询"],
            "犹豫是否购买VERTU手机，需要更多购买建议": ["产品&功能咨询", "使用&配件咨询"],
            "将VERTU手机与其他品牌竞品进行对比": ["产品&功能咨询", "Product & Category Inquiry"],
            "与客服闲聊，了解VERTU品牌故事和高端服务": ["使用&配件咨询", "Usage & Accessories Inquiry"],
        }
        
        # 获取当前场景对应的意图类别
        scenario_intents = scenario_to_intent.get(scenario, [])
        
        # 使用外部知识池文件，根据人格和场景筛选
        if self._knowledge_pool_cache:
            logger.info(f"使用外部知识池文件: {self.knowledge_pool_file}, 人格: {persona}, 场景: {scenario}")
            return self._filter_knowledge_pool_by_persona_and_scenario(
                self._knowledge_pool_cache, 
                persona, 
                scenario,
                preferred_categories,
                scenario_intents
            )
        
        # 如果没有加载知识池文件，返回空知识池（需要用户提供知识池文件）
        logger.error(f"未加载知识池文件，无法生成知识池。请使用 --knowledge-pool 参数提供知识池文件")
        return {
            "faq": [],
            "price": [],
            "graph": [],
            "metadata": {
                "scenario": scenario,
                "persona": persona,
                "preferred_categories": preferred_categories,
                "error": "未加载知识池文件",
                "generated_at": datetime.now().isoformat()
            }
        }
    
    def _filter_knowledge_pool_by_persona_and_scenario(
        self, 
        knowledge_pool: Dict[str, Any], 
        persona: str, 
        scenario: str,
        preferred_categories: List[str],
        scenario_intents: List[str]
    ) -> Dict[str, Any]:
        """根据人格和场景筛选知识池内容
        
        Args:
            knowledge_pool: 原始知识池
            persona: 人格名称
            scenario: 场景描述
            preferred_categories: 人格偏好的类别
            scenario_intents: 场景对应的意图类别
        
        Returns:
            筛选后的知识池
        """
        filtered_pool = {
            "faq": [],
            "price": knowledge_pool.get("price", []),
            "graph": knowledge_pool.get("graph", []),
            "metadata": {
                "scenario": scenario,
                "persona": persona,
                "preferred_categories": preferred_categories,
                "scenario_intents": scenario_intents,
                "filtered": True,
                "generated_at": datetime.now().isoformat()
            }
        }
        
        # 筛选 FAQ - 根据 intent 匹配
        faq_data = knowledge_pool.get("faq", [])
        for faq_entry in faq_data:
            if not isinstance(faq_entry, dict):
                continue
                
            categories = faq_entry.get("categories", [])
            for category in categories:
                items = category.get("items", [])
                category_name = category.get("category_name", "")
                
                # 检查类别是否匹配场景意图或人格偏好
                is_match = (
                    category_name in scenario_intents or
                    category_name in preferred_categories or
                    any(intent in category_name for intent in scenario_intents)
                )
                
                if is_match:
                    filtered_pool["faq"].append(faq_entry)
                    break
        
        # 如果没有匹配到任何内容，返回原始 FAQ 的前10条作为保底
        if not filtered_pool["faq"]:
            logger.warning(f"人格 {persona} + 场景 {scenario} 没有匹配到相关内容，使用默认内容")
            for faq_entry in faq_data[:10]:
                if isinstance(faq_entry, dict):
                    filtered_pool["faq"].append(faq_entry)
        
        faq_count = len(filtered_pool["faq"])
        price_count = len(filtered_pool["price"])
        graph_count = len(filtered_pool["graph"])
        
        logger.info(f"筛选后知识池 - 人格: {persona}, 场景: {scenario}, FAQ: {faq_count}条, 价格: {price_count}条, 图谱: {graph_count}条")
        return filtered_pool
    
    @retry_async(tries=2, delay=0.5, backoff=1.5, logger=logger)
    async def _call_referee_with_retry(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """调用 Referee Agent 评估会话（带重试和超时）"""
        try:
            return await asyncio.wait_for(
                self.referee.generate_session_summary(session_data),
                timeout=300  # 5分钟超时
            )
        except asyncio.TimeoutError:
            logger.error(f"Referee Agent 评估超时（5分钟）")
            raise
        
    async def run_single_session(
        self, 
        persona: str, 
        scenario: str, 
        max_turns: int,
        session_index: int
    ) -> TestResult:
        """运行单个会话"""
        start_time = datetime.now()
        session_id = f"{persona}_{session_index}_{start_time.strftime('%H%M%S')}"
        
        logger.info(f"[{session_id}] 开始测试 - 人格: {persona}")
        
        try:
            # 创建 User Agent
            user_agent = DirectUserAgent(
                chat_model=user_chat_model,
                system_prompt=f"你是一个{get_persona_config(persona).description}用户，正在咨询VERTU手机。",
                react_agent=self.react_adapter
            )
            
            # 生成 mock 知识池（根据人格和场景筛选）
            knowledge_pool = self._generate_knowledge_pool(persona, scenario)
            
            # 运行仿真（传入知识池）
            session_data = await user_agent.start_simulation(
                persona=persona,
                scenario=scenario,
                max_turns=max_turns,
                knowledge_pool=knowledge_pool
            )
            
            # 从对话记录中提取首轮预期答案
            conversation = session_data.get('conversation', [])
            first_user_message = None
            first_bot_message = None
            for msg in conversation:
                if msg.get('role') == 'user_agent' and not first_user_message:
                    first_user_message = msg
                elif msg.get('role') == 'target_bot' and not first_bot_message:
                    first_bot_message = msg
                    break
            
            # 提取首轮问题和预期答案
            first_question = first_user_message.get('content', '') if first_user_message else ''
            first_expected_answer = first_user_message.get('expected_answer', '') if first_user_message else ''
            first_knowledge_used = first_user_message.get('knowledge_used', []) if first_user_message else []
            first_actual_answer = first_bot_message.get('content', '') if first_bot_message else ''
            
            logger.info(f"[{session_id}] 从对话记录提取首轮信息:")
            logger.info(f"[{session_id}] 问题: {first_question[:50]}...")
            logger.info(f"[{session_id}] 预期答案: {first_expected_answer[:50] if first_expected_answer else '无'}...")
            logger.info(f"[{session_id}] 使用知识: {first_knowledge_used}")
            
            # 评估会话（带重试）
            summary = await self._call_referee_with_retry(session_data)
            
            # 计算耗时
            duration = (datetime.now() - start_time).total_seconds()
            
            # 提取首轮问答对比信息（优先使用对话记录中的数据）
            turn_assessments = summary.get('turn_assessments', [])
            first_turn_qa = None
            
            # 从评估结果中获取 first_contact_resolution
            first_contact_resolution = False
            if turn_assessments and len(turn_assessments) > 0:
                first_turn = turn_assessments[0]
                first_contact_resolution = first_turn.get('first_contact_resolution', False)
            
            # 构建首轮问答对比（使用对话记录中的预期答案）
            first_turn_qa = {
                "question": first_question,
                "conversation_question": first_question,
                "expected_answer": first_expected_answer,
                "actual_answer": first_actual_answer,
                "first_contact_resolution": first_contact_resolution,
                "knowledge_used": first_knowledge_used
            }
            
            if first_expected_answer:
                logger.info(f"[{session_id}] 首轮问答对比 - 预期答案来源: 对话记录")
                logger.info(f"[{session_id}] first_contact_resolution: {first_contact_resolution}")
            
            # 构建结果
            detailed = summary.get('detailed_summary', {})
            
            # 从 turn_assessments 汇总 traditional_script 和 language_consistency
            traditional_script_data = {}
            language_consistency_data = {}
            
            if turn_assessments:
                # 汇总 traditional_script
                tech_simplifications = []
                for ta in turn_assessments:
                    dm = ta.get('detailed_metrics', {})
                    ts = dm.get('traditional_script', {})
                    if ts and 'technical_term_simplification' in ts:
                        tech_simplifications.append(ts['technical_term_simplification'])
                
                if tech_simplifications:
                    traditional_script_data = {
                        'avg_technical_term_simplification': round(sum(tech_simplifications) / len(tech_simplifications), 2)
                    }
                
                # 汇总 language_consistency
                language_matches = []
                for ta in turn_assessments:
                    dm = ta.get('detailed_metrics', {})
                    lc = dm.get('language_consistency', {})
                    if lc and 'language_match' in lc:
                        language_matches.append(lc['language_match'])
                
                if language_matches:
                    match_count = sum(1 for m in language_matches if m)
                    language_consistency_data = {
                        'language_match_rate': round(match_count / len(language_matches) * 100, 2)
                    }
            
            result = TestResult(
                session_id=session_data.get('session_id', session_id),
                persona=persona,
                scenario=scenario,
                finish_reason=session_data.get('finish_reason', 'unknown'),
                total_turns=session_data.get('metadata', {}).get('total_turns', 0),
                duration_seconds=duration,
                dimension_scores=detailed.get('dimension_scores', {}),
                user_anthropomorphism=detailed.get('user_anthropomorphism', {}),
                agent_anthropomorphism=detailed.get('agent_anthropomorphism', {}),
                purchase_intent=detailed.get('purchase_intent', {}),
                problem_solving=detailed.get('problem_solving', {}),
                sales_script=detailed.get('sales_script', {}),
                user_experience=detailed.get('user_experience', {}),
                traditional_script=traditional_script_data if traditional_script_data else detailed.get('traditional_script', {}),
                language_consistency=language_consistency_data if language_consistency_data else detailed.get('language_consistency', {}),
                turn_assessments=turn_assessments,
                first_turn_qa_comparison=first_turn_qa,
                error=None
            )
            
            logger.info(f"[{session_id}] 完成 - 轮数: {result.total_turns}, 耗时: {duration:.1f}s")
            return result
            
        except asyncio.CancelledError:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"[{session_id}] 任务被取消（超时）")
            return TestResult(
                session_id=session_id,
                persona=persona,
                scenario=scenario,
                finish_reason="cancelled",
                total_turns=0,
                duration_seconds=duration,
                dimension_scores={},
                user_anthropomorphism={},
                agent_anthropomorphism={},
                purchase_intent={},
                problem_solving={},
                sales_script={},
                user_experience={},
                traditional_script={},
                language_consistency={},
                turn_assessments=[],
                error="任务被取消（超时）"
            )
        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"[{session_id}] 超时: {e}")
            return TestResult(
                session_id=session_id,
                persona=persona,
                scenario=scenario,
                finish_reason="timeout",
                total_turns=0,
                duration_seconds=duration,
                dimension_scores={},
                user_anthropomorphism={},
                agent_anthropomorphism={},
                purchase_intent={},
                problem_solving={},
                sales_script={},
                user_experience={},
                traditional_script={},
                language_consistency={},
                turn_assessments=[],
                error=str(e) if e else "超时"
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"[{session_id}] 失败: {e}")
            logger.error(f"[{session_id}] 异常类型: {type(e).__name__}")
            logger.error(f"[{session_id}] 异常详情: {traceback.format_exc()}")
            
            return TestResult(
                session_id=session_id,
                persona=persona,
                scenario=scenario,
                finish_reason="error",
                total_turns=0,
                duration_seconds=duration,
                dimension_scores={},
                user_anthropomorphism={},
                agent_anthropomorphism={},
                purchase_intent={},
                problem_solving={},
                sales_script={},
                user_experience={},
                traditional_script={},
                language_consistency={},
                turn_assessments=[],
                error=str(e) if e else "未知错误"
            )
    
    async def run_persona_batch(
        self, 
        persona: str, 
        num_sessions: int, 
        max_turns: int
    ) -> List[TestResult]:
        """运行单个人格的批量测试（添加超时和异常处理，每个session完成后立即写入）"""
        logger.info(f"\n{'='*60}")
        logger.info(f"开始测试人格: {persona} ({get_persona_config(persona).description})")
        logger.info(f"计划生成对话数: {num_sessions}")
        logger.info(f"{'='*60}")
        
        # 为每个人格生成不同的场景变体
        base_scenarios = [
            f"咨询VERTU手机的产品特性和价格",
            f"了解VERTU售后服务和保修政策",
            f"犹豫是否购买VERTU手机，需要更多购买建议",
            f"将VERTU手机与其他品牌竞品进行对比",
            f"与客服闲聊，了解VERTU品牌故事和高端服务",
        ]
        
        # 初始化该人格的结果文件
        self._init_persona_results_file(Path(self.output_dir), persona)
        
        tasks = []
        for i in range(num_sessions):
            scenario = base_scenarios[i % len(base_scenarios)]
            task = self.run_single_session(persona, scenario, max_turns, i)
            tasks.append(task)
        
        # 使用信号量控制并发数
        semaphore = asyncio.Semaphore(self.max_parallel)
        
        async def run_with_semaphore(task, index):
            async with semaphore:
                try:
                    result = await task
                    # 每个session完成后立即写入文件
                    if result is not None:
                        self._append_persona_result(Path(self.output_dir), persona, result)
                        logger.info(f"[{persona}] 进度: {index + 1}/{num_sessions} - Session {result.session_id} 已保存")
                    return result
                except asyncio.CancelledError:
                    logger.error(f"任务被取消（超时）")
                    return None
                except Exception as e:
                    logger.error(f"任务执行失败: {e}")
                    return None
        
        # 并发执行所有任务（添加超时和异常处理）
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[run_with_semaphore(t, i) for i, t in enumerate(tasks)], return_exceptions=True),
                timeout=3600  # 1小时超时
            )
        except asyncio.TimeoutError:
            logger.error(f"人格 {persona} 测试超时（1小时），部分任务未完成")
            # 取消所有未完成的任务
            for task in tasks:
                if not task.done():
                    task.cancel()
            # 只收集已完成的结果
            results = [t.result() if t.done() else None for t in tasks]
        
        # 过滤掉失败的结果和异常
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"任务异常: {result}")
            elif result is not None:
                valid_results.append(result)
        
        logger.info(f"人格 {persona} 测试完成: {len(valid_results)} 条对话成功")
        return valid_results
    
    def _init_persona_results_file(self, output_dir: Path, persona: str):
        """初始化人格结果文件（如果不存在则创建）"""
        output_dir.mkdir(parents=True, exist_ok=True)
        persona_file = output_dir / f"{persona}_detailed.json"
        
        if not persona_file.exists():
            data = {
                "persona": persona,
                "description": get_persona_config(persona).description if get_persona_config(persona) else "",
                "generated_at": datetime.now().isoformat(),
                "total_sessions": 0,
                "sessions": []
            }
            with open(persona_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"[{persona}] 初始化结果文件: {persona_file}")
    
    def _append_persona_result(self, output_dir: Path, persona: str, result: TestResult):
        """追加单个session的结果到人格结果文件"""
        persona_file = output_dir / f"{persona}_detailed.json"
        
        # 读取现有数据
        with open(persona_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 追加新结果
        data["sessions"].append(asdict(result))
        data["total_sessions"] = len(data["sessions"])
        data["updated_at"] = datetime.now().isoformat()
        
        # 保存
        with open(persona_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def calculate_persona_summary(self, results: List[TestResult]) -> PersonaSummary:
        """计算单个人格的汇总统计"""
        if not results:
            return None
        
        persona = results[0].persona
        config = get_persona_config(persona)
        
        # 成功的定义：没有 error 且 dimension_scores 不为空（有评估结果）
        successful = [r for r in results if r.error is None and r.dimension_scores]
        # 失败的定义：有 error 或 dimension_scores 为空（评估失败）
        failed = [r for r in results if r.error is not None or not r.dimension_scores]
        
        # 计算平均维度评分（只包含有评估结果的 session）
        avg_scores = {}
        if successful:
            all_scores = [r.dimension_scores for r in successful if r.dimension_scores]
            if all_scores:
                score_keys = all_scores[0].keys()
                for key in score_keys:
                    values = [s.get(key, 0) for s in all_scores if key in s and s.get(key, 0) > 0]
                    avg_scores[key] = round(sum(values) / len(values), 2) if values else 0
        
        # 将维度评分转换为中文
        avg_scores_chinese = convert_scores_to_chinese(avg_scores)
        
        # 结束原因分布
        finish_reasons = {}
        for r in results:
            reason = r.finish_reason
            finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
        
        # 添加评估状态分布
        evaluation_status = {
            "评估成功": len(successful),
            "评估失败": len(failed)
        }
        
        # 平均轮数（只统计成功的 session）
        avg_turns = sum(r.total_turns for r in successful) / len(successful) if successful else 0
        
        # 总耗时
        total_duration = sum(r.duration_seconds for r in results)
        
        # 计算首次解决率统计（只统计成功的 session）
        fcr_stats = None
        if successful:
            # 统计有预期答案的session数量
            sessions_with_expected = [r for r in successful if r.first_turn_qa_comparison and r.first_turn_qa_comparison.get('expected_answer')]
            # 统计首次解决成功的session数量
            sessions_fcr_true = [r for r in successful if r.first_turn_qa_comparison and r.first_turn_qa_comparison.get('first_contact_resolution') == True]
            
            total_with_expected = len(sessions_with_expected)
            total_fcr_true = len(sessions_fcr_true)
            
            fcr_stats = {
                "总会话数": len(successful),
                "有预期答案的会话": total_with_expected,
                "首次解决成功": total_fcr_true,
                "首次解决率": round(total_fcr_true / total_with_expected * 100, 2) if total_with_expected > 0 else 0.0,
                "无预期答案的会话": len(successful) - total_with_expected
            }
        
        # 计算语言一致性统计（只统计成功的 session）
        lc_stats = None
        if successful:
            # 统计语言一致的session数量
            sessions_language_match = [r for r in successful if r.language_consistency and r.language_consistency.get('language_match') == True]
            # 统计语言不一致的session数量
            sessions_language_mismatch = [r for r in successful if r.language_consistency and r.language_consistency.get('language_match') == False]
            
            total_match = len(sessions_language_match)
            total_mismatch = len(sessions_language_mismatch)
            
            # 计算语言一致性得分：一致的session占比
            lc_score = round(total_match / len(successful) * 100, 2) if successful else 0.0
            
            lc_stats = {
                "总会话数": len(successful),
                "语言一致": total_match,
                "语言不一致": total_mismatch,
                "语言一致性得分": lc_score
            }
        
        # 记录评估失败的 session 信息
        failed_sessions_info = []
        for r in failed:
            failed_sessions_info.append({
                "session_id": r.session_id,
                "finish_reason": r.finish_reason,
                "total_turns": r.total_turns,
                "error": r.error or "评估结果为空"
            })
        
        return PersonaSummary(
            persona=persona,
            description=config.description if config else "",
            total_sessions=len(results),
            successful_evaluations=len(successful),
            failed_evaluations=len(failed),
            avg_dimension_scores=avg_scores_chinese,
            finish_reason_distribution=finish_reasons,
            avg_turns=round(avg_turns, 2),
            total_duration=round(total_duration, 2),
            first_contact_resolution_stats=fcr_stats,
            language_consistency_stats=lc_stats,
            evaluation_status=evaluation_status,
            failed_sessions=failed_sessions_info if failed_sessions_info else None
        )
    
    async def run_all_tests(
        self, 
        sessions_per_persona: int, 
        max_turns: int
    ) -> Dict[str, Any]:
        """运行所有测试"""
        logger.info("\n" + "="*60)
        logger.info("🚀 批量对话生成与评估系统")
        logger.info("="*60)
        
        # 初始化 Agent
        self.initialize_agents()
        
        # 获取所有人格
        personas = get_all_persona_names()
        logger.info(f"测试人格: {', '.join(personas)}")
        logger.info(f"每个人格对话数: {sessions_per_persona}")
        logger.info(f"最大对话轮数: {max_turns}")
        logger.info(f"并行数: {self.max_parallel}")
        
        all_results = []
        all_summaries = []
        
        # 为每个人格运行测试
        for persona in personas:
            try:
                results = await self.run_persona_batch(
                        persona, 
                        sessions_per_persona, 
                        max_turns
                )
                all_results.extend(results)
                
                # 计算该人格的汇总
                summary = self.calculate_persona_summary(results)
                all_summaries.append(summary)
                
                # 保存中间结果（详细结果已在run_persona_batch中实时写入）
                self.save_intermediate_results(all_results, all_summaries, Path(self.output_dir))
            except Exception as e:
                # 检测到 API key 余额不足等严重错误
                error_msg = str(e).lower()
                if "insufficient balance" in error_msg or "exceeded_current_quota" in error_msg or "error code: 429" in error_msg:
                    logger.error(f"检测到 API key 余额不足或其他严重错误: {e}")
                    logger.info(f"已生成 {len(all_results)} 个 session，正在生成最终报告...")
                    
                    # 基于已生成的数据生成最终报告
                    report = self.generate_final_report(all_results, all_summaries)
                    
                    # 添加错误信息到报告
                    report["_interrupted"] = {
                        "reason": "API key 余额不足或严重错误",
                        "error": str(e),
                        "completed_sessions": len(all_results),
                        "completed_personas": len(all_summaries)
                    }
                    
                    # 保存最终报告
                    output_file = Path(self.output_dir) / "full_report.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(report, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"最终报告已保存: {output_file}")
                    logger.info(f"已完成的 session 数: {len(all_results)}")
                    logger.info(f"已完成的人格数: {len(all_summaries)}")
                    
                    return report
                else:
                    # 其他错误，继续尝试下一个人格
                    logger.error(f"人格 {persona} 运行失败: {e}")
                    continue
        
        # 生成最终报告
        return self.generate_final_report(all_results, all_summaries)
    
    def save_persona_results(self, output_dir: Path, persona: str, results: List[TestResult]):
        """保存单个人格的详细结果"""
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        persona_file = output_dir / f"{persona}_detailed.json"
        
        data = {
            "persona": persona,
            "description": get_persona_config(persona).description if get_persona_config(persona) else "",
            "generated_at": datetime.now().isoformat(),
            "total_sessions": len(results),
            "sessions": [asdict(r) for r in results]
        }
        
        with open(persona_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[{persona}] 详细结果已保存: {persona_file}")

    def save_intermediate_results(self, results: List[TestResult], summaries: List[PersonaSummary], output_dir: Path):
        """保存中间结果"""
        temp_file = output_dir / "intermediate_progress.json"
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "completed_personas": len(summaries),
            "total_sessions": len(results),
            "summaries": [asdict(s) for s in summaries],
            "recent_results": [asdict(r) for r in results[-10:]]  # 只保存最近10条
        }
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def generate_final_report(
        self, 
        results: List[TestResult], 
        summaries: List[PersonaSummary]
    ) -> Dict[str, Any]:
        """生成最终报告（从各人格详细文件读取数据）"""
        
        # 从文件读取各人格的详细数据
        all_results_from_files = []
        all_summaries_from_files = []
        
        output_dir = Path(self.output_dir)
        personas = get_all_persona_names()
        
        logger.info("正在从各人格详细文件读取数据生成最终报告...")
        
        for persona in personas:
            persona_file = output_dir / f"{persona}_detailed.json"
            if persona_file.exists():
                try:
                    with open(persona_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 读取该人格的所有 session
                    sessions = data.get("sessions", [])
                    
                    # 转换为 TestResult 对象
                    for session_data in sessions:
                        result = TestResult(**session_data)
                        all_results_from_files.append(result)
                    
                    # 计算该人格的汇总
                    if sessions:
                        summary = self.calculate_persona_summary_from_data(persona, sessions)
                        if summary:
                            all_summaries_from_files.append(summary)
                    
                    logger.info(f"[{persona}] 从文件读取了 {len(sessions)} 个 session")
                    
                except Exception as e:
                    logger.error(f"[{persona}] 读取详细文件失败: {e}")
            else:
                logger.warning(f"[{persona}] 详细文件不存在: {persona_file}")
        
        # 使用从文件读取的数据（如果没有则从内存获取）
        if all_results_from_files:
            results = all_results_from_files
            summaries = all_summaries_from_files
            logger.info(f"最终报告使用文件数据: {len(results)} 个 session")
        else:
            logger.warning("未从文件读取到数据，使用内存数据")
        
        # 计算总体统计
        total_sessions = len(results)
        successful = len([r for r in results if r.error is None])
        failed = total_sessions - successful
        
        # 计算所有维度的总体平均分
        all_dimension_scores = {}
        for summary in summaries:
            for key, value in summary.avg_dimension_scores.items():
                if key not in all_dimension_scores:
                    all_dimension_scores[key] = []
                all_dimension_scores[key].append(value)
        
        overall_avg_scores = {
            key: round(sum(values) / len(values), 2) 
            for key, values in all_dimension_scores.items()
        }
        
        # 计算总体首次解决率统计
        overall_fcr_stats = None
        successful_results = [r for r in results if r.error is None]
        if successful_results:
            sessions_with_expected = [r for r in successful_results if r.first_turn_qa_comparison and r.first_turn_qa_comparison.get('expected_answer')]
            sessions_fcr_true = [r for r in successful_results if r.first_turn_qa_comparison and r.first_turn_qa_comparison.get('first_contact_resolution') == True]
            
            total_with_expected = len(sessions_with_expected)
            total_fcr_true = len(sessions_fcr_true)
            
            overall_fcr_stats = {
                "首次解决率": round(total_fcr_true / total_with_expected * 100, 2) if total_with_expected > 0 else 0.0
            }
        
        report = {
            "_report_description": "Vertu Sales Agent 批量测试报告 - 包含多人格对话生成与评估结果",
            "_note": "详细对话数据保存在同目录下的 {persona}_detailed.json 文件中",
            "report_info": {
                "generated_at": datetime.now().isoformat(),
                "total_sessions": total_sessions,
                "successful_evaluations": successful,
                "failed_evaluations": failed,
                "success_rate": round(successful / total_sessions * 100, 2) if total_sessions > 0 else 0,
                "tested_personas": [s.persona for s in summaries],
                "total_duration_seconds": round(sum(r.duration_seconds for r in results), 2)
            },
            "_dimension_score_comments": {
                "anthropomorphism_score": "拟人化体验：语言自然度、人设一致性、温度感",
                "purchase_intent_score": "购买意愿驱动：需求挖掘率、推荐精准度",
                "problem_solving_score": "问题解决能力：首次解决率、意图识别准确率、兜底率",
                "sales_script_score": "销售话术质量：FAB完整度、异议处理、交叉销售、合规性",
                "user_experience_score": "用户体验：CSAT评分、负面反馈触发",
                "traditional_script_score": "传统话术质量：专业名词通俗化解释能力",
                "language_consistency_score": "语言一致性：用户-sales_agent问答语言一致性"
            },
            "overall_first_contact_resolution_stats": overall_fcr_stats,
            "overall_dimension_scores": convert_scores_to_chinese(overall_avg_scores),
            "persona_summaries": [asdict(s) for s in summaries]
        }
        
        return report
    
    def calculate_persona_summary_from_data(self, persona: str, sessions: List[Dict]) -> Optional[PersonaSummary]:
        """从文件数据计算单个人格的汇总统计"""
        if not sessions:
            return None
        
        config = get_persona_config(persona)
        
        # 区分成功和失败的 session
        # 成功的定义：没有 error 且 dimension_scores 不为空（有评估结果）
        successful = [s for s in sessions if not s.get("error") and s.get("dimension_scores")]
        # 失败的定义：有 error 或 dimension_scores 为空（评估失败）
        failed = [s for s in sessions if s.get("error") or not s.get("dimension_scores")]
        
        # 计算平均维度评分（只包含有评估结果的 session）
        avg_scores = {}
        if successful:
            all_scores = [s.get("dimension_scores", {}) for s in successful]
            if all_scores and all_scores[0]:
                score_keys = all_scores[0].keys()
                for key in score_keys:
                    values = [s.get(key, 0) for s in all_scores if key in s and s.get(key, 0) > 0]
                    avg_scores[key] = round(sum(values) / len(values), 2) if values else 0
        
        # 将维度评分转换为中文
        avg_scores_chinese = convert_scores_to_chinese(avg_scores)
        
        # 结束原因分布
        finish_reasons = {}
        for s in sessions:
            reason = s.get("finish_reason", "unknown")
            finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
        
        # 添加评估状态分布
        evaluation_status = {
            "评估成功": len(successful),
            "评估失败": len(failed)
        }
        
        # 平均轮数（只统计成功的 session）
        avg_turns = sum(s.get("total_turns", 0) for s in successful) / len(successful) if successful else 0
        
        # 总耗时
        total_duration = sum(s.get("duration_seconds", 0) for s in sessions)
        
        # 计算首次解决率统计（只统计成功的 session）
        fcr_stats = None
        if successful:
            sessions_with_expected = [s for s in successful if s.get("first_turn_qa_comparison", {}).get("expected_answer")]
            sessions_fcr_true = [s for s in successful if s.get("first_turn_qa_comparison", {}).get("first_contact_resolution") == True]
            
            total_with_expected = len(sessions_with_expected)
            total_fcr_true = len(sessions_fcr_true)
            
            fcr_stats = {
                "总会话数": len(successful),
                "有预期答案的会话": total_with_expected,
                "首次解决成功": total_fcr_true,
                "首次解决率": round(total_fcr_true / total_with_expected * 100, 2) if total_with_expected > 0 else 0.0,
                "无预期答案的会话": len(successful) - total_with_expected
            }
        
        # 计算语言一致性统计（只统计成功的 session）
        lc_stats = None
        if successful:
            sessions_language_match = [s for s in successful if s.get("language_consistency", {}).get("language_match") == True]
            sessions_language_mismatch = [s for s in successful if s.get("language_consistency", {}).get("language_match") == False]
            
            total_match = len(sessions_language_match)
            total_mismatch = len(sessions_language_mismatch)
            lc_score = round(total_match / len(successful) * 100, 2) if successful else 0.0
            
            lc_stats = {
                "总会话数": len(successful),
                "语言一致": total_match,
                "语言不一致": total_mismatch,
                "语言一致性得分": lc_score
            }
        
        # 记录评估失败的 session 信息
        failed_sessions_info = []
        for s in failed:
            failed_sessions_info.append({
                "session_id": s.get("session_id", ""),
                "finish_reason": s.get("finish_reason", "unknown"),
                "total_turns": s.get("total_turns", 0),
                "error": s.get("error") or "评估结果为空"
            })
        
        return PersonaSummary(
            persona=persona,
            description=config.description if config else "",
            total_sessions=len(sessions),
            successful_evaluations=len(successful),
            failed_evaluations=len(failed),
            avg_dimension_scores=avg_scores_chinese,
            finish_reason_distribution=finish_reasons,
            avg_turns=round(avg_turns, 2),
            total_duration=round(total_duration, 2),
            first_contact_resolution_stats=fcr_stats,
            language_consistency_stats=lc_stats,
            evaluation_status=evaluation_status,
            failed_sessions=failed_sessions_info if failed_sessions_info else None
        )


def convert_scores_to_chinese(scores: Dict[str, float]) -> Dict[str, float]:
    """将维度评分字典中的键转换为中文"""
    dimension_names = {
        "anthropomorphism_score": "拟人化体验",
        "purchase_intent_score": "购买意愿驱动",
        "problem_solving_score": "问题解决能力",
        "sales_script_score": "销售话术质量",
        "user_experience_score": "用户体验",
        "traditional_script_score": "传统话术质量",
        "language_consistency_score": "语言一致性"
    }
    return {dimension_names.get(k, k): v for k, v in scores.items()}


def parse_token_usage_from_log(log_file: Path, total_sessions: int = 0) -> Dict[str, Any]:
    """从日志文件中解析 token 使用情况"""
    token_stats = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "api_calls": 0,
        "calls_with_usage": 0,
        "calls_without_usage": 0,
        "avg_input_tokens_per_call": 0,
        "avg_output_tokens_per_call": 0,
        "avg_total_tokens_per_call": 0,
        "avg_input_tokens_per_session": 0,
        "avg_output_tokens_per_session": 0,
        "avg_total_tokens_per_session": 0
    }
    
    if not log_file.exists():
        return token_stats
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                # 匹配 token 使用日志
                match = re.search(r'Token 使用 - 输入: (\d+), 输出: (\d+), 总计: (\d+)', line)
                if match:
                    input_tokens = int(match.group(1))
                    output_tokens = int(match.group(2))
                    total_tokens = int(match.group(3))
                    
                    token_stats["total_input_tokens"] += input_tokens
                    token_stats["total_output_tokens"] += output_tokens
                    token_stats["total_tokens"] += total_tokens
                    token_stats["calls_with_usage"] += 1
                
                # 统计 OpenRouter API 调用次数
                if 'openrouter.ai/api/v1/chat/completions' in line.lower():
                    token_stats["api_calls"] += 1
        
        # 计算每次 API 调用的平均值
        if token_stats["calls_with_usage"] > 0:
            token_stats["avg_input_tokens_per_call"] = round(token_stats["total_input_tokens"] / token_stats["calls_with_usage"], 2)
            token_stats["avg_output_tokens_per_call"] = round(token_stats["total_output_tokens"] / token_stats["calls_with_usage"], 2)
            token_stats["avg_total_tokens_per_call"] = round(token_stats["total_tokens"] / token_stats["calls_with_usage"], 2)
        
        # 计算每个 session 的平均值
        if total_sessions > 0:
            token_stats["avg_input_tokens_per_session"] = round(token_stats["total_input_tokens"] / total_sessions, 2)
            token_stats["avg_output_tokens_per_session"] = round(token_stats["total_output_tokens"] / total_sessions, 2)
            token_stats["avg_total_tokens_per_session"] = round(token_stats["total_tokens"] / total_sessions, 2)
        
        token_stats["calls_without_usage"] = token_stats["api_calls"] - token_stats["calls_with_usage"]
        
    except Exception as e:
        logger.error(f"解析日志文件失败: {e}")
    
    return token_stats


def generate_token_report(output_dir: str, timestamp: str, total_sessions: int = 0):
    """生成 token 使用统计报告"""
    # 查找对应的日志文件
    log_file = Path(f"batch_test_{timestamp}.log")
    
    if not log_file.exists():
        # 尝试查找最新的日志文件
        log_files = sorted(Path('.').glob('batch_test_*.log'), key=lambda x: x.stat().st_mtime, reverse=True)
        if log_files:
            log_file = log_files[0]
        else:
            logger.warning("未找到日志文件，无法生成 token 统计报告")
            return
    
    # 解析 token 使用情况
    token_stats = parse_token_usage_from_log(log_file, total_sessions)
    
    # 构建报告
    report = {
        "report_type": "Token 使用统计报告",
        "generated_at": datetime.now().isoformat(),
        "log_file": str(log_file),
        "total_sessions": total_sessions,
        "summary": {
            "总输入 Token": token_stats["total_input_tokens"],
            "总输出 Token": token_stats["total_output_tokens"],
            "总 Token": token_stats["total_tokens"],
            "API 调用次数": token_stats["api_calls"],
            "有 usage 数据的调用": token_stats["calls_with_usage"],
            "无 usage 数据的调用": token_stats["calls_without_usage"]
        },
        "averages_per_call": {
            "平均输入 Token (每次调用)": token_stats["avg_input_tokens_per_call"],
            "平均输出 Token (每次调用)": token_stats["avg_output_tokens_per_call"],
            "平均总 Token (每次调用)": token_stats["avg_total_tokens_per_call"]
        },
        "averages_per_session": {
            "平均输入 Token (每个 Session)": token_stats["avg_input_tokens_per_session"],
            "平均输出 Token (每个 Session)": token_stats["avg_output_tokens_per_session"],
            "平均总 Token (每个 Session)": token_stats["avg_total_tokens_per_session"]
        },
        "raw_stats": token_stats
    }
    
    # 保存报告
    output_path = Path(output_dir)
    report_file = output_path / "token_usage_report.json"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 打印摘要
    print("\n" + "="*70)
    print("📊 Token 使用统计")
    print("="*70)
    print(f"\n总 Token 使用量:")
    print(f"  输入 Token: {token_stats['total_input_tokens']:,}")
    print(f"  输出 Token: {token_stats['total_output_tokens']:,}")
    print(f"  总 Token: {token_stats['total_tokens']:,}")
    print(f"\nAPI 调用统计:")
    print(f"  总调用次数: {token_stats['api_calls']}")
    print(f"  有 usage 数据: {token_stats['calls_with_usage']}")
    print(f"  无 usage 数据: {token_stats['calls_without_usage']}")
    print(f"\n平均使用量 (每次调用):")
    print(f"  平均输入: {token_stats['avg_input_tokens_per_call']}")
    print(f"  平均输出: {token_stats['avg_output_tokens_per_call']}")
    print(f"  平均总计: {token_stats['avg_total_tokens_per_call']}")
    if total_sessions > 0:
        print(f"\n平均使用量 (每个 Session) - 共 {total_sessions} 个 Sessions:")
        print(f"  平均输入: {token_stats['avg_input_tokens_per_session']}")
        print(f"  平均输出: {token_stats['avg_output_tokens_per_session']}")
        print(f"  平均总计: {token_stats['avg_total_tokens_per_session']}")
    print(f"\n报告已保存: {report_file}")
    print("="*70)


def print_report_summary(report: Dict[str, Any]):
    """打印报告摘要"""
    info = report["report_info"]
    
    print("\n" + "="*70)
    print("📊 批量测试报告摘要")
    print("="*70)
    
    print(f"\n【基本信息】")
    print(f"  生成时间: {info['generated_at']}")
    print(f"  总会话数: {info['total_sessions']}")
    print(f"  成功评估: {info['successful_evaluations']}")
    print(f"  失败评估: {info['failed_evaluations']}")
    print(f"  成功率: {info['success_rate']}%")
    print(f"  总耗时: {info['total_duration_seconds']:.1f}秒")
    
    print(f"\n【总体维度评分】")
    for key, value in report["overall_dimension_scores"].items():
        print(f"  {key}: {value}")
    
    # 显示首次解决率统计
    if report.get("overall_first_contact_resolution_stats"):
        fcr_stats = report["overall_first_contact_resolution_stats"]
        print(f"\n【首次解决率统计】")
        print(f"  首次解决率: {fcr_stats['首次解决率']}%")
    
    print(f"\n【各人格汇总】")
    for summary in report["persona_summaries"]:
        print(f"\n  ▶ {summary['persona']} ({summary['description']})")
        print(f"    会话数: {summary['total_sessions']}")
        print(f"    成功: {summary['successful_evaluations']} / 失败: {summary['failed_evaluations']}")
        print(f"    平均轮数: {summary['avg_turns']}")
        print(f"    总耗时: {summary['total_duration']:.1f}秒")
        print(f"    结束原因分布: {summary['finish_reason_distribution']}")
        if summary['avg_dimension_scores']:
            print(f"    平均维度评分:")
            for k, v in summary['avg_dimension_scores'].items():
                print(f"      - {k}: {v}")
        # 显示该人格的首次解决率统计
        if summary.get('first_contact_resolution_stats'):
            fcr = summary['first_contact_resolution_stats']
            print(f"    首次解决率统计:")
            print(f"      - 有预期答案: {fcr['有预期答案的会话']} / 首次解决成功: {fcr['首次解决成功']}")
            print(f"      - 首次解决率: {fcr['首次解决率']}%")
    
    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(
        description="批量对话生成与评估系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python batch_test_generator.py
  python batch_test_generator.py --sessions-per-persona 50 --max-turns 8
  python batch_test_generator.py --parallel 5 --output-dir my_results
  python batch_test_generator.py --knowledge-pool knowledge_pool.json
        """
    )
    
    parser.add_argument(
        '--sessions-per-persona',
        type=int,
        default=200,
        help='每个人格生成的对话数 (默认: 200)'
    )
    parser.add_argument(
        '--max-turns',
        type=int,
        default=10,
        help='每轮对话最大轮数 (默认: 10)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='输出文件夹路径 (默认: batch_test_results_YYYYMMDD_HHMMSS/)'
    )
    parser.add_argument(
        '--parallel',
        type=int,
        default=3,
        help='并行执行的对话数 (默认: 3)'
    )
    parser.add_argument(
        '--knowledge-pool',
        type=str,
        default=None,
        help='知识池 JSON 文件路径 (可选，用于替代 mock 数据)'
    )
    
    args = parser.parse_args()
    
    # 创建输出文件夹
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.output_dir is None:
        args.output_dir = f"batch_test_results_{timestamp}"
    
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 设置输出文件路径
    output_file = output_path / "full_report.json"
    args.output = str(output_file)
    
    print("="*70)
    print("🚀 批量对话生成与评估系统")
    print("="*70)
    print(f"配置:")
    print(f"  - 每个人格对话数: {args.sessions_per_persona}")
    print(f"  - 最大对话轮数: {args.max_turns}")
    print(f"  - 并行数: {args.parallel}")
    print(f"  - 输出目录: {args.output_dir}")
    print(f"  - 预计总会话数: {args.sessions_per_persona * 5}")
    if args.knowledge_pool:
        print(f"  - 知识池文件: {args.knowledge_pool}")
    print("="*70)
    print()
    
    try:
        # 创建运行器
        runner = BatchTestRunner(
            max_parallel=args.parallel, 
            output_dir=args.output_dir,
            knowledge_pool_file=args.knowledge_pool
        )
        
        # 运行所有测试
        report = asyncio.run(runner.run_all_tests(
            sessions_per_persona=args.sessions_per_persona,
            max_turns=args.max_turns
        ))
        
        # 保存报告
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 打印摘要
        print_report_summary(report)
        
        # 生成 token 使用统计报告
        total_sessions = report.get("report_info", {}).get("total_sessions", 0)
        generate_token_report(args.output_dir, timestamp, total_sessions)
        
        print(f"\n✅ 测试完成！")
        print(f"   输出目录: {args.output_dir}")
        print(f"   - 完整报告: {output_file.name}")
        print(f"   - 各人格详情: {args.output_dir}/*_detailed.json")
        print(f"   - 中间进度: {args.output_dir}/intermediate_progress.json")
        print(f"   - Token 统计: {args.output_dir}/token_usage_report.json")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
