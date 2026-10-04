"""Ánh xạ lỗi nghiệp vụ sang phản hồi HTTP theo RFC 9457 (application/problem+json)."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.errors import (
    DomainError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    PasswordPolicyError,
    RateLimitedError,
)

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"

_STATUS: dict[type[DomainError], int] = {
    InvalidCredentialsError: 401,
    InvalidRefreshTokenError: 401,
    PasswordPolicyError: 400,
    RateLimitedError: 429,
}


def problem(request: Request, status: int, title: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_JSON,
        headers=headers,
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": title,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = _STATUS.get(type(exc), 400)
        headers = {"retry-after": str(exc.retry_after_s)} if isinstance(exc, RateLimitedError) else None
        return problem(request, status, exc.message, headers)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Không lộ chi tiết nội bộ; request_id giúp tra log.
        logger.exception("unhandled error", extra={"path": request.url.path})
        return problem(request, 500, "Lỗi hệ thống, vui lòng thử lại sau")
