from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ReactAgentSettings(BaseSettings):
    """React Agent 服务配置"""

    model_config = SettingsConfigDict(
        env_prefix="REACT_AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # 模型配置
    llm_model: str = Field(default="kimi-k2-turbo-preview", description="LLM模型")
    openai_api_key: str = Field(
        default="",
        description="OpenAI API 密钥",
    )
    openai_base_url: str = Field(
        default="https://api.moonshot.cn/v1", description="OpenAI API 基础 URL"
    )
    temperature: float = Field(default=0.01, description="温度")

    faq_url: str = Field(
        default="http://192.168.151.84:8888/query", description="FAQ 查询 URL"
    )
    faq_top_n: int = Field(default=5, description="FAQ 查询返回结果数量")

    graph_url: str = Field(
        default="http://192.168.151.84:10001/nl2graph_qa", description="图谱查询 URL"
    )

    wechat_push_url: str = Field(default="", description="微信群通知 URL")
    wechat_push_token: str = Field(default="", description="微信群通知 Token")
    wechat_push_api_key: str = Field(default="", description="微信群通知 API Key")
    wechat_push_group_name: str = Field(default="", description="微信群通知群名称")

    language_detector_model_path: str = Field(default=".huggingface/lid.176.bin", description="语言检测模型路径")
    language_detector_threshold: float = Field(default=0.8, description="语言检测阈值")
    language_detector_min_length: int = Field(default=5, description="语言检测最小文本长度")
    language_detector_max_length: int = Field(default=500, description="语言检测最大文本长度")
    language_detector_exclude: list[str] = Field(default=[
        "IVERTU",
        "VERTU",
        "METAVERTU 2",
        "METAVERTU2",
        "METAVERTU",
        "SIGNATURE 4G",
        "SIGNATURE4G",
        "SIGNATURE S",
        "SIGNATURES",
        "SIGNATURE",
        "AGENT Q",
        "AGENTQ",
        "AGENT IRONFLIP",
        "AGENTIRONFLIP",
        "QUANTUM",
        "AGENT",
    ], description="语言检测排除词/短语列表")

react_agent_settings = ReactAgentSettings()
