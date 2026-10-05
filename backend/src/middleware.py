"""Middleware ASGI thuần (nhanh hơn BaseHTTPMiddleware): request id, chặn CSRF theo Origin,
giới hạn kích thước body, header bảo mật, access log."""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.config import Settings
from src.logging_config import request_id_var

logger = logging.getLogger("talenthub.access")

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
# Chỉ endpoint tải tài liệu được nhận body lớn (JSON base64); mọi nơi khác giữ giới hạn nhỏ.
UPLOAD_PATH = "/api/v1/admin/documents"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.allowed_origins = frozenset(settings.allowed_origins)
        self.max_body = settings.max_body_bytes
        self.max_upload = settings.max_upload_bytes
        self.hsts = settings.cookie_secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming = headers.get("x-request-id", "")
        request_id = incoming if REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        path: str = scope["path"]
        method: str = scope["method"]
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                out = MutableHeaders(scope=message)
                out["x-request-id"] = request_id
                out["x-content-type-options"] = "nosniff"
                out["x-frame-options"] = "DENY"
                out["referrer-policy"] = "no-referrer"
                out["cross-origin-resource-policy"] = "same-site"
                out["permissions-policy"] = "geolocation=(), microphone=(), camera=()"
                if not path.startswith(DOC_PATHS):
                    out["content-security-policy"] = "default-src 'none'; frame-ancestors 'none'"
                if path.startswith("/api/"):
                    out["cache-control"] = "no-store"
                if self.hsts:
                    out["strict-transport-security"] = "max-age=63072000; includeSubDomains"
            await send(message)

        try:
            rejection = self._reject(method, headers, path)
            if rejection is not None:
                await rejection(scope, receive, send_wrapper)
            else:
                await self.app(scope, receive, send_wrapper)
        finally:
            if path not in ("/healthz", "/readyz"):
                logger.info(
                    "request",
                    extra={
                        "method": method,
                        "path": path,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            request_id_var.reset(token)

    def _reject(self, method: str, headers: Headers, path: str) -> JSONResponse | None:
        if method not in UNSAFE_METHODS:
            return None
        # Chặn CSRF: yêu cầu ghi từ trình duyệt phải đến từ nguồn được phép.
        origin = headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Nguồn yêu cầu không được phép"})
        length = headers.get("content-length")
        limit = self.max_upload if method == "POST" and path == UPLOAD_PATH else self.max_body
        if length is not None and (not length.isdigit() or int(length) > limit):
            return JSONResponse(status_code=413, content={"detail": "Nội dung yêu cầu quá lớn"})
        return None
