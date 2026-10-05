"""Nhật ký sử dụng AI (token, chi phí ước tính)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.db import enable_org_rls_sql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("application_id", sa.Uuid, sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("job_id", sa.Uuid, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ai_usage_organization_id", "ai_usage", ["organization_id"])
    op.create_index("ix_ai_usage_org_created", "ai_usage", ["organization_id", "created_at"])
    for stmt in enable_org_rls_sql("ai_usage"):
        op.execute(stmt)


def downgrade() -> None:
    op.drop_table("ai_usage")
