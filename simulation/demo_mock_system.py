#!/usr/bin/env python3
"""
Vertu Sales Agent Mock仿真系统演示脚本

运行步骤：
1. 确保后端服务已启动: uv run uvicorn main:app --reload
2. 运行演示: python demo_mock_system.py
3. 按提示输入测试参数
"""

import json
import requests
import sys
from datetime import datetime

def test_quick_simulation():
    """快速仿真测试"""
    print("\n" + "="*60)
    print("快速仿真测试演示")
    print("="*60)

    # 测试参数
    test_params = {
        "persona": "professional",
        "scenario": "测试VERTU手机的售后服务和支持能力",
        "max_turns": 5  # 快速测试，限制轮数
    }

    print(f"测试参数:")
    print(f"- 人格: {test_params['persona']} (专业人士)")
    print(f"- 场景: {test_params['scenario']}")
    print(f"- 最大轮数: {test_params['max_turns']}")

    # 调用API
    url = "http://localhost:8000/api/v1/user/simulation/start"
    try:
        response = requests.post(url, json=test_params)

        if response.status_code == 200:
            result = response.json()
            print(f"\n✓ 仿真测试成功启动!")
            print(f"会话ID: {result['session_id']}")
            print(f"结束原因: {result['finish_reason']}")
            print(f"实际轮数: {result['metadata']['total_turns']}")

            # 查看详情
            session_id = result['session_id']
            details_url = f"http://localhost:8000/api/v1/user/simulation/session/{session_id}"
            details_response = requests.get(details_url)

            if details_response.status_code == 200:
                details = details_response.json()
                print("\n📋 对话详情:")
                conversation = details['conversation']

                for i, msg in enumerate(conversation):
                    role = msg['role']
                    content = msg['content']
                    if role == 'user_agent':
                        print(f"\n👤 用户提问: {content}")
                    else:
                        print(f"🤖 客服回答: {content}")

                print("\n" + "="*60)
                return True
            else:
                print(f"获取详情失败: {details_response.status_code}")
                return False
        else:
            print(f"仿真测试失败: {response.status_code}")
            print(response.text)
            return False

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务，请确保后端服务已启动")
        print("使用命令启动: uv run uvicorn main:app --reload")
        return False

def test_direct_endpoint():
    """直接测试用户Agent端点"""
    print("\n" + "="*60)
    print("直接测试用户Agent端点")
    print("="*60)

    url = "http://localhost:8000/api/v1/user/simulation/test"
    try:
        response = requests.get(url)

        if response.status_code == 200:
            result = response.json()
            print(f"✓ 测试完成!")
            print(f"状态: {result['status']}")
            print(f"会话ID: {result['session_id']}")
            print(f"结束原因: {result['finish_reason']}")
            print(f"对话轮数: {result['total_turns']}")
            return True
        else:
            print(f"测试失败: {response.status_code}")
            print(response.text)
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务")
        return False

def main():
    """主函数"""
    print("\n" + "🤖 Vertu Sales Agent Mock仿真系统演示" + " ".ljust(40))
    print("="*60)
    print("这个演示将向您展示如何使用Mock用户代理测试目标机器人。")
    print("目标机器人地址: http://localhost:8000/api/v1/react/chat")

    try:
        # 步骤1: 快速测试
        print("\n📍 步骤1: 快速仿真测试")
        test_direct_endpoint()

        # 步骤2: 完整仿真
        print("\n📍 步骤2: 完整多轮对话仿真")
        test_quick_simulation()

        print("\n✅ 演示完成!")
        print("\n如需进一步了解，可以：")
        print("1. 查看生成的文件:")
        print("   - mock_questions.json (问题池)")
        print("   - mock_sessions/ (仿真会话记录)")
        print("2. 修改 demo_mock_system.py 中的测试参数")
        print("3. 探索其他人格类型: novice, anxious, confrontational, bilingual")

    except KeyboardInterrupt:
        print("\n\n演示被中断")
    except Exception as e:
        print(f"\n演示出错: {e}")

if __name__ == "__main__":
    main()