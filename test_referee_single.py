#!/usr/bin/env python3
"""
端到端测试脚本 - 直接连接三个 Agent 进行测试

运行方法:
    python test_referee_single.py
    
可选参数:
    --persona: 用户人格类型 (默认: professional)
    --scenario: 测试场景描述 (默认: "测试VERTU手机的产品特性和售后服务")
    --max-turns: 最大对话轮数 (默认: 10)
    --file: 使用已有的会话文件进行评估，跳过对话生成

示例:
    python test_referee_single.py --persona confrontational --max-turns 5
    python test_referee_single.py --file mock_sessions/xxx.json
"""

import json
import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入三个 Agent
from app.services.referee_agent.agent import referee_agent
from app.services.user_agent.agent import UserAgent
from app.services.user_agent.shared import chat_model as user_chat_model
from app.services.react_agent.agent import ReActAgent
from app.services.react_agent.shared import chat_model as react_chat_model
from app.services.react_agent.tools import TOOLS
from app.services.react_agent.prompts import REACT_AGENT_SYSTEM_PROMPT


class DirectReactAgentAdapter:
    """
    ReactAgent 适配器 - 提供与 HTTP API 相同的接口
    使 UserAgent 可以直接调用本地的 ReActAgent
    """
    
    def __init__(self, agent: ReActAgent):
        self.agent = agent
        
    async def chat(self, message: str, thread_id: str) -> dict:
        """模拟 API 响应格式"""
        try:
            response = await self.agent.arun(message, thread_id)
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
    """
    直接连接版本的 UserAgent
    绕过 HTTP API，直接调用本地的 ReActAgent
    """
    
    def __init__(self, chat_model=None, system_prompt: str = "", react_agent=None):
        super().__init__(chat_model, system_prompt, "")
        self.direct_react_agent = react_agent
        
    async def _call_target_bot(self, client, question: str, thread_id: str, user_id: str = "simulation_user", platform: str = "simulation") -> any:
        """重写方法：直接调用 ReActAgent 而不是 HTTP API"""
        print(f"  🤖 [ReAct Agent] 正在处理...")
        
        try:
            response = await self.direct_react_agent.chat(question, thread_id)
            
            # 打印简要回复预览
            answer_preview = response.get("message", "")[:100]
            if len(response.get("message", "")) > 100:
                answer_preview += "..."
            print(f"     回复: {answer_preview}")
            
            return response
            
        except Exception as e:
            print(f"  ❌ [ReAct Agent] 调用失败: {e}")
            raise


def create_react_agent() -> DirectReactAgentAdapter:
    """创建并初始化 ReAct Agent"""
    print("🔧 [1/4] 初始化 ReAct Agent (客服机器人)...")
    
    # 创建 ReActAgent 实例
    agent = ReActAgent(
        chat_model=react_chat_model,
        tools=TOOLS,
        system_prompt=REACT_AGENT_SYSTEM_PROMPT
    )
    
    # 包装为适配器
    adapter = DirectReactAgentAdapter(agent)
    
    print("   ✅ ReAct Agent 初始化完成")
    return adapter


def create_user_agent(react_agent_adapter: DirectReactAgentAdapter) -> DirectUserAgent:
    """创建并初始化 User Agent"""
    print("🔧 [2/4] 初始化 User Agent (模拟用户)...")
    
    # 创建直接连接版本的 UserAgent
    agent = DirectUserAgent(
        chat_model=user_chat_model,
        system_prompt="你是一个模拟真实用户的智能体，用于测试客服机器人。",
        react_agent=react_agent_adapter
    )
    
    print("   ✅ User Agent 初始化完成")
    return agent


def create_referee_agent():
    """创建并初始化 Referee Agent"""
    print("🔧 [3/4] 初始化 Referee Agent (裁判评估)...")
    print("   ✅ Referee Agent 初始化完成")
    return referee_agent


async def run_simulation(user_agent: DirectUserAgent, persona: str, scenario: str, max_turns: int) -> dict:
    """运行仿真测试，生成会话数据"""
    print(f"\n🎭 [4/4] 启动仿真测试")
    print(f"   人格类型: {persona}")
    print(f"   测试场景: {scenario}")
    print(f"   最大轮数: {max_turns}")
    print("-" * 60)
    
    # 运行仿真
    session_data = await user_agent.start_simulation(
        persona=persona,
        scenario=scenario,
        max_turns=max_turns
    )
    
    print("-" * 60)
    print(f"✅ 仿真完成!")
    print(f"   会话ID: {session_data['session_id']}")
    print(f"   结束原因: {session_data['finish_reason']}")
    print(f"   实际轮数: {session_data['metadata']['total_turns']}")
    
    return session_data


async def evaluate_session(referee, session_data: dict) -> dict:
    """使用 Referee Agent 评估会话"""
    print("\n🔍 开始评估会话...")
    
    try:
        summary = await referee.generate_session_summary(session_data)
        print("✅ 评估完成")
        return summary
    except Exception as e:
        print(f"❌ 评估失败: {e}")
        import traceback
        traceback.print_exc()
        raise


