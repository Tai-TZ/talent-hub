"""Khoá tích hợp cho hệ thống bên ngoài (Power BI, LMS, CRM). Chỉ lưu băm SHA-256 của khoá; khoá gốc hiện một lần."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, IdMixin, OrgScopedMixin


class IntegrationKey(IdMixin, OrgScopedMixin, Base):
    __tablename__ = "integration_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_integration_keys_hash"),
        UniqueConstraint("organization_id", "prefix", name="uq_integration_keys_prefix"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Tài khoản dịch vụ riêng của khoá: thao tác qua khoá (ví dụ LMS đẩy đánh giá) được ghi nhận đúng tác nhân.
    service_membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org_memberships.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
