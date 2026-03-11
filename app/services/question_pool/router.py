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
    """生成问题池 CSV 文件"""
    service = QuestionPoolService()
    result = await service.generate_pool(
        product_name=request.product_name,
        platform=request.platform,
        count=request.count
    )
    return QuestionPoolGenerateResponse(**result)
