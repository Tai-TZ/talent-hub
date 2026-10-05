"""Chương trình, khoá, đợt tuyển, hồ sơ, rubric, chấm điểm, quyết định, thông báo, tác vụ nền

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from src.db import enable_org_rls_sql
from src.models.base import NAMING

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
md = sa.MetaData(naming_convention=NAMING)


def _id() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("id", sa.Uuid, primary_key=True)


def _org() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "organization_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _stamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    ]


def _fk(name: str, target: str, *, nullable: bool = False, ondelete: str | None = None) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.Uuid, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def _json(name: str, default: str = "{}", nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, pg.JSONB, nullable=nullable, server_default=default)


def _define() -> list[sa.Table]:
    # Bảng đã có từ migration trước: chỉ khai báo khoá chính để phân giải khoá ngoại, không tạo lại.
    for stub in ("organizations", "users", "org_memberships"):
        sa.Table(stub, md, sa.Column("id", sa.Uuid, primary_key=True))
    programs = sa.Table(
        "programs",
        md,
        _id(),
        _org(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", pg.JSONB, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="cohort"),
        _json("config"),
        *_stamps(),
        sa.UniqueConstraint("organization_id", "code"),
    )
    cohorts = sa.Table(
        "cohorts",
        md,
        _id(),
        _org(),
        _fk("program_id", "programs.id", ondelete="CASCADE"),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("starts_on", sa.Date),
        sa.Column("capacity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        *_stamps(),
        sa.UniqueConstraint("organization_id", "program_id", "code"),
    )
    intakes = sa.Table(
        "intakes",
        md,
        _id(),
        _org(),
        _fk("program_id", "programs.id", ondelete="CASCADE"),
        _fk("cohort_id", "cohorts.id", nullable=True, ondelete="SET NULL"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quota", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        _json("rounds", "[]"),
        sa.Column("approval_mode", sa.String(16), nullable=False, server_default="two_level"),
        sa.Column("ai_screening_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("blind_review", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("min_reviews", sa.Integer, nullable=False, server_default="1"),
        _json("eligibility_rules", "[]"),
        _json("triage_config"),
        *_stamps(),
        sa.CheckConstraint("closes_at > opens_at", name="window_valid"),
        sa.CheckConstraint("quota > 0", name="quota_positive"),
        sa.CheckConstraint("status IN ('draft','open','closed','archived')", name="status_valid"),
        sa.CheckConstraint("approval_mode IN ('two_level','single_level')", name="approval_mode_valid"),
    )
    rubrics = sa.Table(
        "rubrics",
        md,
        _id(),
        _org(),
        _fk("intake_id", "intakes.id", ondelete="CASCADE"),
        sa.Column("round", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("criteria", pg.JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        *_stamps(),
        sa.UniqueConstraint("organization_id", "intake_id", "round", "version"),
    )
    applications = sa.Table(
        "applications",
        md,
        _id(),
        _org(),
        _fk("intake_id", "intakes.id", ondelete="RESTRICT"),
        _fk("applicant_membership_id", "org_memberships.id", ondelete="RESTRICT"),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("current_round", sa.String(40)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("candidate_code", sa.String(16), nullable=False),
        _json("profile"),
        _json("content"),
        _json("flags", "[]"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("consented_at", sa.DateTime(timezone=True)),
        _fk("assigned_reviewer_membership_id", "org_memberships.id", nullable=True),
        *_stamps(),
        sa.UniqueConstraint("organization_id", "intake_id", "applicant_membership_id"),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_ROUND','NEEDS_INFO','PENDING_APPROVAL',"
            "'ACCEPTED','REJECTED','WAITLISTED','ENROLLED','WITHDRAWN')",
            name="status_valid",
        ),
    )
    sa.Index("ix_applications_applicant_membership_id", applications.c.applicant_membership_id)
    sa.Index(
        "ix_applications_queue",
        applications.c.organization_id,
        applications.c.intake_id,
        applications.c.status,
        applications.c.current_round,
    )
    events = sa.Table(
        "application_events",
        md,
        _id(),
        _org(),
        _fk("application_id", "applications.id", ondelete="CASCADE"),
        _fk("actor_user_id", "users.id", nullable=True),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24)),
        _json("payload"),
        sa.Column("visible_to_applicant", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    sa.Index("ix_application_events_app_at", events.c.application_id, events.c.at)
    reviews = sa.Table(
        "reviews",
        md,
        _id(),
        _org(),
        _fk("application_id", "applications.id", ondelete="CASCADE"),
        _fk("reviewer_membership_id", "org_memberships.id"),
        sa.Column("round", sa.String(40), nullable=False),
        _fk("rubric_id", "rubrics.id", nullable=True),
        _json("scores"),
        sa.Column("total_score", sa.Float),
        sa.Column("comment", sa.Text, nullable=False, server_default=""),
        sa.Column("recommendation", sa.String(16)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.UniqueConstraint("organization_id", "application_id", "reviewer_membership_id", "round"),
        sa.CheckConstraint(
            "recommendation IS NULL OR recommendation IN ('advance','reject','waitlist','accept','need_info')",
            name="recommendation_valid",
        ),
    )
    ai = sa.Table(
        "ai_assessments",
        md,
        _id(),
        _org(),
        _fk("application_id", "applications.id", ondelete="CASCADE"),
        sa.Column("round", sa.String(40), nullable=False),
        sa.Column("engine", sa.String(60), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("total_score", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("needs_attention", sa.Boolean, nullable=False, server_default="false"),
        _json("scores"),
        _json("evidence"),
        _json("flags", "[]"),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        _json("input_fields", "[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    sa.Index("ix_ai_assessments_app", ai.c.application_id, ai.c.round)
    decisions = sa.Table(
        "decisions",
        md,
        _id(),
        _org(),
        _fk("application_id", "applications.id", ondelete="CASCADE"),
        sa.Column("proposed_outcome", sa.String(16), nullable=False),
        _fk("proposed_by", "users.id"),
        sa.Column("proposal_reason", sa.Text, nullable=False),
        sa.Column("decided_outcome", sa.String(16)),
        _fk("decided_by", "users.id", nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.Text),
        sa.Column("applicant_message", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        *_stamps(),
        sa.CheckConstraint("decided_by IS NULL OR decided_by <> proposed_by", name="four_eyes"),
        sa.CheckConstraint("proposed_outcome IN ('accepted','rejected','waitlisted')", name="proposed_outcome_valid"),
        sa.CheckConstraint("status IN ('pending','approved','returned')", name="status_valid"),
    )
    sa.Index("ix_decisions_queue", decisions.c.organization_id, decisions.c.status)
    notifications = sa.Table(
        "notifications",
        md,
        _id(),
        _org(),
        _fk("recipient_membership_id", "org_memberships.id", ondelete="CASCADE"),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("link", sa.String(300)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    sa.Index("ix_notifications_recipient", notifications.c.recipient_membership_id, notifications.c.created_at)
    jobs = sa.Table(
        "jobs",
        md,
        _id(),
        _org(),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done", sa.Integer, nullable=False, server_default="0"),
        _json("params"),
        _json("result"),
        sa.Column("error", sa.Text),
        _fk("created_by", "users.id", nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("status IN ('queued','running','done','failed')", name="status_valid"),
    )
    return [programs, cohorts, intakes, rubrics, applications, events, reviews, ai, decisions, notifications, jobs]


def upgrade() -> None:
    tables = _define()
    md.create_all(bind=op.get_bind(), tables=tables)
    for table in tables:
        for stmt in enable_org_rls_sql(table.name):
            op.execute(stmt)
    # application_events chỉ thêm: vai trò runtime không được sửa hoặc xoá.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'talenthub_app') THEN
            REVOKE UPDATE, DELETE ON application_events FROM talenthub_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for name in (
        "jobs",
        "notifications",
        "decisions",
        "ai_assessments",
        "reviews",
        "application_events",
        "applications",
        "rubrics",
        "intakes",
        "cohorts",
        "programs",
    ):
        op.drop_table(name)
