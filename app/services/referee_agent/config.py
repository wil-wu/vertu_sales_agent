from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RefereeAgentSettings(BaseSettings):
    """裁判员智能体服务配置"""
    
    model_config = SettingsConfigDict(
        env_prefix="REFEREE_AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )
    
    # 模型配置
    llm_model: str = Field(
        default="kimi-k2-turbo-preview",
        description="评估LLM模型名称"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API 密钥"
    )
    openai_base_url: str = Field(
        default="https://api.moonshot.cn/v1",
        description="OpenAI API 基础 URL"
    )
    
    # 评估标准阈值
    relevance_threshold: float = Field(
        default=0.7,
        description="相关性阈值，低于此值认为不相关"
    )
    helpfulness_threshold: float = Field(
        default=0.6,
        description="有用性阈值，低于此值认为无用"
    )
    empathy_threshold: float = Field(
        default=0.5,
        description="同理心阈值，低于此值认为缺乏同理心"
    )
    
    # 终止条件配置
    max_turns: int = Field(
        default=10,
        description="最大对话回合数"
    )
    low_score_threshold: float = Field(
        default=0.4,
        description="低分阈值，连续低分该值将考虑终止"
    )
    consecutive_low_scores: int = Field(
        default=3,
        description="连续低分次数阈值"
    )
    
    # 会话数据配置
    session_data_dir: str = Field(
        default="./data/referee_sessions",
        description="会话数据保存目录"
    )
    save_session_data: bool = Field(
        default=True,
        description="是否保存会话数据"
    )
    
    # 评估权重配置
    relevance_weight: float = Field(
        default=0.4,
        description="相关性权重"
    )
    helpfulness_weight: float = Field(
        default=0.4,
        description="有用性权重"
    )
    empathy_weight: float = Field(
        default=0.2,
        description="同理心权重"
    )


referee_agent_settings = RefereeAgentSettings()
