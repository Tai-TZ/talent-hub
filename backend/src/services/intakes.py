"""Quản lý đợt tuyển, rubric và khởi động vòng xét. Chỉ người có quyền `intake.manage` được ghi."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update

from src.errors import ConflictError, NotFoundError, ValidationFailedError
from src.models import Application, Cohort, Intake, Program, Review, Rubric
from src.schemas.intake import IntakeIn, IntakePatch, RubricIn
from src.services.audit import RequestMeta, write_audit
from src.services.tenancy import OrgDb


async def get_intake(db: OrgDb, intake_id: uuid.UUID, *, for_update: bool = False) -> Intake:
    stmt = select(Intake).where(Intake.id == intake_id)
    if for_update:
        stmt = stmt.with_for_update()
    intake = (await db.session.execute(stmt)).scalar_one_or_none()
    if intake is None:
        raise NotFoundError("Không tìm thấy đợt tuyển")
    return intake


async def create_intake(db: OrgDb, data: IntakeIn, *, actor_user_id: uuid.UUID, meta: RequestMeta) -> Intake:
    program = (await db.session.execute(select(Program).where(Program.id == data.program_id))).scalar_one_or_none()
    if program is None:
        raise ValidationFailedError("Chương trình không tồn tại", {"program_id": "Không tồn tại"})
    if data.cohort_id is not None:
        cohort = (
            await db.session.execute(
                select(Cohort).where(Cohort.id == data.cohort_id, Cohort.program_id == data.program_id)
            )
        ).scalar_one_or_none()
        if cohort is None:
            raise ValidationFailedError("Khoá học không thuộc chương trình này", {"cohort_id": "Không hợp lệ"})

    intake = Intake(
        organization_id=db.org.id,
        program_id=data.program_id,
        cohort_id=data.cohort_id,
        name=data.name,
        description=data.description,
        opens_at=data.opens_at,
        closes_at=data.closes_at,
        quota=data.quota,
        rounds=[r.model_dump() for r in data.rounds],
        approval_mode=data.approval_mode,
        ai_screening_enabled=data.ai_screening_enabled,
        blind_review=data.blind_review,
        min_reviews=data.min_reviews,
        eligibility_rules=[r.model_dump() for r in data.eligibility_rules],
        triage_config=data.triage_config.stored(),
        status="draft",
    )
    db.session.add(intake)
    await db.session.flush()
    write_audit(
        db, action="intake.created", entity_type="intake", entity_id=intake.id, actor_user_id=actor_user_id, meta=meta
    )
    return intake


async def update_intake(
    db: OrgDb, intake_id: uuid.UUID, patch: IntakePatch, *, actor_user_id: uuid.UUID, meta: RequestMeta
) -> Intake:
    intake = await get_intake(db, intake_id)
    if intake.status in ("closed", "archived"):
        raise ConflictError("Đợt tuyển đã đóng, không thể sửa")
    changes = patch.model_dump(exclude_unset=True)
    if "closes_at" in changes and changes["closes_at"] is not None and changes["closes_at"] <= intake.opens_at:
        raise ValidationFailedError("Hạn đóng phải sau ngày mở", {"closes_at": "Phải sau ngày mở"})
    if "eligibility_rules" in changes and changes["eligibility_rules"] is not None:
        changes["eligibility_rules"] = [
            r.model_dump() if hasattr(r, "model_dump") else r for r in patch.eligibility_rules or []
        ]
    if patch.triage_config is not None:
        changes["triage_config"] = patch.triage_config.stored()
    before = {k: str(getattr(intake, k)) for k in changes}
    for key, value in changes.items():
        if value is not None:
            setattr(intake, key, value)
    await db.session.flush()
    write_audit(
        db,
        action="intake.updated",
        entity_type="intake",
        entity_id=intake.id,
        actor_user_id=actor_user_id,
        before=before,
        after={k: str(v) for k, v in changes.items()},
        meta=meta,
    )
    return intake


async def active_rubric(db: OrgDb, intake_id: uuid.UUID, round_key: str) -> Rubric | None:
    return (
        await db.session.execute(
            select(Rubric)
            .where(Rubric.intake_id == intake_id, Rubric.round == round_key, Rubric.is_active.is_(True))
            .order_by(Rubric.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def set_rubric(
    db: OrgDb, intake_id: uuid.UUID, round_key: str, data: RubricIn, *, actor_user_id: uuid.UUID, meta: RequestMeta
) -> Rubric:
    """Tạo phiên bản rubric mới. Không cho đổi khi vòng đó đã có điểm được chốt (giữ tính nhất quán)."""
    intake = await get_intake(db, intake_id)
    if round_key not in {r["key"] for r in intake.rounds}:
        raise ValidationFailedError("Vòng không thuộc đợt tuyển", {"round": "Không hợp lệ"})
    submitted = (
        await db.session.execute(
            select(func.count())
            .select_from(Review)
            .join(Application, Application.id == Review.application_id)
            .where(Application.intake_id == intake_id, Review.round == round_key, Review.submitted_at.is_not(None))
        )
    ).scalar_one()
    if submitted:
        raise ConflictError("Vòng này đã có điểm được chốt, không thể đổi rubric")

    current = await active_rubric(db, intake_id, round_key)
    version = (current.version + 1) if current else 1
    if current:
        await db.session.execute(update(Rubric).where(Rubric.id == current.id).values(is_active=False))
    rubric = Rubric(
        organization_id=db.org.id,
        intake_id=intake_id,
        round=round_key,
        version=version,
        criteria=[c.model_dump() for c in data.criteria],
        is_active=True,
    )
    db.session.add(rubric)
    await db.session.flush()
    write_audit(
        db,
        action="rubric.saved",
        entity_type="intake",
        entity_id=intake_id,
        actor_user_id=actor_user_id,
        after={"round": round_key, "version": version, "criteria": len(data.criteria)},
        meta=meta,
    )
    return rubric


async def publish(db: OrgDb, intake_id: uuid.UUID, *, actor_user_id: uuid.UUID, meta: RequestMeta) -> Intake:
    intake = await get_intake(db, intake_id)
    if intake.status != "draft":
        raise ConflictError("Chỉ đợt tuyển nháp mới được mở")
    missing = []
    for round_def in intake.rounds:
        rubric = await active_rubric(db, intake_id, round_def["key"])
        if rubric is None:
            missing.append(round_def["label"])
    if missing:
        raise ValidationFailedError("Mỗi vòng cần có rubric trước khi mở đợt tuyển", {"rounds": ", ".join(missing)})
    intake.status = "open"
    await db.session.flush()
    write_audit(
        db, action="intake.published", entity_type="intake", entity_id=intake.id, actor_user_id=actor_user_id, meta=meta
    )
    return intake


async def close(db: OrgDb, intake_id: uuid.UUID, *, actor_user_id: uuid.UUID, meta: RequestMeta) -> Intake:
    intake = await get_intake(db, intake_id)
    if intake.status != "open":
        raise ConflictError("Chỉ đợt tuyển đang mở mới được đóng")
    intake.status = "closed"
    await db.session.flush()
    write_audit(
        db, action="intake.closed", entity_type="intake", entity_id=intake.id, actor_user_id=actor_user_id, meta=meta
    )
    return intake


def is_accepting(intake: Intake, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return intake.status == "open" and intake.opens_at <= now < intake.closes_at


async def start_first_round(db: OrgDb, intake_id: uuid.UUID, *, actor_user_id: uuid.UUID, meta: RequestMeta) -> int:
    """Đưa mọi hồ sơ SUBMITTED sang vòng đầu bằng một câu lệnh (đủ nhanh cho hàng nghìn hồ sơ).

    Chỉ cho phép sau khi đợt tuyển đã đóng để mọi ứng viên được xét trong cùng điều kiện.
    """
    intake = await get_intake(db, intake_id)
    if intake.status != "closed":
        raise ConflictError("Hãy đóng đợt tuyển trước khi bắt đầu vòng xét")
    first = intake.rounds[0]["key"]
    result = await db.session.execute(
        text(
            """
            WITH moved AS (
              UPDATE applications
                 SET status = 'IN_ROUND', current_round = :round, version = version + 1, updated_at = now()
               WHERE intake_id = :intake AND status = 'SUBMITTED'
               RETURNING id
            )
            INSERT INTO application_events
              (id, organization_id, application_id, actor_user_id, type, from_status, to_status, payload, visible_to_applicant)
            SELECT gen_random_uuid(), :org, id, :actor, 'round.started', 'SUBMITTED', 'IN_ROUND',
                   jsonb_build_object('round', CAST(:round AS text)), true
              FROM moved
            RETURNING 1
            """
        ),
        {"round": first, "intake": intake_id, "org": db.org.id, "actor": actor_user_id},
    )
    moved = len(result.all())
    write_audit(
        db,
        action="intake.round_started",
        entity_type="intake",
        entity_id=intake_id,
        actor_user_id=actor_user_id,
        after={"round": first, "applications": moved},
        meta=meta,
    )
    return moved
