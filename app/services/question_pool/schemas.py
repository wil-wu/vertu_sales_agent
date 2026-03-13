from typing import List, Optional
from pydantic import BaseModel, Field


class QuestionPoolGenerateRequest(BaseModel):
    """问题池生成请求模型 - 自动遍历所有产品类型"""

    platform: str = Field(
        ...,
        description="渠道参数，可选 domestic_jd、domestic_tm、overseas"
    )
    count: int = Field(
        default=100,
        description="生成的问题数量",
        ge=10,
        le=500
    )


class QuestionPoolGenerateResponse(BaseModel):
    """问题池生成响应模型"""

    file_path: str = Field(..., description="生成的 CSV 文件路径")
    total_generated: int = Field(..., description="实际生成的总数量")
    breakdown: dict = Field(..., description="各渠道生成数量统计")


class QuestionAnswerPair(BaseModel):
    """问答对数据模型"""

    question: str = Field(..., description="问题")
    answer: str = Field(..., description="答案")
    platform: str = Field(..., description="平台来源")
