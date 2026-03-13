import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import Any, Dict

from .deps import get_user_agent
from .agent import UserAgent
from .schemas import UserSimulationRequest, UserSimulationResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/user",
    tags=["User Agent"],
)

@router.post("/simulation/start", response_model=UserSimulationResponse)
async def start_simulation(
    request: UserSimulationRequest,
    user_agent: UserAgent = Depends(get_user_agent)
) -> UserSimulationResponse:
    """
    启动仿真测试

    启动 Mock 用户与目标机器人的多轮对话仿真测试。
    该接口会创建一个具备特定人格特征的虚拟用户，与目标客服机器人进行多轮对话，
    模拟真实客户咨询场景，用于评估客服机器人的应答能力。

    Args:

        request: 仿真测试请求参数，包含：

            - persona: 用户人格类型

                - business_elite: 商务精英/务实大佬

                - tech_geek: 数码极客/价值博弈型

                - price_comparer: 极致比价/犹豫摇摆型

                - impulse_buyer: 冲动消费/圈层跟风型

                - efficient_buyer: 目标明确/高效采购型

                - brand_loyalist: 品牌死忠/收藏家

                - disappointed_customer: 失望受挫型老客

            - scenario: 测试场景，可选: "咨询"、"售后"、"犹豫"、"竞品对比"、"闲聊"

            - max_turns: 最大对话轮数，默认 20 轮

            - platform: 用户来源平台

                - domestic_jd: 京东平台

                - domestic_tm: 天猫平台

                - overseas: 海外平台（使用英文对话）

            - thread_id: 会话 ID，不传则自动生成

            - knowledge_pool: 知识池数据（可选），格式: {"faq": [...], "price": [...], "graph": [...]}

                传入后，user_agent 在生成问题时会参考这些知识

    Returns:

        包含会话ID、结束原因、对话记录、LLM调用统计和元数据
    """
    try:
        # 启动仿真
        result = await user_agent.start_simulation(
            persona=request.persona,
            scenario=request.scenario,
            max_turns=request.max_turns,
            platform=request.platform,
            knowledge_pool=request.knowledge_pool
        )

        return UserSimulationResponse(
            session_id=result["session_id"],
            finish_reason=result["finish_reason"],
            finish_reason_description=result.get("finish_reason_description"),
            persona=result["persona"],
            prompt=result["prompt"],
            conversation=result["conversation"],
            llm_call_stats=result["llm_call_stats"],
            metadata=result["metadata"]
        )

    except Exception as e:
        logger.error(f"=== [ROUTER] 启动仿真测试失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"仿真测试启动失败: {str(e)}")

@router.get("/simulation/session/{session_id}")
async def get_simulation_result(
    session_id: str
) -> Dict[str, Any]:
    """获取仿真测试结果"""
    try:
        # 在mock_sessions目录中查找会话文件
        sessions_dir = Path("mock_sessions")

        # 查找包含session_id的所有仿真文件
        session_files = list(sessions_dir.glob(f"{session_id}*.json"))

        if not session_files:
            raise HTTPException(status_code=404, detail="未找到指定的会话记录")

        # 按时间排序，获取最新的记录
        latest_file = max(session_files, key=lambda f: f.stat().st_mtime)

        # 读取并返回数据
        with open(latest_file, "r", encoding="utf-8") as f:
            session_data = json.load(f)

        return session_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== [ROUTER] 获取仿真结果失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"获取会话失败: {str(e)}")

@router.get("/simulation/test")
async def test_simulation() -> Dict[str, Any]:
    """测试仿真功能 - 快速验证"""
    try:
        import asyncio
        from pathlib import Path

        # 启动快速仿真测试
        user_agent = UserAgent()

        # 创建一个测试用户代理实例
        test_result = await user_agent.start_simulation(
            persona="professional",
            scenario="测试VERTU手机的电池续航",
            max_turns=3  # 快速测试，只进行3轮
        )

        return {
            "status": "success",
            "session_id": test_result.get("session_id"),
            "finish_reason": test_result.get("finish_reason"),
            "total_turns": test_result.get("metadata", {}).get("total_turns"),
            "message": "仿真测试成功完成"
        }
    except Exception as e:
        logger.error(f"=== [ROUTER] 测试仿真失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"仿真测试失败: {str(e)}")
