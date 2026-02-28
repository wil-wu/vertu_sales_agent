"""裁判员代理路由模块 - 提供评估和会话管理API"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from .agent import RefereeAgent
from .deps import get_referee_agent
from .schemas import (
    AssessmentRequest,
    AssessmentResponse,
    BatchAssessmentRequest,
    SessionListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/referee",
    tags=["Referee Agent"],
)


@router.post("/assess", response_model=AssessmentResponse)
async def assess_conversation_turn(
    request: AssessmentRequest,
    referee_agent: RefereeAgent = Depends(get_referee_agent),
) -> AssessmentResponse:
    """评估单轮对话质量"""
    try:
        logger.info(f"=== [REFEREE] 评估会话: {request.session_id}, 第{request.turn_number}轮 ===")

        assessment = await referee_agent.assess_turn(
            turn_number=request.turn_number,
            question=request.question,
            answer=request.answer,
            conversation_history=request.conversation_history,
        )

        return AssessmentResponse(
            session_id=request.session_id,
            turn_number=assessment.turn_number,
            relevance_score=assessment.relevance_score,
            helpfulness_score=assessment.helpfulness_score,
            empathy_score=assessment.empathy_score,
            safety_score=assessment.safety_score,
            overall_score=assessment.overall_score,
            sentiment=assessment.sentiment,
            intent_satisfied=assessment.intent_satisfied,
            should_terminate=assessment.should_terminate,
            termination_reason=assessment.termination_reason,
            feedback=assessment.feedback,
        )

    except Exception as e:
        logger.error(f"=== [REFEREE] 评估失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"评估失败: {str(e)}")


@router.post("/assess/batch")
async def assess_batch_sessions(
    request: BatchAssessmentRequest,
    referee_agent: RefereeAgent = Depends(get_referee_agent),
) -> Dict[str, Any]:
    """批量评估多个会话"""
    try:
        logger.info(f"=== [REFEREE] 批量评估 {len(request.session_ids)} 个会话 ===")

        results = []
        for session_id in request.session_ids:
            session_data = await _load_session_data(session_id)
            if session_data:
                summary = await referee_agent.generate_session_summary(session_data)
                results.append({
                    "session_id": session_id,
                    "summary": summary,
                })

        return {
            "total": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"=== [REFEREE] 批量评估失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"批量评估失败: {str(e)}")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = 10,
    offset: int = 0,
) -> SessionListResponse:
    """列出现有会话记录"""
    try:
        sessions_dir = Path("mock_sessions")
        if not sessions_dir.exists():
            return SessionListResponse(total=0, sessions=[])

        session_files = sorted(
            sessions_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        total = len(session_files)
        paginated_files = session_files[offset : offset + limit]

        sessions = []
        for file in paginated_files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions.append({
                        "session_id": data.get("session_id", file.stem),
                        "persona": data.get("persona", "unknown"),
                        "finish_reason": data.get("finish_reason", "unknown"),
                        "total_turns": data.get("metadata", {}).get("total_turns", 0),
                        "created_at": data.get("metadata", {}).get("start_time", ""),
                    })
            except Exception as e:
                logger.warning(f"读取会话文件失败 {file}: {e}")
                continue

        return SessionListResponse(total=total, sessions=sessions)

    except Exception as e:
        logger.error(f"=== [REFEREE] 列会话失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"列会话失败: {str(e)}")


@router.get("/session/{session_id}/report")
async def get_session_report(session_id: str) -> Dict[str, Any]:
    """获取会话完整评估报告"""
    try:
        session_data = await _load_session_data(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 计算统计数据
        conversation = session_data.get("conversation", [])
        total_turns = len([m for m in conversation if m.get("role") == "user_agent"])

        # 生成报告
        report = {
            "session_id": session_id,
            "persona": session_data.get("persona", "unknown"),
            "finish_reason": session_data.get("finish_reason", "unknown"),
            "prompt": session_data.get("prompt", ""),
            "metadata": session_data.get("metadata", {}),
            "statistics": {
                "total_turns": total_turns,
                "total_messages": len(conversation),
            },
            "conversation": conversation,
        }

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== [REFEREE] 生成报告失败: {e} ===")
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """健康检查"""
    return {"status": "healthy", "service": "referee_agent"}


async def _load_session_data(session_id: str) -> Dict[str, Any] | None:
    """加载会话数据"""
    sessions_dir = Path("mock_sessions")
    if not sessions_dir.exists():
        return None

    # 查找匹配的会话文件
    matching_files = list(sessions_dir.glob(f"{session_id}*.json"))
    if not matching_files:
        return None

    # 返回最新的
    latest_file = max(matching_files, key=lambda f: f.stat().st_mtime)

    with open(latest_file, "r", encoding="utf-8") as f:
        return json.load(f)
