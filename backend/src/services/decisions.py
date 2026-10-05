"""Quyết định tuyển sinh theo nguyên tắc bốn mắt: người đề xuất khác người phê duyệt, có lý do, có chỉ tiêu."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from src.models import Application, Decision
from src.services.audit import RequestMeta, write_audit
from src.services.intakes import get_intake
from src.services.notifications import notify
from src.services.reviews import submitted_reviews
from src.services.tenancy import OrgDb
from src.services.workflow import Actor, apply_transition

OUTCOME_TO_STATUS = {"accepted": "ACCEPTED", "rejected": "REJECTED", "waitlisted": "WAITLISTED"}
MIN_REASON = 20


async def get_decision(db: OrgDb, decision_id: uuid.UUID, *, for_update: bool = False) -> Decision:
    stmt = select(Decision).where(Decision.id == decision_id)
    if for_update:
        stmt = stmt.with_for_update()  # hai người cùng duyệt: người sau chờ rồi thấy đề xuất đã xử lý
    decision = (await db.session.execute(stmt)).scalar_one_or_none()
    if decision is None:
        raise NotFoundError("Không tìm thấy đề xuất")
    return decision


async def pending_decision(db: OrgDb, application_id: uuid.UUID) -> Decision | None:
    return (
        await db.session.execute(
            select(Decision)
            .where(Decision.application_id == application_id, Decision.status == "pending")
            .order_by(Decision.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _forbid_own_application(app: Application, actor: Actor) -> None:
    """Xung đột lợi ích: người vừa là ứng viên vừa là nhân sự không được quyết định hồ sơ của chính mình."""
    if app.applicant_membership_id == actor.membership_id:
        raise PermissionDeniedError("Không được quyết định hồ sơ của chính mình (xung đột lợi ích)")


async def occupied_seats(db: OrgDb, intake_id: uuid.UUID) -> int:
    return (
        await db.session.execute(
            select(func.count())
            .select_from(Application)
            .where(Application.intake_id == intake_id, Application.status.in_(("ACCEPTED", "ENROLLED")))
        )
    ).scalar_one()


async def propose(
    db: OrgDb,
    app: Application,
    *,
    actor: Actor,
    outcome: str,
    reason: str,
    expected_version: int | None,
    meta: RequestMeta,
) -> Decision:
    assert actor.user_id is not None
    if outcome not in OUTCOME_TO_STATUS:
        raise ValidationFailedError(
            "Kết quả đề xuất không hợp lệ", {"outcome": "Chọn accepted, rejected hoặc waitlisted"}
        )
    if len(reason.strip()) < MIN_REASON:
        raise ValidationFailedError("Lý do đề xuất cần cụ thể", {"reason": f"Tối thiểu {MIN_REASON} ký tự"})
    _forbid_own_application(app, actor)

    intake = await get_intake(db, app.intake_id)
    if app.status == "IN_ROUND":
        reviews = await submitted_reviews(db, app)
        if len(reviews) < intake.min_reviews:
            raise ConflictError(f"Cần tối thiểu {intake.min_reviews} reviewer chốt điểm trước khi đề xuất")
    if await pending_decision(db, app.id) is not None:
        raise ConflictError("Hồ sơ đã có đề xuất đang chờ duyệt")

    decision = Decision(
        organization_id=db.org.id,
        application_id=app.id,
        proposed_outcome=outcome,
        proposed_by=actor.user_id,
        proposal_reason=reason.strip(),
        status="pending",
    )
    db.session.add(decision)
    try:
        await db.session.flush()
    except IntegrityError:
        raise ConflictError("Hồ sơ đã có đề xuất đang chờ duyệt") from None
    await apply_transition(
        db,
        app,
        "PENDING_APPROVAL",
        actor=actor,
        expected_version=expected_version,
        event_type="decision.proposed",
        payload={"outcome": outcome},
    )
    await db.session.flush()
    write_audit(
        db,
        action="decision.proposed",
        entity_type="application",
        entity_id=app.id,
        actor_user_id=actor.user_id,
        after={"outcome": outcome, "decision_id": str(decision.id)},
        meta=meta,
    )
    return decision


async def approve(
    db: OrgDb,
    decision: Decision,
    app: Application,
    *,
    actor: Actor,
    outcome: str,
    reason: str,
    applicant_message: str,
    expected_version: int | None,
    meta: RequestMeta,
) -> Application:
    assert actor.user_id is not None
    if decision.status != "pending":
        raise ConflictError("Đề xuất đã được xử lý")
    if decision.proposed_by == actor.user_id:
        raise PermissionDeniedError("Người đề xuất không được tự phê duyệt (nguyên tắc bốn mắt)")
    _forbid_own_application(app, actor)
    if outcome not in OUTCOME_TO_STATUS:
        raise ValidationFailedError("Kết quả không hợp lệ", {"outcome": "Chọn accepted, rejected hoặc waitlisted"})
    if len(reason.strip()) < MIN_REASON:
        raise ValidationFailedError("Lý do quyết định cần cụ thể", {"reason": f"Tối thiểu {MIN_REASON} ký tự"})
    if len(applicant_message.strip()) < 10:
        raise ValidationFailedError("Cần có lời nhắn gửi ứng viên", {"applicant_message": "Tối thiểu 10 ký tự"})

    intake = await get_intake(db, app.intake_id)
    if outcome == "accepted" and await occupied_seats(db, intake.id) >= intake.quota:
        raise ConflictError("Đã đủ chỉ tiêu của đợt tuyển. Hãy đưa hồ sơ vào danh sách chờ.")

    decision.status = "approved"
    decision.decided_outcome = outcome
    decision.decided_by = actor.user_id
    decision.decided_at = datetime.now(UTC)
    decision.decision_reason = reason.strip()
    decision.applicant_message = applicant_message.strip()

    await apply_transition(
        db,
        app,
        OUTCOME_TO_STATUS[outcome],
        actor=actor,
        expected_version=expected_version,
        event_type=f"decision.{outcome}",
        payload={"message": applicant_message.strip()},
        visible=True,
    )
    notify(
        db,
        app.applicant_membership_id,
        type=f"decision.{outcome}",
        title={
            "accepted": "Chúc mừng, hồ sơ của bạn được nhận",
            "rejected": "Kết quả xét tuyển",
            "waitlisted": "Hồ sơ của bạn trong danh sách chờ",
        }[outcome],
        body=applicant_message.strip(),
        link=f"/apply/{app.id}",
    )
    write_audit(
        db,
        action="decision.approved",
        entity_type="application",
        entity_id=app.id,
        actor_user_id=actor.user_id,
        after={
            "outcome": outcome,
            "proposed": decision.proposed_outcome,
            "overrode": outcome != decision.proposed_outcome,
        },
        meta=meta,
    )
    return app


async def return_to_review(
    db: OrgDb,
    decision: Decision,
    app: Application,
    *,
    actor: Actor,
    note: str,
    expected_version: int | None,
    meta: RequestMeta,
) -> Application:
    assert actor.user_id is not None
    if decision.status != "pending":
        raise ConflictError("Đề xuất đã được xử lý")
    _forbid_own_application(app, actor)
    if len(note.strip()) < 10:
        raise ValidationFailedError("Hãy nêu yêu cầu xem xét lại", {"note": "Tối thiểu 10 ký tự"})
    decision.status = "returned"
    decision.decided_by = actor.user_id
    decision.decided_at = datetime.now(UTC)
    decision.decision_reason = note.strip()
    await apply_transition(
        db,
        app,
        "IN_ROUND",
        actor=actor,
        expected_version=expected_version,
        next_round=app.current_round,
        event_type="decision.returned",
        payload={"note": note.strip()},
    )
    from src.models import OrgMembership

    proposer_membership = (
        await db.session.execute(select(OrgMembership.id).where(OrgMembership.user_id == decision.proposed_by))
    ).scalar_one_or_none()
    if proposer_membership:
        notify(
            db,
            proposer_membership,
            type="decision.returned",
            title=f"Đề xuất cho hồ sơ {app.candidate_code} bị trả lại",
            body=note.strip(),
            link=f"/staff/applications/{app.id}",
        )
    write_audit(
        db,
        action="decision.returned",
        entity_type="application",
        entity_id=app.id,
        actor_user_id=actor.user_id,
        meta=meta,
    )
    return app
