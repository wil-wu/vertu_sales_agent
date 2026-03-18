"""全局配置管理"""

import secrets
from pathlib import Path
from logging.config import dictConfig

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GlobalSettings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # 应用信息
    app_name: str = Field(default="Vertu Sales Agent", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    app_description: str = Field(default="Vertu Sales Agent API", description="应用描述")

    debug: bool = Field(default=True, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="logs/app.log", description="日志文件")
    log_request_body_length: int = Field(default=1024, description="请求体日志长度")

    # 服务器配置
    host: str = Field(default="0.0.0.0", description="API 主机")
    port: int = Field(default=8000, description="API 端口")
    workers: int = Field(default=1, description="Worker 数量")

    # 安全配置
    secret_key: str = Field(default=secrets.token_hex(32), description="密钥")

    # CORS 配置
    cors_origins: list[str] = Field(default=["*"], description="允许的跨域来源")
    cors_credentials: bool = Field(default=True, description="是否允许携带凭证")
    cors_methods: list[str] = Field(default=["*"], description="允许的 HTTP 方法")
    cors_headers: list[str] = Field(default=["*"], description="允许的 HTTP 头")

    # 监控配置
    enable_metrics: bool = Field(default=True, description="是否启用指标监控")
    metrics_path: str = Field(default="/metrics", description="指标路径")

    # PostgreSQL 连接配置
    postgres_host: str = Field(default="localhost", description="PostgreSQL 主机")
    postgres_port: int = Field(default=5432, description="PostgreSQL 端口")
    postgres_user: str = Field(default="postgres", description="PostgreSQL 用户")
    postgres_password: str = Field(default="", description="PostgreSQL 密码")
    postgres_db: str = Field(default="postgres", description="PostgreSQL 数据库名")
    postgres_sslmode: str = Field(default="disable", description="PostgreSQL SSL 模式")
    postgres_advisory_lock_key: int = Field(default=0x56_52_55_53, description="PostgreSQL 分布式锁")

    @property
    def postgres_url(self) -> str:
        """PostgreSQL 连接 URL，供全局连接池使用。"""
        auth = f"{self.postgres_user}:{self.postgres_password}" if self.postgres_password else self.postgres_user
        return f"postgres://{auth}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}?sslmode={self.postgres_sslmode}"

    # 服务模块
    services_module: str = Field(default="app.services", description="服务模块")


settings = GlobalSettings()

if not Path(settings.log_file).parent.exists():
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)

dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.log_level,
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": settings.log_level,
                "formatter": "detailed",
                "filename": settings.log_file,
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["console", "file"] if not settings.debug else ["console"],
        },
        "loggers": {
            "uvicorn": {
                "level": settings.log_level,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "fastapi": {
                "level": settings.log_level,
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }
)
