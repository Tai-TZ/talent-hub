"""Chương trình, khoá, đợt tuyển, hồ sơ và các bản ghi quy trình xét tuyển (docs/05-data-model.md)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, IdMixin, OrgScopedMixin, TimestampMixin

APPLICATION_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "IN_ROUND",
    "NEEDS_INFO",
    "PENDING_APPROVAL",
    "ACCEPTED",
    "REJECTED",
    "WAITLISTED",
    "ENROLLED",
    "WITHDRAWN",
)


class Program(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="cohort")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Cohort(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "cohorts"
    __table_args__ = (UniqueConstraint("organization_id", "program_id", "code"),)

    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_on: Mapped[date | None] = mapped_column(Date)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")


class Intake(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "intakes"
    __table_args__ = (
        CheckConstraint("closes_at > opens_at", name="window_valid"),
        CheckConstraint("quota > 0", name="quota_positive"),
        CheckConstraint("status IN ('draft','open','closed','archived')", name="status_valid"),
        CheckConstraint("approval_mode IN ('two_level','single_level')", name="approval_mode_valid"),
    )

    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # Dãy vòng: [{"key": "portfolio", "label": "Xét hồ sơ", "type": "review"}, ...]
    rounds: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    approval_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="two_level")
    ai_screening_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Ẩn danh tính ứng viên với reviewer; AI chỉ hiện sau khi reviewer chốt điểm.
    blind_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    eligibility_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    triage_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Rubric(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("organization_id", "intake_id", "round", "version"),)

    intake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intakes.id", ondelete="CASCADE"), nullable=False)
    round: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # [{"id": "projects", "name": "...", "description": "...", "weight": 3, "max": 5, "kind": "projects"}]
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Application(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("organization_id", "intake_id", "applicant_membership_id"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_ROUND','NEEDS_INFO','PENDING_APPROVAL',"
            "'ACCEPTED','REJECTED','WAITLISTED','ENROLLED','WITHDRAWN')",
            name="status_valid",
        ),
        Index("ix_applications_queue", "organization_id", "intake_id", "status", "current_round"),
    )

    intake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("intakes.id", ondelete="RESTRICT"), nullable=False)
    applicant_membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org_memberships.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    current_round: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    candidate_code: Mapped[str] = mapped_column(String(16), nullable=False)
    # profile: thông tin nhận dạng/nhạy cảm; content: nội dung năng lực. Chỉ content được đưa vào AI chấm.
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_reviewer_membership_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("org_memberships.id"))


class ApplicationEvent(IdMixin, OrgScopedMixin, Base):
    """Chỉ thêm. Là timeline của ứng viên (visible_to_applicant) và nhật ký xử lý nội bộ."""

    __tablename__ = "application_events"
    __table_args__ = (Index("ix_application_events_app_at", "application_id", "at"),)

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str | None] = mapped_column(String(24))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    visible_to_applicant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Review(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "application_id", "reviewer_membership_id", "round"),
        CheckConstraint(
            "recommendation IS NULL OR recommendation IN ('advance','reject','waitlist','accept','need_info')",
            name="recommendation_valid",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    reviewer_membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org_memberships.id"), nullable=False)
    round: Mapped[str] = mapped_column(String(40), nullable=False)
    rubric_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rubrics.id"))
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    total_score: Mapped[float | None] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendation: Mapped[str | None] = mapped_column(String(16))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiAssessment(IdMixin, OrgScopedMixin, Base):
    """Gợi ý của AI. Lưu kèm engine, phiên bản prompt và các trường đã dùng để giải trình được."""

    __tablename__ = "ai_assessments"
    __table_args__ = (Index("ix_ai_assessments_app", "application_id", "round"),)

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    round: Mapped[str] = mapped_column(String(40), nullable=False)
    engine: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    needs_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Decision(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint("decided_by IS NULL OR decided_by <> proposed_by", name="four_eyes"),
        CheckConstraint("proposed_outcome IN ('accepted','rejected','waitlisted')", name="proposed_outcome_valid"),
        CheckConstraint("status IN ('pending','approved','returned')", name="status_valid"),
        Index("ix_decisions_queue", "organization_id", "status"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    proposed_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    proposal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_outcome: Mapped[str | None] = mapped_column(String(16))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    applicant_message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")


class Notification(IdMixin, OrgScopedMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient", "recipient_membership_id", "created_at"),)

    recipient_membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("org_memberships.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Job(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """Tác vụ nền có tiến độ (ví dụ chấm sơ bộ hàng loạt) để giao diện hiển thị thanh tiến độ thật."""

    __tablename__ = "jobs"
    __table_args__ = (CheckConstraint("status IN ('queued','running','done','failed')", name="status_valid"),)

    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiUsage(IdMixin, OrgScopedMixin, Base):
    """Mỗi lần gọi LLM: token và chi phí ước tính (USD) để kiểm soát chi phí AI theo tính năng."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_org_created", "organization_id", "created_at"),)

    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
