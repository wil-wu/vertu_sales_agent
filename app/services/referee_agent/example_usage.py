"""
Example usage of RefereeAgent
"""
import asyncio
from .agent import referee_agent
from .schemas import RefereeRequest


async def example_usage():
    """示例用法"""
    # 创建一个请求
    request = RefereeRequest(
        session_id="test_session_001",
        user_message="我想重置我的密码，但是我没有手机号了。",
        agent_response="很抱歉，目前重置密码需要绑定手机号。请您联系客服热线400-123-4567进行人工处理。",
        conversation_history=[
            {"user": "我想重置密码", "assistant": "好的，密码重置需要验证您的手机号，请输入收到的验证码。"},
            {"user": "我没有手机号了", "assistant": "很抱歉，目前重置密码需要绑定手机号。请您联系客服热线400-123-4567进行人工处理。"}
        ]
    )
    
    # 评估对话
    response = await referee_agent.evaluate_turn(request)
    
    # 输出结果
    print("评估结果:")
    print(f"相关性评分: {response.assessment.relevance}")
    print(f"有用性评分: {response.assessment.helpfulness}")
    print(f"同理心评分: {response.assessment.empathy}")
    print(f"综合评分: {response.assessment.overall_score}")
    print(f"评估反馈: {response.assessment.feedback}")
    print(f"是否终止: {response.should_terminate}")
    if response.termination_reason:
        print(f"终止原因: {response.termination_reason}")


if __name__ == "__main__":
    asyncio.run(example_usage())
