#!/usr/bin/env python3
"""
测试单个 mock 会话文件
使用方法:
    python test_referee_single.py
"""

import json
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.services.referee_agent.agent import referee_agent


async def test_single_session(filepath: str):
    """测试单个会话文件"""
    
    # 1. 加载会话数据
    print(f"📂 加载会话文件：{filepath}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        print(f"✅ 加载成功")
    except Exception as e:
        print(f"❌ 加载失败：{e}")
        return
    
    # 2. 生成评估
    print("\n🔍 开始评估...")
    try:
        summary = await referee_agent.generate_session_summary(session_data)
        print(f"✅ 评估完成")
    except Exception as e:
        print(f"❌ 评估失败：{e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. 构建简化版输出
    detailed = summary.get('detailed_summary', {})
    turn_assessments = summary.get('turn_assessments', [])
    
    simplified_output = {
        "基本信息": {
            "Session ID": summary.get('session_id', 'N/A'),
            "Persona": summary.get('persona', 'N/A'),
            "Finish Reason": summary.get('finish_reason', 'N/A'),
            "Total Turns": summary.get('total_turns', 0)
        },
        "详细指标汇总": {
            "维度评分": detailed.get('dimension_scores', {}),
            "用户拟人化": detailed.get('user_anthropomorphism', {}),
            "Agent 拟人化": detailed.get('agent_anthropomorphism', {}),
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
            f"第 {i} 轮": {
                "Agent 拟人化评分": turn.get('agent_anthropomorphism_score', 0),
                "User 拟人化评分": turn.get('user_anthropomorphism_score', 0),
                "反馈": turn.get('feedback', '')
            }
        }
        simplified_output["每轮评估"].append(turn_data)
    
    # 4. 保存结果到文件
    output_file = f"test_output_{session_data.get('session_id', 'unknown')[:8]}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(simplified_output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 结果已保存到：{output_file}")
    
    # 5. 打印结果预览
    print("\n" + "="*60)
    print("📊 评估结果预览")
    print("="*60)
    print(json.dumps(simplified_output, ensure_ascii=False, indent=2))


def main():
    """主函数"""
    # 默认测试文件
    default_filepath = r"mock_sessions\e4da0053-c55c-4321-bab1-f1a133a16d6f_20260303_165724 - 副本.json"
    
    # 如果命令行提供了参数，使用参数
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = default_filepath
    
    # 检查文件是否存在
    if not Path(filepath).exists():
        print(f"❌ 文件不存在：{filepath}")
        print(f"\n使用方法:")
        print(f"  python test_referee_single.py [文件路径]")
        print(f"\n示例:")
        print(f"  python test_referee_single.py mock_sessions/116102ac-3bfe-48ef-b73c-b39b7b9fcd7a.json")
        return
    
    # 运行异步测试
    asyncio.run(test_single_session(filepath))


if __name__ == "__main__":
    main()