def build_output(summary: dict, session_data: dict) -> dict:
    """构建简化版输出"""
    detailed = summary.get('detailed_summary', {})
    turn_assessments = summary.get('turn_assessments', [])
    
    output = {
        "测试信息": {
            "测试时间": datetime.now().isoformat(),
            "会话ID": summary.get('session_id', 'N/A'),
            "人格类型": summary.get('persona', 'N/A'),
            "结束原因": summary.get('finish_reason', 'N/A'),
            "总轮数": summary.get('total_turns', 0)
        },
        "维度评分汇总": detailed.get('dimension_scores', {}),
        "详细指标": {
            "用户拟人化": detailed.get('user_anthropomorphism', {}),
            "Agent拟人化": detailed.get('agent_anthropomorphism', {}),
            "购买意愿": detailed.get('purchase_intent', {}),
            "问题解决": detailed.get('problem_solving', {}),
            "销售话术": detailed.get('sales_script', {}),
            "用户体验": detailed.get('user_experience', {})
        },
        "每轮评估": []
    }
    
    # 添加每轮评估
    for i, turn in enumerate(turn_assessments, 1):
        turn_data = {
            f"第{i}轮": {
                "Agent拟人化评分": turn.get('agent_anthropomorphism_score', 0),
                "User拟人化评分": turn.get('user_anthropomorphism_score', 0),
                "反馈": turn.get('feedback', '')
            }
        }
        
        # 为首轮对话添加 first_contact_resolution 和问答对比
        if i == 1 and turn.get('qa_comparison'):
            turn_data[f"第{i}轮"]["9. first_contact_resolution (首次解决) - 仅评估首轮对话"] = {
                "是否解决": turn.get('first_contact_resolution', False),
                "问答对比": {
                    "用户问题": turn['qa_comparison'].get('question', ''),
                    "预期回答": turn['qa_comparison'].get('expected_answer', ''),
                    "实际回答": turn['qa_comparison'].get('actual_answer', '')
                }
            }
        
        output["每轮评估"].append(turn_data)
    
    return output


def save_results(output: dict, session_id: str):
    """保存测试结果"""
    output_file = f"test_output_{session_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 结果已保存到: {output_file}")
    return output_file


def print_results(output: dict):
    """打印结果预览"""
    print("\n" + "=" * 60)
    print("📊 评估结果预览")
    print("=" * 60)
    print(json.dumps(output, ensure_ascii=False, indent=2))


async def test_with_existing_file(filepath: str):
    """使用已有会话文件进行测试"""
    print(f"📂 加载已有会话文件: {filepath}")
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        print("✅ 加载成功")
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        sys.exit(1)
    
    # 只需要初始化 Referee Agent
    referee = create_referee_agent()
    
    # 评估会话
    summary = await evaluate_session(referee, session_data)
    
    # 构建输出
    output = build_output(summary, session_data)
    
    # 保存结果
    session_id = session_data.get('session_id', 'unknown')
    save_results(output, session_id)
    
    # 打印结果
    print_results(output)


async def run_full_test(args):
    """运行完整测试（创建新会话并评估）"""
    
    # 1. 创建三个 Agent
    react_adapter = create_react_agent()
    user_agent = create_user_agent(react_adapter)
    referee = create_referee_agent()
    
    print()
    
    # 2. 运行仿真测试
    session_data = await run_simulation(
        user_agent=user_agent,
        persona=args.persona,
        scenario=args.scenario,
        max_turns=args.max_turns
    )
    
    # 3. 评估会话
    summary = await evaluate_session(referee, session_data)
    
    # 4. 构建输出
    output = build_output(summary, session_data)
    
    # 5. 保存结果
    session_id = session_data.get('session_id', 'unknown')
    output_file = save_results(output, session_id)
    
    # 6. 打印结果
    print_results(output)
    
    print(f"\n✅ 完整测试流程结束!")
    print(f"   会话数据: mock_sessions/{session_id}_*.json")
    print(f"   评估结果: {output_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="端到端测试 - 直接连接三个 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_referee_single.py
  python test_referee_single.py --persona confrontational --max-turns 5
  python test_referee_single.py --file mock_sessions/xxx.json
        """
    )
    
    parser.add_argument(
        '--persona', 
        type=str, 
        default='professional',
        choices=['professional', 'novice', 'anxious', 'confrontational', 'bilingual'],
        help='用户人格类型 (默认: professional)'
    )
    parser.add_argument(
        '--scenario', 
        type=str, 
        default='测试VERTU手机的产品特性和售后服务',
        help='测试场景描述'
    )
    parser.add_argument(
        '--max-turns', 
        type=int, 
        default=10,
        help='最大对话轮数 (默认: 10)'
    )
    parser.add_argument(
        '--file', 
        type=str, 
        default=None,
        help='使用已有会话文件进行评估，跳过对话生成'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 Vertu Sales Agent - 端到端测试")
    print("=" * 60)
    print()
    print("连接的三个 Agent:")
    print("   1. User Agent    - 模拟真实用户")
    print("   2. ReAct Agent   - 客服机器人(被测系统)")
    print("   3. Referee Agent - 裁判评估系统")
    print()
    
    try:
        if args.file:
            # 使用已有文件
            asyncio.run(test_with_existing_file(args.file))
        else:
            # 运行完整测试
            asyncio.run(run_full_test(args))
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
