"""Bảng tổng quan vận hành cho bộ phận IT: người dùng, tác vụ, an ninh, email, AI, tài liệu."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from src.ai.factory import provider_model, resolve_provider_kind
from src.config import get_settings
from src.models import AuditLog, Decision, EmailOutbox, Intake, Job, KbDocument, OrgMembership, Role, User, UserRole
from src.services import costs, org_settings
from src.services.tenancy import OrgDb


async def overview(db: OrgDb) -> dict[str, Any]:
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)
    settings = get_settings()

    members = dict(
        (await db.session.execute(select(OrgMembership.status, func.count()).group_by(OrgMembership.status))).all()
    )
    roles = dict(
        (
            await db.session.execute(
                select(Role.code, func.count(func.distinct(UserRole.membership_id)))
                .join(UserRole, UserRole.role_id == Role.id)
                .join(OrgMembership, OrgMembership.id == UserRole.membership_id)
                .where(OrgMembership.status == "active")
                .group_by(Role.code)
            )
        ).all()
    )
    locked = (
        await db.session.execute(
            select(func.count())
            .select_from(User)
            .join(OrgMembership, OrgMembership.user_id == User.id)
            .where(User.locked_until > now)
        )
    ).scalar_one()
    intakes = dict((await db.session.execute(select(Intake.status, func.count()).group_by(Intake.status))).all())
    pending_decisions = (
        await db.session.execute(select(func.count()).select_from(Decision).where(Decision.status == "pending"))
    ).scalar_one()
    jobs = dict(
        (
            await db.session.execute(
                select(Job.status, func.count()).where(Job.created_at >= day_ago).group_by(Job.status)
            )
        ).all()
    )
    failed_logins = (
        await db.session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "auth.login_failed", AuditLog.at >= day_ago)
        )
    ).scalar_one()
    logins = (
        await db.session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "auth.login", AuditLog.at >= day_ago)
        )
    ).scalar_one()
    emails = dict(
        (await db.session.execute(select(EmailOutbox.status, func.count()).group_by(EmailOutbox.status))).all()
    )
    docs = dict((await db.session.execute(select(KbDocument.status, func.count()).group_by(KbDocument.status))).all())
    cfg = await org_settings.get_all(db)
    mtd = await costs.ai_month_to_date_usd(db)

    return {
        "users": {"by_status": members, "active_by_role": roles, "locked": locked},
        "intakes": intakes,
        "pending_decisions": pending_decisions,
        "jobs_24h": jobs,
        "security_24h": {"logins": logins, "failed_logins": failed_logins},
        "email": {"backend": settings.email_backend, "queue": emails},
        "documents": docs,
        "ai": {
            "engine": cfg["ai_engine"],
            "llm_configured": resolve_provider_kind(settings) is not None,
            "model": provider_model(settings, "scoring") or settings.ai_scoring_model,
            "month_to_date_usd": round(mtd, 4),
            "monthly_budget_usd": cfg["ai_monthly_budget_usd"],
        },
    }
