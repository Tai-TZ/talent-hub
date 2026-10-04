"""Danh tính, đa tổ chức, audit log

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from src.db import enable_org_rls_sql
from src.models.base import uuid7

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    "applicant",
    "reviewer",
    "approver",
    "cohort_manager",
    "training_manager",
    "mentor",
    "admin",
    "platform_admin",
]

NOW = sa.text("now()")


def _ts(name: str, **kw: object) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=NOW, **kw)


def _org_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "organization_id",
        sa.Uuid,
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("default_locale", sa.String(8), nullable=False, server_default="vi"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Ho_Chi_Minh"),
        sa.Column("branding", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("plan_limits", pg.JSONB, nullable=False, server_default="{}"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("slug ~ '^[a-z0-9][a-z0-9-]*$'", name="slug_format"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", pg.CITEXT, nullable=False, unique=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.Text),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("failed_logins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        _ts("updated_at"),
    )

    roles = op.create_table(
        "roles",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
    )
    op.bulk_insert(roles, [{"id": uuid7(), "code": code} for code in ROLES])

    op.create_table(
        "org_memberships",
        sa.Column("id", sa.Uuid, primary_key=True),
        _org_fk(),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("organization_id", "user_id"),
        sa.CheckConstraint("status IN ('invited','active','suspended')", name="status_valid"),
    )
    op.create_index("ix_org_memberships_organization_id", "org_memberships", ["organization_id"])
    op.create_index("ix_org_memberships_user_id", "org_memberships", ["user_id"])

    op.create_table(
        "user_roles",
        _org_fk(),
        sa.Column(
            "membership_id",
            sa.Uuid,
            sa.ForeignKey("org_memberships.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role_id", sa.Uuid, sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("granted_by", sa.Uuid, sa.ForeignKey("users.id")),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=NOW),
    )
    op.create_index("ix_user_roles_organization_id", "user_roles", ["organization_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid, primary_key=True),
        _org_fk(),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("family_id", sa.Uuid, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by", sa.Uuid),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_refresh_tokens_organization_id", "refresh_tokens", ["organization_id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid, primary_key=True),
        _org_fk(),
        sa.Column("actor_user_id", sa.Uuid, sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80)),
        sa.Column("before", pg.JSONB),
        sa.Column("after", pg.JSONB),
        sa.Column("ip", pg.INET),
        sa.Column("request_id", sa.String(64)),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_org_at", "audit_logs", ["organization_id", "at"])

    for table in ("org_memberships", "user_roles", "refresh_tokens", "audit_logs"):
        for stmt in enable_org_rls_sql(table):
            op.execute(stmt)

    # Vai trò runtime chỉ được đọc bảng toàn cục; audit log chỉ thêm, không sửa/xoá.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'talenthub_app') THEN
            REVOKE INSERT, UPDATE, DELETE ON organizations, roles FROM talenthub_app;
            REVOKE UPDATE, DELETE ON audit_logs FROM talenthub_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in (
        "audit_logs",
        "refresh_tokens",
        "user_roles",
        "org_memberships",
        "roles",
        "users",
        "organizations",
    ):
        op.drop_table(table)
