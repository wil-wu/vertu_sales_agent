"""自动扫描和注册服务路由、定时任务"""

import importlib
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI

from app.config import settings

logger = logging.getLogger(__name__)


class RouterScanner:
    """路由扫描器 - 自动发现和注册服务路由"""

    def __init__(self, app: FastAPI):
        """初始化路由扫描器

        Args:
            app: FastAPI 应用实例
        """
        self.app = app
        self.services_path = Path(settings.services_module.replace(".", "/"))

    def scan_and_register(self) -> None:
        """扫描所有服务并注册路由"""
        services = self._scan_services()
        for service in services:
            self._register_service(service)

    def _scan_services(self) -> list[str]:
        """扫描所有服务"""
        services = []

        if not self.services_path.exists():
            logger.warning(f"Services path {self.services_path} does not exist")
            return

        # 遍历 services 目录
        for service in self.services_path.iterdir():
            if not service.is_dir() or service.name.startswith("_"):
                continue

            services.append(service.name)

        return services

    def _register_service(self, service_name: str) -> None:
        """注册单个服务的路由

        Args:
            service_name: 服务名称(目录名)
        """
        try:
            # 动态导入服务的 router 模块
            module_path = f"{settings.services_module}.{service_name}.router"
            module = importlib.import_module(module_path)

            # 获取 router 对象
            if not hasattr(module, "router"):
                logger.warning(
                    f"Service {service_name} does not have a 'router' object"
                )
                return

            router: APIRouter = getattr(module, "router")

            # 注册到应用
            self.app.include_router(router)

            logger.info(
                f"Registered service: {service_name} with prefix: {router.prefix}"
            )

        except ModuleNotFoundError as e:
            logger.error(f"Failed to import service {service_name}: {e}")
        except Exception as e:
            logger.error(
                f"Error registering service {service_name}: {e}", exc_info=True
            )

    def get_registered_routes(self) -> list[dict[str, Any]]:
        """获取所有已注册的路由信息

        Returns:
            路由信息列表
        """
        routes = []
        for route in self.app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append(
                    {
                        "path": route.path,
                        "methods": list(route.methods),
                        "name": route.name,
                    }
                )
        return routes


class JobScanner:
    """任务扫描器 - 扫描每个服务下的 jobs.py 并加载执行（注册定时任务）"""

    def __init__(self) -> None:
        self.services_path = Path(settings.services_module.replace(".", "/"))

    def scan_and_load(self) -> None:
        """扫描所有服务下的 jobs.py 并导入执行"""
        services = self._scan_services()
        for service_name in services:
            self._load_service_jobs(service_name)

    def _scan_services(self) -> list[str]:
        """扫描所有服务目录名"""
        services: list[str] = []
        if not self.services_path.exists():
            logger.warning(
                f"Services path {self.services_path} does not exist, skip job scan"
            )
            return services
        for service in self.services_path.iterdir():
            if not service.is_dir() or service.name.startswith("_"):
                continue
            services.append(service.name)
        return services

    def _load_service_jobs(self, service_name: str) -> None:
        """加载并执行单个服务的 jobs 模块

        导入模块时会执行模块顶层代码，从而将定时任务注册到全局 scheduler。
        """
        jobs_file = self.services_path / service_name / "jobs.py"
        if not jobs_file.exists():
            return
        try:
            module_path = f"{settings.services_module}.{service_name}.jobs"
            importlib.import_module(module_path)
            logger.info(f"Loaded jobs from service: {service_name}")
        except Exception as e:
            logger.error(
                f"Error loading jobs for service {service_name}: {e}",
                exc_info=True,
            )
