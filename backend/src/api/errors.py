"""Ánh xạ lỗi nghiệp vụ sang phản hồi HTTP theo RFC 9457 (application/problem+json)."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.errors import (
    ConflictError,
    DomainError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidTransitionError,
    NotFoundError,
    PasswordPolicyError,
    PermissionDeniedError,
    RateLimitedError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"

_STATUS: dict[type[DomainError], int] = {
    InvalidCredentialsError: 401,
    InvalidRefreshTokenError: 401,
    PasswordPolicyError: 400,
    RateLimitedError: 429,
    NotFoundError: 404,
    PermissionDeniedError: 403,
    ConflictError: 409,
    InvalidTransitionError: 422,
    ValidationFailedError: 422,
}


def problem(
    request: Request,
    status: int,
    title: str,
    headers: dict[str, str] | None = None,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
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
            **(extra or {}),
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = _STATUS.get(type(exc), 400)
        headers = {"retry-after": str(exc.retry_after_s)} if isinstance(exc, RateLimitedError) else None
        extra: dict[str, object] | None = (
            {"fields": exc.fields} if isinstance(exc, ValidationFailedError) and exc.fields else None
        )
        return problem(request, status, exc.message, headers, extra)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return problem(request, exc.status_code, str(exc.detail), dict(exc.headers) if exc.headers else None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {".".join(str(p) for p in err["loc"][1:]): err["msg"] for err in exc.errors() if len(err["loc"]) > 1}
        return problem(request, 422, "Dữ liệu gửi lên không hợp lệ", None, {"fields": fields})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Không lộ chi tiết nội bộ; request_id giúp tra log.
        logger.exception("unhandled error", extra={"path": request.url.path})
        return problem(request, 500, "Lỗi hệ thống, vui lòng thử lại sau")
