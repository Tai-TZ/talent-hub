"""Fixture test dùng Postgres thật (docker compose up -d postgres) với database riêng talenthub_test.

Test dựng database từ migration bằng vai trò chủ sở hữu, rồi chạy ứng dụng bằng vai trò runtime
không có BYPASSRLS, đúng như môi trường thật.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

HOST = os.environ.get("TEST_DB_HOST", "localhost")
TEST_DB = "talenthub_test"
SUPERUSER_DSN = f"postgresql://postgres:postgres@{HOST}:5432"
OWNER_URL = f"postgresql+asyncpg://talenthub_owner:owner@{HOST}:5432/{TEST_DB}"
APP_URL = f"postgresql+asyncpg://talenthub_app:app@{HOST}:5432/{TEST_DB}"

os.environ["DATABASE_URL"] = APP_URL
os.environ["MIGRATION_DATABASE_URL"] = OWNER_URL
os.environ["ENVIRONMENT"] = "local"
os.environ["ALLOW_ORG_HEADER"] = "true"

from src.config import get_settings  # noqa: E402

get_settings.cache_clear()

from src import db as db_module  # noqa: E402
from src.main import create_app  # noqa: E402
from src.models import Organization  # noqa: E402

PASSWORD = "Passw0rd!test"


async def _prepare_database() -> None:
    admin = await asyncpg.connect(f"{SUPERUSER_DSN}/postgres")
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {TEST_DB}")
        await admin.execute(f"GRANT ALL PRIVILEGES ON DATABASE {TEST_DB} TO talenthub_owner")
        await admin.execute(f"GRANT CONNECT ON DATABASE {TEST_DB} TO talenthub_app")
    finally:
        await admin.close()
    conn = await asyncpg.connect(f"{SUPERUSER_DSN}/{TEST_DB}")
    try:
        # Giống infra/postgres/init/01-roles.sql cho database test.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS citext")
        await conn.execute("GRANT ALL ON SCHEMA public TO talenthub_owner")
        await conn.execute("GRANT USAGE ON SCHEMA public TO talenthub_app")
        await conn.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE talenthub_owner IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO talenthub_app"
        )
        await conn.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE talenthub_owner IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO talenthub_app"
        )
    finally:
        await conn.close()

    api_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", OWNER_URL)
    await asyncio.to_thread(command.upgrade, cfg, "head")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    await _prepare_database()
    yield
    await db_module.dispose_engine()


@pytest_asyncio.fixture(scope="session")
async def owner_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(OWNER_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def app_maker() -> async_sessionmaker[AsyncSession]:
    return db_module.get_sessionmaker()


@pytest_asyncio.fixture(scope="session")
async def orgs(owner_maker: async_sessionmaker[AsyncSession]) -> dict[str, Organization]:
    """Hai tổ chức, mỗi tổ chức đủ các vai trò, tạo bằng cùng code với CLI."""
    from src.cli import ALL_ROLES, add_member, create_org

    result: dict[str, Organization] = {}
    async with owner_maker() as session, session.begin():
        for slug in ("alpha", "beta"):
            org = await create_org(session, slug=slug, name=slug.title())
            for role in ALL_ROLES:
                await add_member(
                    session,
                    org,
                    email=f"{role}@{slug}.test",
                    full_name=f"{role} {slug}",
                    role_codes=[role],
                    password=PASSWORD,
                    must_change_password=False,
                )
            result[slug] = org
        # Người dùng bổ sung cho các kịch bản nhiều người cùng xét hồ sơ.
        for slug in ("alpha", "beta"):
            for email, name, roles in (
                (f"applicant2@{slug}.test", "Applicant Two", ["applicant"]),
                (f"applicant3@{slug}.test", "Applicant Three", ["applicant"]),
                (f"reviewer2@{slug}.test", "Reviewer Two", ["reviewer"]),
                (f"approver2@{slug}.test", "Approver Two", ["approver"]),
                (f"dual@{slug}.test", "Dual Role", ["applicant", "reviewer", "approver"]),
            ):
                await add_member(
                    session,
                    result[slug],
                    email=email,
                    full_name=name,
                    role_codes=roles,
                    password=PASSWORD,
                    must_change_password=False,
                )
        # Người dùng buộc đổi mật khẩu ở lần đầu.
        await add_member(
            session,
            result["alpha"],
            email="newbie@alpha.test",
            full_name="Newbie",
            role_codes=["admin"],
            password=PASSWORD,
            must_change_password=True,
        )
    return result


@pytest_asyncio.fixture
async def app_instance(orgs: dict[str, Organization]) -> AsyncIterator[FastAPI]:
    app = create_app()
    # ASGITransport không tự chạy lifespan: chạy tay để có rate limiter và kiểm tra RLS khi khởi động.
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture
async def client(app_instance: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def login_as(app_instance: FastAPI) -> AsyncIterator[Callable[..., Awaitable[AsyncClient]]]:
    """Tạo client đã đăng nhập (cookie riêng) cho một người dùng của tổ chức."""
    clients: list[AsyncClient] = []

    async def factory(role_or_email: str, org: str = "alpha") -> AsyncClient:
        email = role_or_email if "@" in role_or_email else f"{role_or_email}@{org}.test"
        c = AsyncClient(
            transport=ASGITransport(app=app_instance), base_url="http://test", headers={"X-Organization": org}
        )
        clients.append(c)
        res = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert res.status_code == 200, res.text
        return c

    yield factory
    for c in clients:
        await c.aclose()


@pytest.fixture
def password() -> str:
    return PASSWORD
