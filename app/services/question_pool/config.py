from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QuestionPoolSettings(BaseSettings):
    """问题池生成服务配置"""

    model_config = SettingsConfigDict(
        env_prefix="QUESTION_POOL_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # FAQ API 配置
    faq_url: str = Field(
        default="http://192.168.151.84:8888/query",
        description="FAQ 查询 API URL"
    )

    # 价格 API 配置
    price_url: str = Field(
        default="http://192.168.151.84:8030/api/v1/semantic/product/search",
        description="价格查询 API URL"
    )

    # 图谱 API 配置
    graph_url: str = Field(
        default="http://192.168.151.84:10001/direct_cypher_query",
        description="知识图谱查询 API URL"
    )

    # LLM 配置
    llm_model: str = Field(
        default="kimi-k2-turbo-preview",
        description="LLM 模型名称"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API 密钥"
    )
    openai_base_url: str = Field(
        default="https://api.moonshot.cn/v1",
        description="OpenAI API 基础 URL"
    )

    # 输出配置
    output_dir: str = Field(
        default="mock_sessions",
        description="CSV 文件输出目录"
    )


# 渠道映射配置
PLATFORM_CONFIG = {
    "domestic_jd": {
        "faq_collection": "domestic",
        "price_index": "jd_product",
        "platform_label": "京东"
    },
    "domestic_tm": {
        "faq_collection": "domestic",
        "price_index": "tm_product",
        "platform_label": "天猫"
    },
    "overseas": {
        "faq_collection": "overseas",
        "price_index": "overseas_product",
        "platform_label": "海外"
    }
}

question_pool_settings = QuestionPoolSettings()
