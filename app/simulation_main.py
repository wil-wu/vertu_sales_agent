"""仿真模拟测试主流程
- 检索管道:
    - FAQ
    - 价格API
    - Graph
1, 读取输入参数
    - 输入参数包括：
        - 渠道[国内/海外]
        - 待仿真维度(总计32个维度)
    - 检索管道知识 检索结果形成知识子集
2, 获取单个session知识
    - 从知识子集随机组合20份知识 -> 单个session知识池
3, 单个session仿真
    - 用户维度画像(1/7维)
    - 用户意图画像(1/5维)
    - 组合知识池
    - 增量上下文
    *-> 生产用户问题 + 预期答案
    -> 调用AI sales Agent
    -> 保持后续流程一致 
"""


import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import random
import asyncio
from typing import List, Dict, Any
from datetime import datetime
import json

from app.services.user_agent.user_config import get_all_persona_names
from app.services.user_agent.agent import UserAgent
from app.services.referee_agent.agent import RefereeAgent
from app.services.referee_agent.schemas import RefereeRequest
from app.simulation_util import SearchUtil

class SimulationMain:
    # 七个人格类型
    PERSONAS = [
        "business_elite",      # 传统商务型/务实大佬
        "tech_geek",           # 数码极客/价值博弈型
        "price_comparer",      # 极致比价/犹豫摇摆型
        "impulse_buyer",       # 冲动消费/圈层跟风型
        "efficient_buyer",     # 目标明确/高效采购型
        "brand_loyalist",      # 品牌死忠/收藏家
        "disappointed_customer" # 失望受挫型老客
    ]

    # 五个场景类型
    SCENARIOS = [
        "咨询",       # 产品咨询
        "售后",       # 售后服务
        "犹豫",       # 犹豫型购买
        "竞品对比",   # 竞品对比
        "闲聊"        # 闲聊
    ]

    def __init__(self, config: dict, excute_config: dict):
        self.config = config
        self.excute_config = excute_config
        self.search_util = SearchUtil(config=self.config)
        
        self.user_agent = UserAgent()
        self.referee_agent = RefereeAgent()

    def run(self):
        # 根据输入参数 执行检索管道知识检索 检索结果形成知识子集
        knowledge_subset = self.search_knowledge()

        # 根据知识池 用户维度画像(1/7维) 用户意图场景(1/5维) 组合知识池 增量上下文 生产用户问题 + 预期答案 调用AI sales Agent 保持后续流程一致
        session_results = self.generate_session_simulation(knowledge_subset)

        # 保存仿真结果
        self._save_results(session_results)

        return session_results

    def _save_results(self, results: List[Dict[str, Any]]):
        """保存仿真结果到输出目录
        - 每个session生成单独的JSON文件
        - 生成最终报告
        """
        output_dir = Path(self.excute_config.get("output-dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # 为每个session生成单独的文件
        for session_result in results:
            self._save_session_file(session_result, output_dir)

        # 生成最终报告
        final_report = self._generate_final_report(results)
        report_file = output_dir / "final_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(final_report, f, ensure_ascii=False, indent=2)

        print(f"[最终报告已保存] {report_file}")
        print(f"[共生成 {len(results)} 个session文件]")

    def _save_session_file(self, session_result: Dict[str, Any], output_dir: Path):
        """保存单个session的结果到文件"""
        session_id = session_result.get("session_id", "")
        assessments = session_result.get("assessments", [])
        conversation = session_result.get("conversation", [])

        # 计算该session各指标的平均分
        session_averages = self._calculate_session_averages(assessments)

        # 提取所有预期答案
        expected_answers = []
        for msg in conversation:
            if msg.get("role") == "user_agent" and msg.get("expected_answer"):
                expected_answers.append({
                    "turn": len(expected_answers) + 1,
                    "question": msg.get("content", ""),
                    "expected_answer": msg.get("expected_answer", ""),
                    "knowledge_used": msg.get("knowledge_used", [])
                })

        # 构建session文件内容
        session_data = {
            "session_id": session_id,
            "persona": session_result.get("persona"),
            "scenario": session_result.get("scenario"),
            "finish_reason": session_result.get("finish_reason"),
            "total_turns": session_result.get("total_turns"),
            "average_scores": session_averages,
            "expected_answers": expected_answers,
            "assessments": assessments,
            "conversation": conversation,
            "metadata": session_result.get("metadata", {})
        }

        # 保存到文件
        session_file = output_dir / f"session_{session_id}.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

    def _calculate_session_averages(self, assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算session各指标的平均分 - 包含7大维度综合评分和详细子指标"""
        if not assessments:
            return {}

        # 收集详细指标
        detailed_metrics_all = []
        for a in assessments:
            dm = a.get("detailed_metrics")
            if dm and isinstance(dm, dict):
                detailed_metrics_all.append(dm)

        if not detailed_metrics_all:
            return {}

        averages = {}

        # 1. 计算7大维度综合评分
        dimension_scores = {
            "anthropomorphism_score": [],
            "purchase_intent_score": [],
            "problem_solving_score": [],
            "sales_script_score": [],
            "user_experience_score": [],
            "traditional_script_score": [],
            "language_consistency_score": []
        }

        for dm in detailed_metrics_all:
            for key in dimension_scores:
                value = dm.get(key)
                if value is not None:
                    dimension_scores[key].append(value)

        for key, values in dimension_scores.items():
            if values:
                averages[key] = round(sum(values) / len(values), 4)

        # 2. 计算各维度下的详细子指标
        # user_anthropomorphism 子指标
        user_anthro_metrics = ["language_naturalness", "personality_deviation_count", "humor_warmth", "rhythm_pacing"]
        user_anthro_scores = {}
        for metric in user_anthro_metrics:
            values = [dm.get("user_anthropomorphism", {}).get(metric) for dm in detailed_metrics_all if dm.get("user_anthropomorphism")]
            values = [v for v in values if v is not None]
            if values:
                user_anthro_scores[metric] = round(sum(values) / len(values), 4)
        if user_anthro_scores:
            averages["user_anthropomorphism"] = user_anthro_scores

        # agent_anthropomorphism 子指标
        agent_anthro_metrics = ["language_naturalness", "personality_deviation_count", "humor_warmth", "rhythm_pacing"]
        agent_anthro_scores = {}
        for metric in agent_anthro_metrics:
            values = [dm.get("agent_anthropomorphism", {}).get(metric) for dm in detailed_metrics_all if dm.get("agent_anthropomorphism")]
            values = [v for v in values if v is not None]
            if values:
                agent_anthro_scores[metric] = round(sum(values) / len(values), 4)
        if agent_anthro_scores:
            averages["agent_anthropomorphism"] = agent_anthro_scores

        # purchase_intent 子指标
        purchase_metrics = ["needs_discovery_rate", "product_recommendation_accuracy"]
        purchase_scores = {}
        for metric in purchase_metrics:
            values = [dm.get("purchase_intent", {}).get(metric) for dm in detailed_metrics_all if dm.get("purchase_intent")]
            values = [v for v in values if v is not None]
            if values:
                purchase_scores[metric] = round(sum(values) / len(values), 4)
        if purchase_scores:
            averages["purchase_intent"] = purchase_scores

        # problem_solving 子指标
        problem_metrics = ["first_contact_resolution", "intent_recognition_accuracy", "fallback_rate"]
        problem_scores = {}
        for metric in problem_metrics:
            values = [dm.get("problem_solving", {}).get(metric) for dm in detailed_metrics_all if dm.get("problem_solving")]
            values = [v for v in values if v is not None]
            if values:
                problem_scores[metric] = round(sum(values) / len(values), 4)
        if problem_scores:
            averages["problem_solving"] = problem_scores

        # sales_script 子指标
        sales_metrics = ["fab_completeness", "objection_handling_score", "script_compliance", "personalization_rate"]
        sales_scores = {}
        for metric in sales_metrics:
            values = [dm.get("sales_script", {}).get(metric) for dm in detailed_metrics_all if dm.get("sales_script")]
            values = [v for v in values if v is not None]
            if values:
                sales_scores[metric] = round(sum(values) / len(values), 4)
        if sales_scores:
            averages["sales_script"] = sales_scores

        # user_experience 子指标
        ux_metrics = ["csat_score"]
        ux_scores = {}
        for metric in ux_metrics:
            values = [dm.get("user_experience", {}).get(metric) for dm in detailed_metrics_all if dm.get("user_experience")]
            values = [v for v in values if v is not None]
            if values:
                ux_scores[metric] = round(sum(values) / len(values), 4)
        if ux_scores:
            averages["user_experience"] = ux_scores

        # traditional_script 子指标
        traditional_metrics = ["technical_term_simplification"]
        traditional_scores = {}
        for metric in traditional_metrics:
            values = [dm.get("traditional_script", {}).get(metric) for dm in detailed_metrics_all if dm.get("traditional_script")]
            values = [v for v in values if v is not None]
            if values:
                traditional_scores[metric] = round(sum(values) / len(values), 4)
        if traditional_scores:
            averages["traditional_script"] = traditional_scores

        # language_consistency 子指标
        lang_metrics = ["language_match"]
        lang_scores = {}
        for metric in lang_metrics:
            values = [dm.get("language_consistency", {}).get(metric) for dm in detailed_metrics_all if dm.get("language_consistency")]
            values = [v for v in values if v is not None]
            if values:
                lang_scores[metric] = round(sum(values) / len(values), 4)
        if lang_scores:
            averages["language_consistency"] = lang_scores

        return averages

    def _generate_final_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成最终报告，包含所有session各指标的平均分"""
        total_sessions = len(results)

        # 收集所有session的平均分
        all_session_averages = []
        for r in results:
            assessments = r.get("assessments", [])
            session_avg = self._calculate_session_averages(assessments)
            if session_avg:
                all_session_averages.append(session_avg)

        # 计算所有session各指标的总平均
        final_averages = {}
        if all_session_averages:
            all_metrics = set()
            for avg in all_session_averages:
                all_metrics.update(avg.keys())

            for metric in all_metrics:
                values = [avg.get(metric) for avg in all_session_averages if avg.get(metric) is not None]
                if values:
                    final_averages[metric] = {
                        "average": round(sum(values) / len(values), 4),
                        "min": round(min(values), 4),
                        "max": round(max(values), 4),
                        "count": len(values)
                    }

        # 人格分布
        persona_distribution = {}
        for r in results:
            p = r.get("persona", "unknown")
            persona_distribution[p] = persona_distribution.get(p, 0) + 1

        # 场景分布
        scenario_distribution = {}
        for r in results:
            s = r.get("scenario", "unknown")
            scenario_distribution[s] = scenario_distribution.get(s, 0) + 1

        return {
            "total_sessions": total_sessions,
            "timestamp": datetime.now().isoformat(),
            "config": self.config,
            "excute_config": self.excute_config,
            "metric_averages": final_averages,
            "persona_distribution": persona_distribution,
            "scenario_distribution": scenario_distribution,
            "session_files": [f"session_{r.get('session_id')}.json" for r in results]
        }

    # 注意: search_knowledge() 和 generate_session_knowledge_pool() 方法从远程分支合并

    def generate_session_simulation(self, knowledge_subset: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        单个session仿真
        - 从七个人格中随机选择一个
        - 从五个场景中随机选择一个
        - 结合知识池与对话上下文与react_agent进行问答
        - 调用referee进行评估

        Args:
            session_knowledge_pool: 知识池列表，每个元素包含faq/price/graph知识

        Returns:
            仿真结果列表，包含每个session的对话记录和评估结果

        # 保持单session 
        # 随机获取7维人格, 随机获取5维场景, 随机获取20个知识点
        # 组合生成问题 -> 继续调用AI sales Agent -> 形成上下文
        # 组合上下文 一起调用 referee Agent -> 保存到输出目录
        """
        results = []
        session_count = self.config.get("session_count", 1)

        for session_idx in range(session_count):
            knowledge_pool = self.generate_session_knowledge_pool(knowledge_subset)
            # 随机选择人格和场景
            persona = random.choice(self.PERSONAS)
            scenario = random.choice(self.SCENARIOS)

            print(f"[Session {session_idx + 1}] 人格: {persona}, 场景: {scenario}")

            # 运行单个session仿真
            session_result = asyncio.run(
                self._run_single_session(knowledge_pool, persona, scenario)
            )
            results.append(session_result)

        return results

    async def _run_single_session(
        self,
        knowledge_pool: Dict[str, Any],
        persona: str,
        scenario: str
    ) -> Dict[str, Any]:
        """
        运行单个session仿真

        Args:
            knowledge_pool: 单个session的知识池
            persona: 用户人格类型
            scenario: 测试场景

        Returns:
            包含对话记录和评估结果的字典
        """
        # 使用UserAgent启动仿真
        session_data = await self.user_agent.start_simulation(
            persona=persona,
            scenario=f"VERTU手机{scenario}咨询",
            max_turns=self.excute_config.get("max-turns", 10),
            knowledge_pool=knowledge_pool
        )

        # 获取完整对话记录
        conversation = session_data.get("conversation", [])
        session_id = session_data.get("session_id", "")

        # 调用referee进行评估
        assessments = await self._evaluate_conversation(
            session_id,
            conversation
        )

        return {
            "session_id": session_id,
            "persona": persona,
            "scenario": scenario,
            "conversation": conversation,
            "finish_reason": session_data.get("finish_reason"),
            "total_turns": session_data.get("metadata", {}).get("total_turns", 0),
            "assessments": assessments,
            "metadata": {
                "start_time": session_data.get("metadata", {}).get("start_time"),
                "llm_call_stats": session_data.get("llm_call_stats", {}),
                "knowledge_pool_size": {
                    "faq": len(knowledge_pool.get("faq", [])),
                    "price": len(knowledge_pool.get("price", [])),
                    "graph": len(knowledge_pool.get("graph", []))
                }
            }
        }

    async def _evaluate_conversation(
        self,
        session_id: str,
        conversation: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        使用referee对对话进行逐轮评估

        Args:
            session_id: 会话ID
            conversation: 对话记录列表

        Returns:
            每轮的评估结果列表
        """
        assessments = []

        # 构建对话历史
        conversation_history = []

        for turn in conversation:
            if turn.get("role") == "user_agent":
                user_message = turn.get("content", "")
                # 查找对应的agent回复
                agent_response = ""
                for next_turn in conversation[conversation.index(turn) + 1:]:
                    if next_turn.get("role") == "target_bot":
                        agent_response = next_turn.get("content", "")
                        break

                if agent_response:
                    # 构建评估请求
                    request = RefereeRequest(
                        session_id=session_id,
                        user_message=user_message,
                        agent_response=agent_response,
                        conversation_history=conversation_history.copy()
                    )

                    try:
                        # 调用referee评估
                        response = await self.referee_agent.evaluate_turn(request)
                        assessments.append({
                            "turn_id": response.assessment.turn_id,
                            "user_message": user_message,
                            "agent_response": agent_response,
                            "detailed_metrics": response.assessment.detailed_metrics.dict() if response.assessment.detailed_metrics else None,
                            "feedback": response.assessment.feedback
                        })
                    except Exception as e:
                        print(f"[Referee评估失败] {e}")
                        assessments.append({
                            "user_message": user_message,
                            "agent_response": agent_response,
                            "error": str(e)
                        })

                    # 更新对话历史
                    conversation_history.append({
                        "role": "user",
                        "content": user_message
                    })
                    conversation_history.append({
                        "role": "assistant",
                        "content": agent_response
                    })

        return assessments
        pass

    def search_knowledge(self):
        faq_results = self.search_util.search_faq()
        price_results = self.search_util.search_price()
        graph_results = self.search_util.search_graph()
        return {"faq": faq_results, "price": price_results, "graph": graph_results}

    def generate_session_knowledge_pool(self, knowledge_subset):
        """
        根据知识子集 随机组合20份知识 形成知识池, 数据结构与父集一致, 即:
        [{"faq": faq_results', "price": price_results', "graph": graph_results'}, ...]
        - 子集总量<20份知识 即返回的每个元素中对应的key 取到的值长度不超过20 
        - session_count 为知识池中元素的总数, 即返回的列表长度
        todo:
            随机取值优先保障单子集管道取到的值不重复
        """
        knowledge_pool = []
        for _ in range(self.excute_config["session_count"]):
            knowledge_pool.append({
                "faq": random.sample(knowledge_subset["faq"], min(20, len(knowledge_subset["faq"]))),
                "price": random.sample(knowledge_subset["price"], min(20, len(knowledge_subset["price"]))),
                "graph": random.sample(knowledge_subset["graph"], min(20, len(knowledge_subset["graph"]))),
            })
        return knowledge_pool

if __name__ == "__main__":
    # config = {
    #     "channel": "国内",
    #     "dimensions": ["维度1", "维度2", "维度3"],
    #     "session_count": 1, # 3/32 ~= 10% then *8000  + 2000 = 10000 == 8000 单维度  + 2000 交叉维度
    # }
    config = {
        "collection_names": ["domestic_e_commerce","domestic_general","oversea_private","preceding_questions"],
        "query_list": ["屏幕分辨率", "屏幕尺寸", "屏幕类型"],
        "product_names": ["VERTU AGENT Q"],
        "max_path_len": 2,
        "session_count": 1, # 3/32 ~= 10% then *8000  + 2000 = 10000 == 8000 单维度  + 2000 交叉维度
    }
    excute_config = {
        "max-turns": 10, # 每轮对话最大轮数
        "output-dir": "output", # 输出文件夹路径
        "parallel": 10, # 并行执行的对话数
    }
    simulation_main = SimulationMain(config, excute_config)
    simulation_main.run()