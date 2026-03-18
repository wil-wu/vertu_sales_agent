#!/usr/bin/env python3
"""
评估 mock_sessions 文件夹下的对话记录
- 使用 referee agent 进行评估
- 支持轮次之间并发
- 单独统计首次问题解决率
- 按 output 格式输出结果
"""

import json
import logging
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).parent / ".env")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.services.referee_agent.agent import RefereeAgent
from app.services.referee_agent.schemas import RefereeRequest


class MockSessionEvaluator:
    """Mock Sessions 评估器"""
    
    def __init__(self, mock_sessions_dir: str = "mock_sessions", output_dir: str = "output", 
                 turn_concurrency: int = 5):
        self.mock_sessions_dir = Path(mock_sessions_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.referee = RefereeAgent()
        self.turn_concurrency = turn_concurrency
        self.turn_semaphore = asyncio.Semaphore(turn_concurrency)
        
    def load_mock_sessions(self) -> List[Dict[str, Any]]:
        """加载所有 mock session 文件"""
        session_files = list(self.mock_sessions_dir.glob("*.json"))
        sessions = []
        
        for file_path in session_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    session = json.load(f)
                    session["_source_file"] = file_path.name
                    sessions.append(session)
            except Exception as e:
                logging.error(f"读取文件 {file_path} 失败: {e}")
        
        logging.info(f"加载了 {len(sessions)} 个 mock session 文件")
        return sessions
    
    def extract_conversation_pairs(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 session 中提取对话对（用户问题 + 客服回复 + 预期答案）"""
        conversation = session.get("conversation", [])
        pairs = []
        
        i = 0
        while i < len(conversation) - 1:
            user_msg = conversation[i]
            bot_msg = conversation[i + 1]
            
            if user_msg.get("role") == "user_agent" and bot_msg.get("role") == "target_bot":
                pairs.append({
                    "turn_number": len(pairs) + 1,
                    "user_message": user_msg.get("content", ""),
                    "expected_answer": user_msg.get("expected_answer", ""),
                    "agent_response": bot_msg.get("content", ""),
                    "timestamp": bot_msg.get("timestamp", "")
                })
                i += 2
            else:
                i += 1
        
        return pairs
    
    async def _evaluate_turn_with_semaphore(self, turn: Dict[str, Any], session_id: str, 
                                             conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        """使用信号量评估单个对话回合"""
        async with self.turn_semaphore:
            return await self._evaluate_turn_internal(turn, session_id, conversation_history)
    
    async def _evaluate_turn_internal(self, turn: Dict[str, Any], session_id: str, 
                                      conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        """评估单个对话回合的内部实现"""
        try:
            request = RefereeRequest(
                session_id=session_id,
                user_message=turn["user_message"],
                agent_response=turn["agent_response"],
                conversation_history=conversation_history,
                expected_answer=turn["expected_answer"],
                is_first_turn=(len(conversation_history) == 0)
            )
            
            response = await self.referee.evaluate_turn(request)
            assessment = response.assessment
            
            # 构建评估结果
            result = {
                "turn_number": turn["turn_number"],
                "user_message": turn["user_message"],
                "agent_response": turn["agent_response"],
                "expected_answer": turn["expected_answer"],
                "detailed_metrics": assessment.detailed_metrics.model_dump() if assessment.detailed_metrics else None,
                "feedback": assessment.feedback,
                "overall_score": assessment.overall_score
            }
            
            return result
            
        except Exception as e:
            logging.error(f"评估回合 {turn['turn_number']} 失败: {e}")
            return {
                "turn_number": turn["turn_number"],
                "user_message": turn["user_message"],
                "agent_response": turn["agent_response"],
                "expected_answer": turn["expected_answer"],
                "detailed_metrics": None,
                "feedback": f"评估失败: {str(e)}",
                "overall_score": 0
            }
    
    async def evaluate_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """评估整个 session（轮次之间并发）"""
        session_id = session.get("session_id", "")
        persona = session.get("persona", "")
        scenario = session.get("scenario", "")
        
        logging.info(f"评估 session: {session_id} ({persona} - {scenario})")
        
        # 提取对话对
        pairs = self.extract_conversation_pairs(session)
        if not pairs:
            logging.warning(f"Session {session_id} 没有有效的对话对")
            return None
        
        # 为每个轮次构建对话历史（基于轮次位置）
        def build_history_for_turn(turn_idx: int) -> List[Dict[str, str]]:
            """为指定轮次构建对话历史"""
            history = []
            for i in range(turn_idx):
                history.append({
                    "role": "user",
                    "content": pairs[i]["user_message"]
                })
                history.append({
                    "role": "assistant",
                    "content": pairs[i]["agent_response"]
                })
            return history
        
        # 并发评估所有轮次
        logging.info(f"  开始并发评估 {len(pairs)} 个轮次 (并发数: {self.turn_concurrency})")
        
        tasks = []
        for idx, pair in enumerate(pairs):
            history = build_history_for_turn(idx)
            task = self._evaluate_turn_with_semaphore(pair, session_id, history)
            tasks.append(task)
        
        # 等待所有评估完成
        assessments = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理可能的异常
        processed_assessments = []
        for idx, result in enumerate(assessments):
            if isinstance(result, Exception):
                logging.error(f"  轮次 {idx+1} 评估异常: {result}")
                processed_assessments.append({
                    "turn_number": idx + 1,
                    "user_message": pairs[idx]["user_message"],
                    "agent_response": pairs[idx]["agent_response"],
                    "expected_answer": pairs[idx]["expected_answer"],
                    "detailed_metrics": None,
                    "feedback": f"评估异常: {str(result)}",
                    "overall_score": 0
                })
            else:
                processed_assessments.append(result)
        
        assessments = processed_assessments
        logging.info(f"  完成评估 {len(assessments)} 个轮次")
        
        # 计算 session 级别的平均分
        average_scores = self._calculate_session_averages(assessments)
        
        # 计算首次问题解决率
        first_contact_resolution_rate = self._calculate_fcr_rate(assessments)
        
        # 计算答案准确率
        answer_accuracy_rate = self._calculate_answer_accuracy_rate(assessments)
        
        # 构建预期答案列表
        expected_answers = [
            {
                "turn": pair["turn_number"],
                "question": pair["user_message"],
                "expected_answer": pair["expected_answer"]
            }
            for pair in pairs
        ]
        
        # 构建输出格式
        session_result = {
            "session_id": session_id,
            "persona": persona,
            "scenario": scenario,
            "finish_reason": session.get("finish_reason", ""),
            "total_turns": len(pairs),
            "average_scores": average_scores,
            "first_contact_resolution_rate": first_contact_resolution_rate,
            "answer_accuracy_rate": answer_accuracy_rate,
            "expected_answers": expected_answers,
            "assessments": assessments,
            "metadata": {
                "source_file": session.get("_source_file", ""),
                "evaluated_at": datetime.now().isoformat()
            }
        }
        
        return session_result
    
    def _calculate_session_averages(self, assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算 session 各指标的平均分"""
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
        
        # 8大维度综合评分
        dimension_scores = {
            "anthropomorphism_score": [],
            "purchase_intent_score": [],
            "problem_solving_score": [],
            "sales_script_score": [],
            "user_experience_score": [],
            "traditional_script_score": [],
            "language_consistency_score": [],
            "answer_accuracy_score": []
        }
        
        for dm in detailed_metrics_all:
            for key in dimension_scores:
                value = dm.get(key)
                if value is not None:
                    dimension_scores[key].append(value)
        
        for key, values in dimension_scores.items():
            if values:
                averages[key] = round(sum(values) / len(values), 4)
        
        return averages
    
    def _calculate_fcr_rate(self, assessments: List[Dict[str, Any]]) -> float:
        """计算首次问题解决率"""
        if not assessments:
            return 0.0
        
        fcr_count = 0
        for a in assessments:
            dm = a.get("detailed_metrics")
            if dm and isinstance(dm, dict):
                ps = dm.get("problem_solving", {})
                if ps.get("first_contact_resolution"):
                    fcr_count += 1
        
        return round(fcr_count / len(assessments) * 100, 2)
    
    def _calculate_answer_accuracy_rate(self, assessments: List[Dict[str, Any]]) -> float:
        """计算答案准确率（session 内所有轮次 accuracy_score 的平均值）"""
        if not assessments:
            return 0.0
        
        accuracy_scores = []
        for a in assessments:
            dm = a.get("detailed_metrics")
            if dm and isinstance(dm, dict):
                aa = dm.get("answer_accuracy", {})
                score = aa.get("accuracy_score")
                if score is not None:
                    accuracy_scores.append(score)
        
        if not accuracy_scores:
            return 0.0
        
        # 计算 session 内所有轮次的平均值
        return round(sum(accuracy_scores) / len(accuracy_scores), 2)
    
    def save_session_result(self, session_result: Dict[str, Any]):
        """保存单个 session 的评估结果"""
        session_id = session_result.get("session_id", "")
        output_file = self.output_dir / f"session_{session_id}.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(session_result, f, ensure_ascii=False, indent=2)
        
        logging.info(f"Session 结果已保存: {output_file}")
    
    def generate_final_report(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成最终报告"""
        total_sessions = len(all_results)
        
        # 收集所有 session 的平均分
        all_session_averages = []
        fcr_rates = []
        accuracy_rates = []
        
        for r in all_results:
            avg_scores = r.get("average_scores", {})
            if avg_scores:
                all_session_averages.append(avg_scores)
            
            fcr = r.get("first_contact_resolution_rate", 0)
            fcr_rates.append(fcr)
            
            acc = r.get("answer_accuracy_rate", 0)
            accuracy_rates.append(acc)
        
        # 计算所有 session 各指标的总平均
        final_averages = {}
        if all_session_averages:
            all_metrics = set()
            for avg in all_session_averages:
                all_metrics.update(avg.keys())
            
            for metric in all_metrics:
                values = [avg.get(metric) for avg in all_session_averages if avg.get(metric) is not None]
                values = [v for v in values if isinstance(v, (int, float))]
                if values:
                    final_averages[metric] = {
                        "average": round(sum(values) / len(values), 4),
                        "min": round(min(values), 4),
                        "max": round(max(values), 4),
                        "count": len(values)
                    }
        
        # 计算平均首次问题解决率
        avg_fcr_rate = round(sum(fcr_rates) / len(fcr_rates), 2) if fcr_rates else 0
        
        # 计算平均答案准确率
        avg_accuracy_rate = round(sum(accuracy_rates) / len(accuracy_rates), 2) if accuracy_rates else 0
        
        # 人格分布
        persona_distribution = {}
        for r in all_results:
            p = r.get("persona", "unknown")
            persona_distribution[p] = persona_distribution.get(p, 0) + 1
        
        # 场景分布
        scenario_distribution = {}
        for r in all_results:
            s = r.get("scenario", "unknown")
            scenario_distribution[s] = scenario_distribution.get(s, 0) + 1
        
        return {
            "total_sessions": total_sessions,
            "timestamp": datetime.now().isoformat(),
            "metric_averages": final_averages,
            "first_contact_resolution_rate": {
                "average": avg_fcr_rate,
                "details": "首次问题解决率：客服在第一轮回复中就完全解决用户问题的比例"
            },
            "answer_accuracy_rate": {
                "average": avg_accuracy_rate,
                "details": "答案准确率：先计算每个session内所有轮次的accuracy_score平均值，再计算所有session的平均"
            },
            "persona_distribution": persona_distribution,
            "scenario_distribution": scenario_distribution,
            "session_files": [f"session_{r.get('session_id')}.json" for r in all_results]
        }
    
    async def run(self):
        """运行评估"""
        # 加载所有 mock sessions
        sessions = self.load_mock_sessions()
        if not sessions:
            logging.error("没有找到 mock session 文件")
            return
        
        # 评估每个 session
        all_results = []
        for i, session in enumerate(sessions):
            logging.info(f"[{i+1}/{len(sessions)}] 评估 session: {session.get('session_id', '')}")
            result = await self.evaluate_session(session)
            if result:
                self.save_session_result(result)
                all_results.append(result)
        
        # 生成最终报告
        if all_results:
            final_report = self.generate_final_report(all_results)
            report_file = self.output_dir / "final_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(final_report, f, ensure_ascii=False, indent=2)
            logging.info(f"最终报告已保存: {report_file}")
            logging.info(f"平均首次问题解决率: {final_report['first_contact_resolution_rate']['average']}%")
            logging.info(f"平均答案准确率: {final_report['answer_accuracy_rate']['average']}%")
        
        logging.info(f"评估完成！共处理 {len(all_results)} 个 sessions")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="评估 mock sessions")
    parser.add_argument("--mock-sessions-dir", default="mock_sessions", help="mock sessions 文件夹路径")
    parser.add_argument("--output-dir", default="output_new", help="输出文件夹路径")
    parser.add_argument("--turn-concurrency", type=int, default=5, help="轮次并发数 (默认: 5)")
    args = parser.parse_args()
    
    evaluator = MockSessionEvaluator(
        mock_sessions_dir=args.mock_sessions_dir,
        output_dir=args.output_dir,
        turn_concurrency=args.turn_concurrency
    )
    await evaluator.run()


if __name__ == "__main__":
    asyncio.run(main())
