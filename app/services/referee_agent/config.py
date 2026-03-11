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
        default="openai/gpt-5-nano",
        description="评估LLM模型名称"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API 密钥"
    )
    openai_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenAI API 基础 URL"
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
    


referee_agent_settings = RefereeAgentSettings()
