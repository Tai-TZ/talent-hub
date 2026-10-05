from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.admin import router as admin_router
from src.api.applications import router as applications_router
from src.api.audit import router as audit_router
from src.api.auth import me_router
from src.api.auth import router as auth_router
from src.api.errors import register_error_handlers
from src.api.intakes import router as intakes_router
from src.api.notifications import router as notifications_router
from src.api.org import router as org_router
from src.api.staff import router as staff_router
from src.api.triage import router as triage_router
from src.config import get_settings
from src.db import dispose_engine, get_engine
from src.logging_config import configure_logging
from src.middleware import RequestContextMiddleware
from src.services.ratelimit import create_rate_limiter


async def assert_rls_safe(engine: AsyncEngine) -> None:
    """Dừng app nếu vai trò runtime có thể bỏ qua RLS (docs/09-multi-tenancy.md mục 2)."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))
        ).one()
        if row.rolsuper or row.rolbypassrls:
            raise RuntimeError("Vai trò DB của ứng dụng là superuser hoặc có BYPASSRLS: dừng khởi động")
        owned = (
            await conn.execute(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user")
            )
        ).scalar_one()
        if owned:
            raise RuntimeError("Vai trò DB của ứng dụng đang sở hữu bảng: dừng khởi động")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await assert_rls_safe(get_engine())
    app.state.limiter = create_rate_limiter(settings.redis_url)
    try:
        yield
    finally:
        await app.state.limiter.close()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    docs = settings.is_local
    app = FastAPI(
        title="Talent Hub API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    # Thứ tự: middleware thêm sau nằm ngoài cùng.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestContextMiddleware, settings=settings)
    register_error_handlers(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Liveness: tiến trình còn sống, không chạm phụ thuộc ngoài."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> dict[str, str]:
        """Readiness: sẵn sàng nhận tải khi database truy cập được."""
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(org_router, prefix="/api/v1")
    for router in (
        intakes_router,
        applications_router,
        staff_router,
        notifications_router,
        triage_router,
        admin_router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
