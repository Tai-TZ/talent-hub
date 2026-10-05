"""Khoá tích hợp (Power BI, LMS, CRM) và mã tham chiếu ngoài cho đánh giá năng lực đẩy từ LMS

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.db import enable_org_rls_sql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "service_membership_id", sa.Uuid(), sa.ForeignKey("org_memberships.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("key_hash", name="uq_integration_keys_hash"),
        sa.UniqueConstraint("organization_id", "prefix", name="uq_integration_keys_prefix"),
    )
    op.create_index("ix_integration_keys_organization_id", "integration_keys", ["organization_id"])
    for stmt in enable_org_rls_sql("integration_keys"):
        op.execute(stmt)

    op.add_column("competency_assessments", sa.Column("external_ref", sa.String(200)))
    op.create_index(
        "uq_competency_assessments_external_ref",
        "competency_assessments",
        ["organization_id", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_competency_assessments_external_ref", table_name="competency_assessments")
    op.drop_column("competency_assessments", "external_ref")
    op.drop_index("ix_integration_keys_organization_id", table_name="integration_keys")
    op.drop_table("integration_keys")
