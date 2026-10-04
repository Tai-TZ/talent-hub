import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from src.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_s,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={
                "server_settings": {
                    "application_name": "talenthub-api",
                    "statement_timeout": str(settings.db_statement_timeout_ms),
                    "idle_in_transaction_session_timeout": str(settings.db_idle_in_tx_timeout_ms),
                }
            },
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def set_org_context(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Đặt ngữ cảnh tổ chức cho transaction hiện tại (SET LOCAL qua set_config(..., true)).

    Giá trị tự mất khi commit/rollback nên không rò rỉ giữa các request dùng chung kết nối.
    """
    await session.execute(text("SELECT set_config('app.org_id', :org_id, true)"), {"org_id": str(org_id)})
    session.info["org_id"] = org_id


@asynccontextmanager
async def org_session(
    org_id: uuid.UUID, maker: async_sessionmaker[AsyncSession] | None = None
) -> AsyncIterator[AsyncSession]:
    """Session có transaction và ngữ cảnh tổ chức, dùng cho worker/job/CLI."""
    maker = maker or get_sessionmaker()
    async with maker() as session, session.begin():
        await set_org_context(session, org_id)
        yield session


@event.listens_for(Session, "before_flush")
def _stamp_organization(session: Session, flush_context: object, instances: object) -> None:
    """Tự gán organization_id cho bản ghi mới thuộc tổ chức nếu chưa có.

    Đây chỉ là tiện ích; ranh giới bảo vệ thật sự là RLS (WITH CHECK) ở database.
    """
    org_id = session.info.get("org_id")
    if org_id is None:
        return
    for obj in session.new:
        if hasattr(obj, "organization_id") and getattr(obj, "organization_id", None) is None:
            obj.organization_id = org_id


# --- Tiện ích tạo policy RLS cho migration (xem docs/09-multi-tenancy.md) ---
# Mọi migration tạo bảng có cột organization_id phải gọi enable_org_rls_sql(table).
# Test cô lập trong CI kiểm tra không có bảng nào bị sót.
ORG_EXPR = "nullif(current_setting('app.org_id', true), '')::uuid"


def enable_org_rls_sql(table: str) -> list[str]:
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        # FORCE: ngay cả chủ sở hữu bảng cũng bị policy ràng buộc.
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        (
            f"CREATE POLICY org_isolation ON {table} "
            f"USING (organization_id = {ORG_EXPR}) "
            f"WITH CHECK (organization_id = {ORG_EXPR})"
        ),
    ]
