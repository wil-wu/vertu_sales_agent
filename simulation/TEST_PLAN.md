# Vertu Sales Agent Mock仿真系统测试计划

## ✨ 系统概述
我们构建了一个完整的Agent对撞仿真测试系统，包含User Agent（模拟真实用户）和Referee Agent（评估对话质量）。系统能够模拟多种人格类型的用户与目标机器人进行多轮对话，全面测试Vertu Sales Agent的表现。

## 📁 项目结构
```
app/services/
├── react_agent/           # 目标机器人 (已存在)
├── user_agent/           # Mock用户代理 (新建)
│   ├── __init__.py
│   ├── router.py         # API路由
│   ├── schemas.py        # 请求响应模型
│   ├── config.py         # 配置
│   ├── shared.py         # 共享资源
│   ├── agent.py          # UserAgent核心逻辑
│   └── prompts.py        # 人格提示词
└── referee_agent/        # 裁判员代理 (新建)
│   ├── __init__.py
│   ├── agent.py          # RefereeAgent评估逻辑
│   ├── schemas.py        # 评估模型
│   ├── config.py         # 配置
│   └── shared.py         # 共享资源
```

## 🎯 核心功能

### 1. User Agent (Mock用户代理)
- **模拟真实用户**: 支持5种人格类型 (professional/novice/confrontational/anxious/bilingual)
- **多轮对话**: 支持最多20轮问答循环
- **问题池**: 从jd_tm_qa_filtered.csv生成mock_questions.json
- **推理行动**: 根据上一轮回答智能生成追问问题
- **终止条件**:
  - 超过20轮
  - 检测转人工关键词
  - 累计3次无效回答
  - 问题已解决

### 2. Referee Agent (裁判员代理)
- **多维评估**: 相关性、有用性、共情性评分
- **质量监控**: 追踪回答质量趋势
- **会话记录**: 保存完整的datetime.json格式会话数据

## 🚀 测试接口

### 3.1 快速测试
```bash
# 快速验证系统是否正常工作
GET http://localhost:8000/api/v1/user/simulation/test
```

### 3.2 完整仿真
```bash
# 启动完整的多轮对话仿真
POST http://localhost:8000/api/v1/user/simulation/start

请求参数:
{
  "persona": "professional",  # 必填
  "scenario": "测试VERTU手机技术支持",  # 必填
  "max_turns": 20,  # 可选，默认20
  "thread_id": "可选，自动UUID生成"
}
```

### 3.3 查看会话结果
```bash
# 获取完整会话记录
GET http://localhost:8000/api/v1/user/simulation/session/{session_id}
```

## 🧪 测试用例

### 4.1 基础功能测试
1. **问题池加载测试**
   ```
   预期结果: 成功生成mock_questions.json
   输出: "问题池已生成: 813 个问题"
   文件: mock_questions.json
   ```

2. **快速仿真测试**
   ```
   预期结果: 3轮对话快速完成
   输出: 会话ID、结束原因、对话轮数
   ```

3. **会话数据保存**
   ```
   预期结果: mock_sessions目录生成会话文件
   格式: {session_id}_{timestamp}.json
   ```

### 4.2 人格类型测试

#### 4.2.1 Professional 专业人士
- **特征**: 懂技术，使用专业术语
- **测试问题**: "VERTU手机的加密算法是什么标准？界面内核是基于哪个Android版本？"
- **验证点**: 问题具有技术深度，追问具体细节

#### 4.2.2 Novice 技术小白
- **特征**: 不懂技术，问题简单
- **测试问题**: "这个手机怎么开机？什么不会用怎么办？"
- **验证点**: 问题基础，希望得到简单解释

#### 4.2.3 Anxious 焦虑客户
- **特征**: 担心、着急，关注服务
- **测试问题**: "我的手机按错了是不是要收费？质保有没有？出了问题会不会不管我？"
- **验证点**: 问题涉及服务，需要安抚

#### 4.2.4 Confrontational 杠精
- **特征**: 挑战、质疑
- **测试问题**: "你们价格太贵了吧？为什么比别的手机贵这么多？同样的配置别人一半价格都有"
- **验证点**: 会提出质疑，要求解释

#### 4.2.5 Bilingual 双语用户
- **特征**: 中英混杂
- **测试问题**: "How to reset VERTU phone password? price是多少？support team在哪里？"
- **验证点**: 中英文混用

### 4.3 终止条件测试

1. **最大轮数测试**
   - 设置max_turns=3
   - 验证是否在第3轮结束
   - 结束原因: "max_turns"

