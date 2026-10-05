"""Vòng đời hồ sơ phía ứng viên: tạo nháp, lưu, nộp, bổ sung, rút."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from src.models import Application, ApplicationEvent, Intake
from src.schemas.application import Content, Profile, submission_errors
from src.services import eligibility
from src.services.audit import RequestMeta, write_audit
from src.services.intakes import get_intake, is_accepting
from src.services.notifications import notify
from src.services.tenancy import OrgDb
from src.services.workflow import Actor, apply_transition

EDITABLE = ("DRAFT", "NEEDS_INFO")


def candidate_code(application_id: uuid.UUID) -> str:
    """Mã ẩn danh ổn định dùng khi chấm mù; không suy ngược được ra người."""
    return "A-" + hashlib.sha256(application_id.bytes).hexdigest()[:6].upper()


async def get_application(db: OrgDb, application_id: uuid.UUID) -> Application:
    app = (await db.session.execute(select(Application).where(Application.id == application_id))).scalar_one_or_none()
    if app is None:
        raise NotFoundError("Không tìm thấy hồ sơ")
    return app


async def get_own_application(db: OrgDb, application_id: uuid.UUID, membership_id: uuid.UUID) -> Application:
    app = await get_application(db, application_id)
    if app.applicant_membership_id != membership_id:
        # Trả 404 thay vì 403 để không lộ sự tồn tại của hồ sơ người khác.
        raise NotFoundError("Không tìm thấy hồ sơ")
    return app


async def create_draft(
    db: OrgDb, *, intake_id: uuid.UUID, membership_id: uuid.UUID, user_id: uuid.UUID, full_name: str, meta: RequestMeta
) -> Application:
    intake = await get_intake(db, intake_id)
    existing = (
        await db.session.execute(
            select(Application).where(
                Application.intake_id == intake_id, Application.applicant_membership_id == membership_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing  # idempotent: mỗi người một hồ sơ cho mỗi đợt
    if not is_accepting(intake):
        raise ValidationFailedError("Đợt tuyển chưa mở hoặc đã đóng nhận hồ sơ")

    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        organization_id=db.org.id,
        intake_id=intake_id,
        applicant_membership_id=membership_id,
        status="DRAFT",
        candidate_code=candidate_code(app_id),
        profile={"full_name": full_name},
        content={},
    )
    db.session.add(app)
    try:
        await db.session.flush()
    except IntegrityError:
        # Hai yêu cầu đồng thời cùng tạo: giữ bản ghi thắng cuộc.
        await db.session.rollback()
        raise ConflictError("Hồ sơ đã được tạo, hãy tải lại trang") from None
    db.session.add(
        ApplicationEvent(
            organization_id=db.org.id,
            application_id=app.id,
            actor_user_id=user_id,
            type="application.created",
            to_status="DRAFT",
            visible_to_applicant=True,
        )
    )
    write_audit(
        db, action="application.created", entity_type="application", entity_id=app.id, actor_user_id=user_id, meta=meta
    )
    return app


def _parse(model: type[Profile] | type[Content], raw: dict[str, Any], prefix: str) -> Profile | Content:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        fields = {f"{prefix}.{'.'.join(str(p) for p in e['loc'])}": e["msg"] for e in exc.errors()}
        raise ValidationFailedError("Thông tin hồ sơ chưa hợp lệ", fields) from None


async def save_draft(
    db: OrgDb, app: Application, *, profile: dict[str, Any] | None, content: dict[str, Any] | None
) -> Application:
    if app.status not in EDITABLE:
        raise ConflictError("Hồ sơ đã nộp, không thể chỉnh sửa")
    intake = await get_intake(db, app.intake_id)
    if app.status == "DRAFT" and not is_accepting(intake):
        raise ConflictError("Đợt tuyển đã đóng nhận hồ sơ")
    if profile is not None:
        app.profile = _parse(Profile, profile, "profile").model_dump(mode="json", exclude_none=True)
    if content is not None:
        app.content = _parse(Content, content, "content").model_dump(mode="json", exclude_none=True)
    await db.session.flush()
    return app


async def submit(
    db: OrgDb, app: Application, *, actor: Actor, consent: bool, expected_version: int | None, meta: RequestMeta
) -> Application:
    if not consent:
        raise ValidationFailedError(
            "Bạn cần đồng ý với việc xử lý dữ liệu cá nhân để nộp hồ sơ", {"consent": "Bắt buộc"}
        )
    intake = await get_intake(db, app.intake_id)
    if not is_accepting(intake):
        raise ConflictError("Đợt tuyển đã đóng nhận hồ sơ")

    profile = _parse(Profile, app.profile, "profile") if app.profile else None
    content = _parse(Content, app.content, "content") if app.content else None
    assert profile is None or isinstance(profile, Profile)
    assert content is None or isinstance(content, Content)
    errors = submission_errors(profile, content)
    if errors:
        raise ValidationFailedError("Hồ sơ chưa đủ thông tin để nộp", errors)
    assert content is not None

    app.flags = eligibility.evaluate(intake.eligibility_rules, content)
    app.consented_at = datetime.now(UTC)
    app.submitted_at = app.consented_at
    await apply_transition(
        db, app, "SUBMITTED", actor=actor, expected_version=expected_version, event_type="application.submitted"
    )
    notify(
        db,
        app.applicant_membership_id,
        type="application.submitted",
        title="Đã nhận hồ sơ của bạn",
        body=f"Mã hồ sơ {app.candidate_code}. Chúng tôi sẽ thông báo khi có cập nhật.",
        link=f"/apply/{app.id}",
    )
    write_audit(
        db,
        action="application.submitted",
        entity_type="application",
        entity_id=app.id,
        actor_user_id=actor.user_id,
        meta=meta,
    )
    return app


async def resubmit_after_info(
    db: OrgDb, app: Application, *, actor: Actor, expected_version: int | None
) -> Application:
    """Ứng viên bổ sung thông tin theo yêu cầu: quay lại đúng vòng đang xét."""
    if app.status != "NEEDS_INFO":
        raise ConflictError("Hồ sơ không ở trạng thái cần bổ sung")
    last_round = (
        await db.session.execute(
            select(ApplicationEvent.payload)
            .where(ApplicationEvent.application_id == app.id, ApplicationEvent.to_status == "NEEDS_INFO")
            .order_by(ApplicationEvent.at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    round_key = (last_round or {}).get("from_round") or app.current_round
    return await apply_transition(
        db,
        app,
        "IN_ROUND",
        actor=actor,
        expected_version=expected_version,
        next_round=round_key,
        event_type="application.info_provided",
    )


async def withdraw(db: OrgDb, app: Application, *, actor: Actor, reason: str | None, meta: RequestMeta) -> Application:
    await apply_transition(
        db, app, "WITHDRAWN", actor=actor, event_type="application.withdrawn", payload={"reason": reason or ""}
    )
    write_audit(
        db,
        action="application.withdrawn",
        entity_type="application",
        entity_id=app.id,
        actor_user_id=actor.user_id,
        meta=meta,
    )
    return app


async def timeline(db: OrgDb, app: Application, *, applicant_view: bool) -> list[ApplicationEvent]:
    stmt = (
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app.id)
        .order_by(ApplicationEvent.at, ApplicationEvent.id)
    )
    if applicant_view:
        stmt = stmt.where(ApplicationEvent.visible_to_applicant.is_(True))
    return list((await db.session.execute(stmt)).scalars().all())


def application_view(app: Application, intake: Intake, *, can_see_pii: bool, owner: bool) -> dict[str, Any]:
    """Dữ liệu hồ sơ trả về cho client. Chấm mù: staff không có `pii.read` không thấy profile và liên kết cá nhân."""
    show_identity = owner or can_see_pii or not intake.blind_review
    content = dict(app.content or {})
    if not show_identity and "links" in content:
        content["links"] = {k: ("(ẩn)" if v else None) for k, v in content["links"].items()}
    return {
        "id": app.id,
        "candidate_code": app.candidate_code,
        "status": app.status,
        "current_round": app.current_round,
        "version": app.version,
        "intake": {"id": intake.id, "name": intake.name, "rounds": intake.rounds, "blind_review": intake.blind_review},
        "profile": app.profile if show_identity else None,
        "content": content,
        "flags": app.flags,
        "submitted_at": app.submitted_at,
        "owner": owner,
    }


def ensure_staff_can_view(actor: Actor) -> None:
    if "application.read" not in actor.permissions:
        raise PermissionDeniedError("Không đủ quyền xem hồ sơ")
