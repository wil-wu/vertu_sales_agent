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
    """启动仿真测试 - Mock用户与目标机器人的多轮对话"""
    try:
        # 启动仿真
        result = await user_agent.start_simulation(
            persona=request.persona,
            scenario=request.scenario,
            max_turns=request.max_turns
        )

        return UserSimulationResponse(
            session_id=result["session_id"],
            finish_reason=result["finish_reason"],
            persona=result["persona"],
            prompt=result["prompt"],
            conversation=result["conversation"],
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