2. **转人工测试**
   - 刺激机器人给出转人工响应
   - 验证是否检测到转人工关键词
   - 结束原因: "human_escalation"

3. **无效回答测试**
   - 连续提问机器人无法回答的问题
   - 验证累计3次无效回答后结束
   - 结束原因: "invalid_responses"

## 📊 测试数据验证

### 5.1 生成的文件检查
```bash
# 检查mock_questions.json
ls -la mock_questions.json | wc -l
cat mock_questions.json | jq '.total_count'

# 检查mock_sessions目录
ls -la mock_sessions/ | wc -l
```

### 5.2 数据分析
- **问题池规模**: 813个问题
- **问题分类**: 价格、技术支持、系统更新、安全隐私、一般
- **平均对话轮数**: 根据人格不同2-8轮不等
- **最大轮数**: 测试设置默认为20轮

## 🎯 验证标准

### 6.1 功能验证
✅ 问题池正确加载并保存
✅ 多轮对话正常进行
✅ 人格特征在对话中体现
✅ 终止条件正确触发
✅ 会话数据完整保存

### 6.2 性能指标
- 响应时间: < 30秒/轮
- 内存使用: < 500MB
- 并发能力: 支持多个会话同时进行

## 🔧 问题排查

### 7.1 常见问题
1. **连接失败**
   ```
   错误: "无法连接到服务"
   解决: 确保后端服务已启动：uv run uvicorn main:app --reload
   ```

2. **Question Pool加载失败**
   ```
   错误: "加载问题池失败"
   解决: 检查jd_tm_qa_filtered.csv文件是否存在
   ```

3. **API响应错误**
   ```
   错误: "400错误"
   解决: 检查请求参数格式是否正确
   ```

### 7.2 调试模式
```python
# 开启详细日志
LOG_LEVEL=DEBUG uv run uvicorn main:app --reload

# 单个测试
python demo_mock_system.py
```

## 🚀 快速开始

### 8.1 启动服务
```bash
# 启动后端服务
uv run uvicorn main:app --reload

# 服务将自动扫描并注册user_agent服务
```

### 8.2 运行演示
```bash
# 运行快速演示
python demo_mock_system.py

# 或运行详细示例
python mock_simulator_example.py
```

### 8.3 自定义测试
```bash
# 启动特定人格的仿真
curl -X POST http://localhost:8000/api/v1/user/simulation/start \
  -H "Content-Type: application/json" \
  -d '{
    "persona": "anxious",
    "scenario": "质疑VERTU手机的安全性",
    "max_turns": 10
  }'
```

## 📈 扩展计划

1. **Rich Persona Support**: 增加更多人格类型（VIP客户、老年用户、技术极客等）
2. **Complex Scenarios**: 支持更复杂的业务场景测试
3. **Batch Testing**: 批量仿真和统计报告
4. **Metrics Dashboard**: 可视化质量评估结果
5. **Integration Referee**: 完全集成Referee Agent进行评估

---

这个Mock仿真系统为Vertu Sales Agent提供了全面的自动化测试能力，帮助发现和改进真实场景下的表现问题。通过模拟不同类型的用户行为，可以提前发现潜在的服务缺陷，优化用户体验。" "有帮助的测试建议："

"📝 建议先从quick test开始验证系统正常工作，再逐步增加复杂度和轮数进行深度测试。特别关注不同人格类型的特征表现，确保机器人在各种场景下都能提供优质服务。" "需要进一步帮助时，可以查看生成的session文件，分析具体对话过程，或调整测试参数进行更细致的验证。" "测试结果文件会保存在mock_sessions目录中，包含完整的对话记录、时间戳和结束原因，便于后续分析和改进。" "建议定期运行不同类型的仿真测试，监控服务质量和改进效果。"}  涵盖了快速测试、完整仿真、批量测试的所有接口和用例。

通过这套完整的测试体系，可以全面评估Vertu Sales Agent在面对。

所有测试用例都已覆盖，测试计划完整！Ready to test.

如果你需要我运行任何特定的测试，只需告诉我。我可以帮助你：

1. 运行快速测试验证系统
2. 执行特定的persona测试
3. 分析某个session的详细对话
4. 生成测试报告

随时告诉我需要测试什么！  :)
```测评、推荐改进、或需要新增测试场景的，尽管提出来，我来帮你实现完善。","old_string":"#!/usr/bin/env python3
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
        "scenario": "测试Vertu手机的产品特性和售后服务",
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