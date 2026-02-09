"""请求日志中间件"""

import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录请求信息的中间件"""

    def __init__(
        self,
        app: ASGIApp,
        log_request_body: bool = False,
        log_request_body_length: int = 1024,
        exclude_paths: list[str] | None = None,
    ):
        """
        初始化请求日志中间件

        Args:
            app: ASGI 应用实例
            log_request_body: 是否记录请求体内容
            exclude_paths: 排除记录的路径列表（如 /health, /metrics）
        """
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_request_body_length = log_request_body_length
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并记录日志"""

        # 检查是否应该跳过此路径
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # 记录请求开始时间
        start_time = time.perf_counter()

        # 获取客户端IP
        client_ip = self._get_client_ip(request)

        # 记录请求信息
        request_info = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": client_ip,
            "user_agent": request.headers.get("user-agent", ""),
        }

        # 可选：记录请求体
        body_bytes = b""
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    # 将 body 重新设置到 request，因为已经读取过了
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}

                    request._receive = receive
                    # 安全地处理请求体（支持二进制数据）
                    body_info = self._process_request_body(body_bytes, request)
                    if body_info:
                        request_info["body"] = body_info
            except Exception as e:
                logger.warning(f"Failed to read request body: {e}")

        # 记录请求头（过滤敏感信息）
        headers = dict(request.headers)
        sensitive_headers = ["authorization", "cookie", "x-api-key"]
        filtered_headers = {
            k: "***" if k.lower() in sensitive_headers else v
            for k, v in headers.items()
        }
        request_info["headers"] = filtered_headers

        logger.info(
            f"请求开始: {request.method} {request.url.path} | 客户端IP: {client_ip}"
        )

        # 执行请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 记录异常
            process_time = time.perf_counter() - start_time
            logger.error(
                f"请求异常: {request.method} {request.url.path} | "
                f"客户端IP: {client_ip} | 处理时间: {process_time:.3f}s | 错误: {str(e)}",
                exc_info=True,
            )
            raise

        # 计算处理时间
        process_time = time.perf_counter() - start_time

        # 记录响应信息
        response_info = {
            "status_code": response.status_code,
            "process_time": f"{process_time:.3f}s",
        }

        # 组合日志信息
        log_message = (
            f"请求完成: {request.method} {request.url.path} | "
            f"状态码: {response.status_code} | "
            f"客户端IP: {client_ip} | "
            f"处理时间: {process_time:.3f}s"
        )

        # 根据状态码选择日志级别
        if response.status_code >= 500:
            logger.error(log_message)
        elif response.status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        # 在调试模式下记录详细信息
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"请求详情: {request_info}")
            logger.debug(f"响应详情: {response_info}")

        return response

    def _process_request_body(
        self, body_bytes: bytes, request: Request
    ) -> dict | str | None:
        """
        处理请求体，支持文本和二进制数据

        Args:
            body_bytes: 请求体的字节数据
            request: 请求对象

        Returns:
            如果是文本数据，返回截断后的字符串（如果内容过长）
            如果是二进制数据，返回包含大小和类型信息的字典
        """
        if not body_bytes:
            return None

        content_type = request.headers.get("content-type", "").lower()

        # 只通过 Content-Type 判断是否为二进制内容类型
        binary_types = [
            "image/",
            "video/",
            "audio/",
            "application/octet-stream",
            "application/pdf",
            "application/zip",
            "application/x-",
            "multipart/form-data",  # 文件上传
        ]

        is_binary = any(content_type.startswith(bt) for bt in binary_types)

        if is_binary:
            # 二进制数据：只记录元信息
            return {
                "type": "binary",
                "content_type": content_type or "unknown",
                "size": len(body_bytes),
                "size_human": f"{len(body_bytes) / 1024:.2f} KB"
                if len(body_bytes) > 1024
                else f"{len(body_bytes)} B",
            }
        else:
            # 文本数据：尝试解码并截断
            try:
                # 尝试 UTF-8 解码
                body_str = body_bytes.decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                try:
                    # 尝试其他常见编码
                    body_str = body_bytes.decode("latin-1", errors="ignore")
                except Exception:
                    # 如果解码失败，记录为无法解码的文本
                    return f"<无法解码的文本数据，大小: {len(body_bytes)} 字节>"

            # 限制长度，避免日志过大
            if len(body_str) > self.log_request_body_length:
                return (
                    body_str[: self.log_request_body_length]
                    + f"... (truncated, total: {len(body_str)} chars)"
                )
            return body_str

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """
        获取客户端真实IP地址

        优先从以下头部获取：
        1. X-Forwarded-For (代理服务器)
        2. X-Real-IP (Nginx)
        3. 直接连接的客户端IP
        """
        # 检查 X-Forwarded-For 头
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For 可能包含多个IP，取第一个
            return forwarded_for.split(",")[0].strip()

        # 检查 X-Real-IP 头
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # 使用直接连接的客户端IP
        if request.client:
            return request.client.host

        return "unknown"
