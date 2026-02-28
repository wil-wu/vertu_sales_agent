#!/usr/bin/env python3
"""
Mock仿真测试系统使用示例

这个脚本演示了如何使用User Agent模拟真实用户行为，
与目标机器人（react_agent）进行多轮对话仿真测试。
"""

import asyncio
import json
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API端点配置
USER_AGENT_API = "http://localhost:8000/api/v1/user"

def print_conversation(conversation_data: dict):
    """打印对话记录"""
    print("\n" + "="*60)
    print(f"会话ID: {conversation_data['session_id']}")
    print(f"人格类型: {conversation_data['persona']}")
    print(f"结束原因: {conversation_data['finish_reason']}")
    print(f"对话轮数: {conversation_data['metadata']['total_turns']}")
    print("="*60)
    print("对话内容:")

    for turn in conversation_data['conversation']:
        role = turn['role']
        timestamp = turn['timestamp'][:19].replace('T', ' ')
        content = turn['content']

        if role == 'user_agent':
            print(f"\n[用户 - {timestamp}]")
        else:
            print(f"\n[客服 - {timestamp}]")
        print(content)

    print("\n" + "="*60)

async def test_single_simulation(persona: str):
    """测试单个仿真"""
    logger.info(f"开始测试 {persona} 人格仿真...")

    import httpx
    async with httpx.AsyncClient() as client:
        # 启动仿真
        start_payload = {
            "persona": persona,
            "scenario": f"测试Vertu手机的产品特性和售后服务 ({persona})",
            "max_turns": 5  # 限制轮数用于演示
        }

        print("\n开始仿真请求:")
        print(f"人格: {persona}")
        print(f"场景: {start_payload['scenario']}")
        print(f"最大轮数: {start_payload['max_turns']}")

        response = await client.post(
            f"{USER_AGENT_API}/simulation/start",
            json=start_payload
        )

        if response.status_code == 200:
            result = response.json()
            logger.info("仿真启动成功")
            print(f"会话ID: {result['session_id']}")
            print(f"结束原因: {result['finish_reason']}")
            print(f"对话轮数: {result['metadata']['total_turns']}")

            return result
        else:
            logger.error(f"仿真启动失败: {response.status_code} - {response.text}")
            return None

async def show_conversation_details(session_id: str):
    """显示完整对话"""
    logger.info(f"获取会话详情: {session_id}")

    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{USER_AGENT_API}/simulation/session/{session_id}"
        )

        if response.status_code == 200:
            data = response.json()
            print_conversation(data)
        else:
            logger.error(f"获取会话失败: {response.status_code}")

async def run_batch_simulation():
    """批量仿真测试"""
    logger.info("开始批量仿真测试...")

    personas = ["professional", "novice", "anxious", "bilingual", "confrontational"]
    results = []

    for persona in personas:
        print(f"\n{'='*80}")
        print(f"测试人格: {persona}")
        print(f"{'='*80}")

        result = await test_single_simulation(persona)
        if result:
            results.append({
                "persona": persona,
                "session_id": result['session_id'],
                "finish_reason": result['finish_reason'],
                "total_turns": result['metadata']['total_turns']
            })

    # 生成测试报告
    print("\n\n★ ★ ★ 批量仿真测试结果汇总 ★ ★ ★")
    print("-"*80)

    summary = {
        "test_time": datetime.now().isoformat(),
        "total_simulations": len(results),
        "persona_stats": {
            p: {
                "count": len([r for r in results if r['persona'] == p]),
                "avg_turns": sum([r['total_turns'] for r in results if r['persona'] == p]) / len([r for r in results if r['persona'] == p]) if [r for r in results if r['persona'] == p] else 0
            }
            for p in personas
        },
        "termination_reasons": {
            reason: len([r for r in results if r['finish_reason'] == reason])
            for reason in set(r['finish_reason'] for r in results)
        }
    }

    print(f"总仿真数: {summary['total_simulations']}")
    print("\n各人格表现:")
    for persona in summary['persona_stats']:
        stats = summary['persona_stats'][persona]
        print(f"  {persona}: {stats['count']}次, 平均{stats['avg_turns']:.1f}轮")

    print("\n结束原因统计:")
    for reason, count in summary['termination_reasons'].items():
        print(f"  {reason}: {count}次")

    # 保存测试报告
    report_file = f"mock_simulation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "summary": summary,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n测试报告已保存到: {report_file}")

async def main():
    """主函数"""
    print("欢迎使用 Vertu Sales Agent 仿真测试系统示例")
    print("="*80)

    # 1. 快速测试单个仿真
    print("\n1. 快速仿真测试")
    result = await test_single_simulation("professional")

    if result:
        # 2. 查看完整对话
        print("\n\n2. 查看完整对话")
        await show_conversation_details(result['session_id'])

    # 3. 批量仿真测试
    print("\n\n3. 批量仿真测试")
    choice = input("是否运行完整批量测试？(会消耗较多时间) [y/N]: ")

    if choice.lower() == 'y':
        await run_batch_simulation()

    print("\n✓ 仿真测试示例完成")

if __name__ == "__main__":
    asyncio.run(main())