"""Nhật ký câu hỏi của trợ lý (đo chất lượng, phát hiện khoảng trống tài liệu)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from src.db import enable_org_rls_sql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_queries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("membership_id", sa.Uuid(), sa.ForeignKey("org_memberships.id", ondelete="SET NULL")),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("question_key", sa.String(500), nullable=False),
        sa.Column("answered", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False, server_default=""),
        sa.Column("engine", sa.String(60), nullable=False),
        sa.Column("citations", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("helpful", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_queries_organization_id", "assistant_queries", ["organization_id"])
    op.create_index("ix_assistant_queries_org_created", "assistant_queries", ["organization_id", "created_at"])
    for stmt in enable_org_rls_sql("assistant_queries"):
        op.execute(stmt)


def downgrade() -> None:
    op.drop_index("ix_assistant_queries_org_created", table_name="assistant_queries")
    op.drop_index("ix_assistant_queries_organization_id", table_name="assistant_queries")
    op.drop_table("assistant_queries")
