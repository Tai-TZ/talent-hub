"""Khu quản trị IT: lời mời, email outbox, cài đặt tổ chức, tài liệu tri thức, chi phí và ngân sách

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from src.db import enable_org_rls_sql
from src.models.base import NAMING

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
md = sa.MetaData(naming_convention=NAMING)


def _id() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("id", sa.Uuid, primary_key=True)


def _org(index: bool = True) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=index
    )


def _stamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    ]


def _define() -> list[sa.Table]:
    for stub in ("organizations", "users", "org_memberships", "cohorts"):
        sa.Table(stub, md, sa.Column("id", sa.Uuid, primary_key=True))

    invitations = sa.Table(
        "invitations",
        md,
        _id(),
        _org(),
        sa.Column(
            "membership_id",
            sa.Uuid,
            sa.ForeignKey("org_memberships.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(10), nullable=False, server_default="invite"),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    outbox = sa.Table(
        "email_outbox",
        md,
        _id(),
        _org(),
        sa.Column("to_email", sa.String(254), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    sa.Index("ix_email_outbox_pending", outbox.c.status, outbox.c.created_at)
    settings = sa.Table(
        "org_settings",
        md,
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value", pg.JSONB, nullable=False),
        sa.Column("updated_by", sa.Uuid, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    docs = sa.Table(
        "kb_documents",
        md,
        _id(),
        _org(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="public"),
        sa.Column("filename", sa.String(255), nullable=False, server_default=""),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="text/plain"),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("char_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(10), nullable=False, server_default="ready"),
        sa.Column("error", sa.Text),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id")),
        *_stamps(),
        sa.CheckConstraint("visibility IN ('public','internal')", name="visibility_valid"),
        sa.CheckConstraint("status IN ('ready','failed','retired')", name="status_valid"),
    )
    chunks = sa.Table(
        "kb_chunks",
        md,
        _id(),
        _org(),
        sa.Column("document_id", sa.Uuid, sa.ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("heading", sa.String(300), nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "tsv",
            pg.TSVECTOR,
            sa.Computed("to_tsvector('simple', f_unaccent(heading || ' ' || content))", persisted=True),
        ),
    )
    sa.Index("ix_kb_chunks_doc", chunks.c.document_id, chunks.c.ordinal)
    sa.Index("ix_kb_chunks_tsv", chunks.c.tsv, postgresql_using="gin")
    costs = sa.Table(
        "cost_entries",
        md,
        _id(),
        _org(),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("amount_vnd", sa.Numeric(16, 2), nullable=False),
        sa.Column("occurred_on", sa.Date, nullable=False),
        sa.Column("cohort_id", sa.Uuid, sa.ForeignKey("cohorts.id", ondelete="SET NULL")),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("source", sa.String(10), nullable=False, server_default="manual"),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.String(300)),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id")),
        *_stamps(),
        sa.CheckConstraint(
            "category IN ('stipend','ai','infrastructure','partner','operations','other')", name="category_valid"
        ),
        sa.CheckConstraint("source IN ('manual','system')", name="source_valid"),
    )
    sa.Index("ix_cost_entries_org_date", costs.c.organization_id, costs.c.occurred_on)
    budgets = sa.Table(
        "budgets",
        md,
        _id(),
        _org(),
        sa.Column("cohort_id", sa.Uuid, sa.ForeignKey("cohorts.id", ondelete="CASCADE")),
        sa.Column("category", sa.String(20)),
        sa.Column("amount_vnd", sa.Numeric(16, 2), nullable=False),
        sa.Column("updated_by", sa.Uuid, sa.ForeignKey("users.id")),
        *_stamps(),
        sa.CheckConstraint("amount_vnd >= 0", name="amount_non_negative"),
        sa.UniqueConstraint(
            "organization_id", "cohort_id", "category", name="uq_budgets_scope", postgresql_nulls_not_distinct=True
        ),
    )
    return [invitations, outbox, settings, docs, chunks, costs, budgets]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # Bọc unaccent thành hàm IMMUTABLE để dùng được trong cột sinh tự động và chỉ mục (tìm kiếm tiếng Việt không dấu).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent', $1) $$
        """
    )
    tables = _define()
    md.create_all(bind=op.get_bind(), tables=tables)
    for table in tables:
        for stmt in enable_org_rls_sql(table.name):
            op.execute(stmt)
    op.execute("GRANT EXECUTE ON FUNCTION f_unaccent(text) TO PUBLIC")


def downgrade() -> None:
    for name in ("budgets", "cost_entries", "kb_chunks", "kb_documents", "org_settings", "email_outbox", "invitations"):
        op.drop_table(name)
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
