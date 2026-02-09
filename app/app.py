"""FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.scanner import RouterScanner
from app.core.middlewares import RequestLoggingMiddleware
from app.core.shared import httpx_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    # 启动时执行
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    logger.info("Application startup completed")

    yield

    # 关闭时执行
    logger.info("Shutting down application")

    await httpx_client.aclose()

    logger.info("Application shutdown completed")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=settings.app_description,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )

    # 配置请求日志中间件
    app.add_middleware(
        RequestLoggingMiddleware,
        log_request_body=settings.debug,  # 仅在调试模式下记录请求体
        log_request_body_length=settings.log_request_body_length,  # 请求体日志长度
        exclude_paths=["/health", "/metrics"],  # 排除健康检查和指标端点
    )

    # 配置 Prometheus 监控
    if settings.enable_metrics:
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/metrics", "/health"],
            inprogress_name="fastapi_inprogress",
            inprogress_labels=True,
        )
        instrumentator.instrument(app).expose(app, endpoint=settings.metrics_path)
        logger.info(f"Metrics enabled at {settings.metrics_path}")

    # 注册所有服务路由
    scanner = RouterScanner(app)
    scanner.scan_and_register()

    # 注册全局路由
    @app.get("/", tags=["Root"])
    async def root():
        """根路径"""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
        }

    @app.get("/health", tags=["Health"])
    async def health_check():
        """健康检查"""
        return {
            "status": "healthy",
            "app_name": settings.app_name,
            "version": settings.app_version,
        }

    @app.get("/routes", tags=["Debug"])
    async def list_routes():
        """列出所有路由(仅调试模式)"""
        if not settings.debug:
            return JSONResponse(
                status_code=403,
                content={"detail": "This endpoint is only available in debug mode"},
            )

        routes = scanner.get_registered_routes()
        return {"total": len(routes), "routes": routes}

    logger.info("FastAPI application initialized")

    return app
