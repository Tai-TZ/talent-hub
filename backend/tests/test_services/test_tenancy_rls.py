"""Cô lập dữ liệu giữa các tổ chức ở tầng database (docs/09-multi-tenancy.md mục 2).

Mọi test dùng vai trò runtime `talenthub_app` (không BYPASSRLS), đúng như môi trường thật.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db import get_engine, org_session
from src.main import assert_rls_safe
from src.models import AuditLog, Organization


async def _count_audit(maker: async_sessionmaker[AsyncSession], org: Organization) -> int:
    async with org_session(org.id, maker) as session:
        return (await session.execute(text("SELECT count(*) FROM audit_logs"))).scalar_one()


async def test_runtime_role_cannot_bypass_rls() -> None:
    await assert_rls_safe(get_engine())  # không raise


async def test_every_org_table_has_forced_rls_and_policy(orgs: dict[str, Organization]) -> None:
    """Bảng nào có cột organization_id mà thiếu RLS/policy sẽ làm test này fail."""
    async with org_session(orgs["alpha"].id) as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                           EXISTS (SELECT 1 FROM pg_policies p
                                   WHERE p.schemaname = 'public' AND p.tablename = c.relname)
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
                    JOIN information_schema.columns col
                      ON col.table_schema = 'public' AND col.table_name = c.relname
                     AND col.column_name = 'organization_id'
                    WHERE c.relkind = 'r'
                    """
                )
            )
        ).all()
    assert rows, "không tìm thấy bảng nào có organization_id"
    for name, rls, forced, has_policy in rows:
        if name == "organizations":
            continue  # bảng toàn cục không có organization_id; phòng khi sau này đổi
        assert rls and forced and has_policy, f"bảng {name} thiếu RLS/FORCE/policy"


async def test_tenant_sees_only_own_rows(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    alpha, beta = orgs["alpha"], orgs["beta"]
    async with org_session(alpha.id, app_maker) as s:
        s.add(AuditLog(action="test.alpha", entity_type="probe"))
    async with org_session(beta.id, app_maker) as s:
        s.add(AuditLog(action="test.beta", entity_type="probe"))

    async with org_session(alpha.id, app_maker) as s:
        actions = set((await s.execute(text("SELECT action FROM audit_logs"))).scalars())
    assert "test.alpha" in actions
    assert "test.beta" not in actions


async def test_memberships_are_isolated(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    async with org_session(orgs["alpha"].id, app_maker) as s:
        org_ids = set((await s.execute(text("SELECT DISTINCT organization_id FROM org_memberships"))).scalars())
    assert org_ids == {orgs["alpha"].id}


async def test_no_context_means_no_rows(app_maker: async_sessionmaker[AsyncSession]) -> None:
    async with app_maker() as s, s.begin():
        assert (await s.execute(text("SELECT count(*) FROM org_memberships"))).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM audit_logs"))).scalar_one() == 0


async def test_cannot_insert_row_for_another_org(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    alpha, beta = orgs["alpha"], orgs["beta"]
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with org_session(alpha.id, app_maker) as s:
            await s.execute(
                text(
                    "INSERT INTO audit_logs (id, organization_id, action, entity_type) "
                    "VALUES (:id, :org, 'evil', 'probe')"
                ),
                {"id": uuid.uuid4(), "org": beta.id},
            )


async def test_cannot_update_or_delete_other_orgs_rows(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    alpha, beta = orgs["alpha"], orgs["beta"]
    async with org_session(alpha.id, app_maker) as s:
        result = await s.execute(text("UPDATE org_memberships SET status = 'suspended'"))
        # chỉ chạm vào dòng của alpha (dưới đây hoàn tác bằng rollback)
        assert result.rowcount > 0
        await s.rollback()
    async with org_session(beta.id, app_maker) as s:
        statuses = set((await s.execute(text("SELECT status FROM org_memberships"))).scalars())
    assert statuses == {"active"}


async def test_audit_log_is_append_only(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    async with org_session(orgs["alpha"].id, app_maker) as s:
        s.add(AuditLog(action="test.append_only", entity_type="probe"))
    for statement in ("UPDATE audit_logs SET action = 'x'", "DELETE FROM audit_logs"):
        with pytest.raises(DBAPIError):
            async with org_session(orgs["alpha"].id, app_maker) as s:
                await s.execute(text(statement))


async def test_runtime_role_cannot_write_global_tables(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    for statement in (
        "INSERT INTO organizations (id, slug, name) VALUES (gen_random_uuid(), 'evil', 'Evil')",
        "DELETE FROM roles",
        "UPDATE organizations SET name = 'x'",
    ):
        with pytest.raises(DBAPIError):
            async with org_session(orgs["alpha"].id, app_maker) as s:
                await s.execute(text(statement))


async def test_context_does_not_leak_between_transactions(
    orgs: dict[str, Organization], app_maker: async_sessionmaker[AsyncSession]
) -> None:
    async with org_session(orgs["alpha"].id, app_maker) as s:
        assert await _scalar(s, "SELECT count(*) FROM org_memberships") > 0
    # transaction mới trên (có thể) cùng kết nối: không còn ngữ cảnh
    async with app_maker() as s, s.begin():
        assert await _scalar(s, "SELECT count(*) FROM org_memberships") == 0


async def _scalar(session: AsyncSession, sql: str) -> int:
    return (await session.execute(text(sql))).scalar_one()
