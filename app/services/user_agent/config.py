from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UserAgentSettings(BaseSettings):
    """用户智能体服务配置"""
    
    model_config = SettingsConfigDict(
        env_prefix="USER_AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
    
    # 模型配置
    llm_model: str = Field(
        default="kimi-k2-turbo-preview", 
        description="LLM模型名称"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API 密钥",
    )
    openai_base_url: str = Field(
        default="https://api.moonshot.cn/v1", 
        description="OpenAI API 基础 URL"
    )
    
    # 用户知识库配置
    user_kb_url: str = Field(
        default="", 
        description="用户知识库查询 URL"
    )
    user_kb_top_n: int = Field(
        default=5, 
        description="用户知识库查询返回结果数量"
    )
    
    # 用户画像配置
    user_profile_url: str = Field(
        default="", 
        description="用户画像查询 URL"
    )
    
    # 用户行为分析配置
    behavior_analytics_url: str = Field(
        default="", 
        description="用户行为分析 API URL"
    )
    
    # 个性化推荐配置
    recommendation_url: str = Field(
        default="", 
        description="个性化推荐 API URL"
    )
    recommendation_top_n: int = Field(
        default=3,
        description="个性化推荐返回结果数量"
    )

    # 仿真测试配置
    default_max_turns: int = Field(
        default=20,
        description="默认最大对话轮数"
    )
    target_bot_url: str = Field(
        default="http://localhost:8000/api/v1/react/chat",
        description="目标机器人API地址"
    )
    mock_sessions_dir: str = Field(
        default="mock_sessions",
        description="仿真会话数据保存目录"
    )
    question_pool_file: str = Field(
        default="jd_tm_qa_filtered.csv",
        description="问题池文件路径"
    )


user_agent_settings = UserAgentSettings()
