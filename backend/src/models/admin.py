"""Mô hình cho khu quản trị của bộ phận IT: lời mời, email, cài đặt, tài liệu, chi phí."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, IdMixin, OrgScopedMixin, TimestampMixin

COST_CATEGORIES = ("stipend", "ai", "infrastructure", "partner", "operations", "other")


class Invitation(IdMixin, OrgScopedMixin, Base):
    """Lời mời đặt mật khẩu cho tài khoản do admin cấp (kind=invite) hoặc đặt lại mật khẩu (kind=reset)."""

    __tablename__ = "invitations"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org_memberships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="invite")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EmailOutbox(IdMixin, OrgScopedMixin, Base):
    """Hàng đợi email (outbox): ghi cùng transaction nghiệp vụ, gửi nền, thử lại khi lỗi."""

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_pending", "status", "created_at"),)

    to_email: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrgSetting(Base):
    __tablename__ = "org_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KbDocument(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "kb_documents"
    __table_args__ = (
        CheckConstraint("visibility IN ('public','internal')", name="visibility_valid"),
        CheckConstraint("status IN ('ready','failed','retired')", name="status_valid"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False, default="public")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ready")
    error: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class KbChunk(IdMixin, OrgScopedMixin, Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (Index("ix_kb_chunks_doc", "document_id", "ordinal"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', f_unaccent(heading || ' ' || content))", persisted=True)
    )


class CostEntry(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "cost_entries"
    __table_args__ = (
        CheckConstraint(
            "category IN ('stipend','ai','infrastructure','partner','operations','other')", name="category_valid"
        ),
        CheckConstraint("source IN ('manual','system')", name="source_valid"),
        Index("ix_cost_entries_org_date", "organization_id", "occurred_on"),
    )

    category: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_vnd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Budget(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("amount_vnd >= 0", name="amount_non_negative"),
        UniqueConstraint(
            "organization_id", "cohort_id", "category", name="uq_budgets_scope", postgresql_nulls_not_distinct=True
        ),
    )

    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"))
    category: Mapped[str | None] = mapped_column(String(20))  # null = tổng ngân sách của khoá
    amount_vnd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
