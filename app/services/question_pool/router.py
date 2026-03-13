import logging
import traceback

from fastapi import APIRouter, HTTPException

from .schemas import QuestionPoolGenerateRequest, QuestionPoolGenerateResponse
from .service import QuestionPoolService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/question-pool",
    tags=["Question Pool"],
)


@router.post("/generate", response_model=QuestionPoolGenerateResponse)
async def generate_question_pool(
    request: QuestionPoolGenerateRequest,
) -> QuestionPoolGenerateResponse:
    """
    生成问题池

    从 FAQ、价格 API、图谱等多数据源获取与屏幕相关的信息，
    使用屏幕相关关键词（屏幕、分辨率、AMOLED、刷新率等）查询数据，
    生成指定数量的屏幕相关问答对，保存为 CSV 文件供后续仿真测试使用。

    Args:

        request: 包含以下字段：

            - platform: 目标平台，支持 domestic_jd(京东)、domestic_tm(天猫)、overseas(海外)

            - count: 生成问题数量，范围 10-500，默认 100


    Returns:

        包含生成的文件路径、数量统计和各渠道统计信息
    """
    try:
        service = QuestionPoolService()
        result = await service.generate_pool(
            platform=request.platform,
            count=request.count
        )
        return QuestionPoolGenerateResponse(**result)
    except Exception as e:
        error_msg = f"生成问题池失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=str(e))
