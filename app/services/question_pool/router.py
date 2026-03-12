from fastapi import APIRouter

from .schemas import QuestionPoolGenerateRequest, QuestionPoolGenerateResponse
from .service import QuestionPoolService

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

    基于产品名称和渠道参数生成问题池 CSV 文件。
    该接口会根据产品名称从 FAQ、价格 API、图谱等多数据源获取信息，
    生成指定数量的问答对，保存为 CSV 文件供后续仿真测试使用。

    Args:

        request: 包含以下字段：

            - product_name: 产品名称，例如 "VERTU AGENT Q"

            - platform: 目标平台，支持 domestic_jd(京东)、domestic_tm(天猫)、overseas(海外)

            - count: 生成问题数量，范围 10-500，默认 100


    Returns:
    
        包含生成的文件路径、数量统计和数据源统计信息
    """
    service = QuestionPoolService()
    result = await service.generate_pool(
        product_name=request.product_name,
        platform=request.platform,
        count=request.count
    )
    return QuestionPoolGenerateResponse(**result)
