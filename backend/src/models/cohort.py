"""Vận hành khoá học sau khi nhập học: lớp, nhánh, học viên, năng lực, thực chiến, phụ cấp, lịch sử xếp lớp."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, IdMixin, OrgScopedMixin, TimestampMixin


class Track(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """Nhánh chuyên sâu của chương trình (ví dụ AI Products, AI Infrastructure, AI Applications)."""

    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("organization_id", "program_id", "key"),)

    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Từ khoá mô tả nhánh, dùng để ước lượng độ phù hợp của học viên với nhánh.
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class CohortTrack(OrgScopedMixin, Base):
    __tablename__ = "cohort_tracks"

    cohort_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class CohortClass(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "cohort_classes"
    __table_args__ = (UniqueConstraint("organization_id", "cohort_id", "name"),)

    cohort_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class Enrollment(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("organization_id", "application_id"),
        CheckConstraint("status IN ('active','withdrawn','qualified','not_qualified')", name="status_valid"),
        Index("ix_enrollments_cohort", "organization_id", "cohort_id", "status"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org_memberships.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cohorts.id", ondelete="RESTRICT"), nullable=False)
    class_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohort_classes.id", ondelete="SET NULL"))
    track_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    qualification_reason: Mapped[str | None] = mapped_column(Text)
    qualification_decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    qualification_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Competency(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """Năng lực theo mức (thang SFIA 1–7 hoặc thang tuỳ chỉnh)."""

    __tablename__ = "competencies"
    __table_args__ = (UniqueConstraint("organization_id", "program_id", "code"),)

    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_level: Mapped[int] = mapped_column(Integer, nullable=False, default=7)


class TrackTarget(OrgScopedMixin, Base):
    """Mức năng lực mục tiêu của từng nhánh."""

    __tablename__ = "track_targets"

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    competency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), primary_key=True
    )
    target_level: Mapped[int] = mapped_column(Integer, nullable=False)


class CompetencyAssessment(IdMixin, OrgScopedMixin, Base):
    """Đánh giá năng lực theo mức do mentor/giảng viên thực hiện; chỉ thêm, giữ lịch sử."""

    __tablename__ = "competency_assessments"
    __table_args__ = (Index("ix_comp_assess_enrollment", "enrollment_id", "competency_id", "assessed_at"),)

    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    competency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessor_membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org_memberships.id"), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Mã tham chiếu của hệ thống nguồn (LMS) để đẩy lại không tạo bản ghi trùng; duy nhất trong tổ chức.
    external_ref: Mapped[str | None] = mapped_column(String(200))


class Partner(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "partners"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")


class PartnerDemand(OrgScopedMixin, Base):
    """Số vị trí thực chiến mỗi đối tác nhận theo khoá và nhánh."""

    __tablename__ = "partner_demand"

    cohort_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("partners.id", ondelete="CASCADE"), primary_key=True)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    slots: Mapped[int] = mapped_column(Integer, nullable=False)


class Placement(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "placements"
    __table_args__ = (UniqueConstraint("organization_id", "enrollment_id"),)

    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    mentor_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("org_memberships.id"))
    project: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)


class StipendEntry(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """Sổ ghi nhận phụ cấp theo tháng. Hệ thống chỉ ghi nhận; chi trả thực hiện ngoài hệ thống."""

    __tablename__ = "stipend_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "enrollment_id", "period"),
        CheckConstraint("status IN ('eligible','paid','void')", name="status_valid"),
    )

    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    amount_vnd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="eligible")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cost_entries.id", ondelete="SET NULL"))


class RoundResult(IdMixin, OrgScopedMixin, Base):
    """Điểm vòng đánh giá năng lực nhập từ hệ thống bài thi bên ngoài (CSV/JSON)."""

    __tablename__ = "round_results"
    __table_args__ = (UniqueConstraint("organization_id", "application_id", "round"),)

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    round: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    imported_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ComposerRun(IdMixin, OrgScopedMixin, Base):
    """Phương án xếp lớp/nhánh/thực chiến do bộ giải đề xuất. Chỉ áp dụng khi người quản lý xác nhận."""

    __tablename__ = "composer_runs"

    cohort_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assignments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
