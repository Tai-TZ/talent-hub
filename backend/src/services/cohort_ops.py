"""Vận hành khoá học sau khi nhận: nhập học, nhánh, lớp, đối tác, đánh giá năng lực, xét đạt, phụ cấp."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from src.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from src.models import (
    Application,
    Cohort,
    CohortClass,
    CohortTrack,
    Competency,
    CompetencyAssessment,
    CostEntry,
    Enrollment,
    Intake,
    OrgMembership,
    Partner,
    PartnerDemand,
    Placement,
    StipendEntry,
    Track,
    TrackTarget,
    User,
)
from src.services import org_settings
from src.services.audit import RequestMeta, write_audit
from src.services.notifications import notify
from src.services.sqlutil import LIKE_ESCAPE, contains_pattern
from src.services.tenancy import OrgDb
from src.services.workflow import Actor, apply_transition


async def get_cohort(db: OrgDb, cohort_id: uuid.UUID) -> Cohort:
    cohort = (await db.session.execute(select(Cohort).where(Cohort.id == cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise NotFoundError("Không tìm thấy khoá học")
    return cohort


async def get_enrollment(db: OrgDb, enrollment_id: uuid.UUID) -> Enrollment:
    row = (await db.session.execute(select(Enrollment).where(Enrollment.id == enrollment_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Không tìm thấy học viên")
    return row


# ---------- Nhập học ----------
async def enroll_application(db: OrgDb, app: Application, *, actor: Actor, meta: RequestMeta) -> Enrollment:
    intake = (await db.session.execute(select(Intake).where(Intake.id == app.intake_id))).scalar_one()
    if intake.cohort_id is None:
        raise ValidationFailedError(
            "Đợt tuyển chưa gắn với khoá học nào", {"cohort": "Gắn khoá học cho đợt tuyển trước"}
        )
    await apply_transition(db, app, "ENROLLED", actor=actor, event_type="application.enrolled")
    enrollment = Enrollment(
        organization_id=db.org.id,
        application_id=app.id,
        membership_id=app.applicant_membership_id,
        cohort_id=intake.cohort_id,
        status="active",
    )
    db.session.add(enrollment)
    await db.session.flush()
    notify(
        db,
        app.applicant_membership_id,
        type="application.enrolled",
        title="Bạn đã được nhập học",
        body="Chào mừng bạn đến với khoá học. Thông tin lớp và nhánh sẽ được thông báo.",
        link=f"/apply/{app.id}",
    )
    write_audit(
        db,
        action="enrollment.created",
        entity_type="enrollment",
        entity_id=enrollment.id,
        actor_user_id=actor.user_id,
        after={"application_id": str(app.id)},
        meta=meta,
    )
    return enrollment


async def enroll_all_accepted(db: OrgDb, cohort_id: uuid.UUID, *, actor: Actor, meta: RequestMeta) -> int:
    await get_cohort(db, cohort_id)
    apps = (
        (
            await db.session.execute(
                select(Application)
                .join(Intake, Intake.id == Application.intake_id)
                .where(Intake.cohort_id == cohort_id, Application.status == "ACCEPTED")
                .order_by(Application.id)
            )
        )
        .scalars()
        .all()
    )
    for app in apps:
        await enroll_application(db, app, actor=actor, meta=meta)
    return len(apps)


# ---------- Danh sách học viên ----------
async def list_enrollments(
    db: OrgDb,
    cohort_id: uuid.UUID,
    *,
    status: str | None,
    class_id: uuid.UUID | None,
    track_id: uuid.UUID | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    conditions = [Enrollment.cohort_id == cohort_id]
    if status:
        conditions.append(Enrollment.status == status)
    if class_id:
        conditions.append(Enrollment.class_id == class_id)
    if track_id:
        conditions.append(Enrollment.track_id == track_id)
    if q:
        like = contains_pattern(q)
        conditions.append(
            User.full_name.ilike(like, escape=LIKE_ESCAPE)
            | User.email.ilike(like, escape=LIKE_ESCAPE)
            | Application.candidate_code.ilike(like, escape=LIKE_ESCAPE)
        )
    base = (
        select(Enrollment, User, Application)
        .join(OrgMembership, OrgMembership.id == Enrollment.membership_id)
        .join(User, User.id == OrgMembership.user_id)
        .join(Application, Application.id == Enrollment.application_id)
        .where(*conditions)
    )
    total = (await db.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.session.execute(base.order_by(User.full_name, Enrollment.id).limit(limit).offset(offset))).all()
    return (
        [
            {
                "id": e.id,
                "name": u.full_name,
                "email": u.email,
                "candidate_code": a.candidate_code,
                "status": e.status,
                "class_id": e.class_id,
                "track_id": e.track_id,
                "enrolled_at": e.enrolled_at,
            }
            for e, u, a in rows
        ],
        total,
    )


async def cohort_overview(db: OrgDb, cohort_id: uuid.UUID) -> dict[str, Any]:
    cohort = await get_cohort(db, cohort_id)
    status = dict(
        (
            await db.session.execute(
                select(Enrollment.status, func.count())
                .where(Enrollment.cohort_id == cohort_id)
                .group_by(Enrollment.status)
            )
        ).all()
    )
    classes = (
        (
            await db.session.execute(
                select(CohortClass).where(CohortClass.cohort_id == cohort_id).order_by(CohortClass.level)
            )
        )
        .scalars()
        .all()
    )
    class_counts = dict(
        (
            await db.session.execute(
                select(Enrollment.class_id, func.count())
                .where(Enrollment.cohort_id == cohort_id, Enrollment.class_id.is_not(None))
                .group_by(Enrollment.class_id)
            )
        ).all()
    )
    tracks = (
        await db.session.execute(
            select(Track, CohortTrack.capacity)
            .outerjoin(CohortTrack, (CohortTrack.track_id == Track.id) & (CohortTrack.cohort_id == cohort_id))
            .order_by(Track.key)
        )
    ).all()
    track_counts = dict(
        (
            await db.session.execute(
                select(Enrollment.track_id, func.count())
                .where(Enrollment.cohort_id == cohort_id, Enrollment.track_id.is_not(None))
                .group_by(Enrollment.track_id)
            )
        ).all()
    )
    unplaced = (
        await db.session.execute(
            select(func.count())
            .select_from(Enrollment)
            .outerjoin(Placement, Placement.enrollment_id == Enrollment.id)
            .where(Enrollment.cohort_id == cohort_id, Enrollment.status == "active", Placement.id.is_(None))
        )
    ).scalar_one()
    accepted_waiting = (
        await db.session.execute(
            select(func.count())
            .select_from(Application)
            .join(Intake, Intake.id == Application.intake_id)
            .where(Intake.cohort_id == cohort_id, Application.status == "ACCEPTED")
        )
    ).scalar_one()
    return {
        "cohort": {
            "id": cohort.id,
            "code": cohort.code,
            "name": cohort.name,
            "capacity": cohort.capacity,
            "starts_on": cohort.starts_on,
            "status": cohort.status,
        },
        "enrollments": status,
        "accepted_waiting_enrollment": accepted_waiting,
        "classes": [
            {
                "id": c.id,
                "name": c.name,
                "level": c.level,
                "capacity": c.capacity,
                "assigned": class_counts.get(c.id, 0),
            }
            for c in classes
        ],
        "tracks": [
            {"id": t.id, "key": t.key, "name": t.name, "capacity": cap, "assigned": track_counts.get(t.id, 0)}
            for t, cap in tracks
        ],
        "unplaced": unplaced,
    }


# ---------- Nhánh, lớp ----------
async def upsert_track(
    db: OrgDb,
    *,
    program_id: uuid.UUID,
    key: str,
    name_vi: str,
    keywords: list[str],
    actor_user_id: uuid.UUID,
    meta: RequestMeta,
) -> Track:
    track = (
        await db.session.execute(select(Track).where(Track.program_id == program_id, Track.key == key))
    ).scalar_one_or_none()
    if track is None:
        track = Track(
            organization_id=db.org.id,
            program_id=program_id,
            key=key,
            name={"vi": name_vi, "en": name_vi},
            keywords=keywords,
        )
        db.session.add(track)
    else:
        track.name = {**track.name, "vi": name_vi}
        track.keywords = keywords
    await db.session.flush()
    write_audit(
        db, action="track.saved", entity_type="track", entity_id=track.id, actor_user_id=actor_user_id, meta=meta
    )
    return track


async def set_cohort_track_capacity(db: OrgDb, cohort_id: uuid.UUID, track_id: uuid.UUID, capacity: int) -> None:
    from sqlalchemy.dialects.postgresql import insert

    await get_cohort(db, cohort_id)
    stmt = insert(CohortTrack).values(
        organization_id=db.org.id, cohort_id=cohort_id, track_id=track_id, capacity=capacity
    )
    await db.session.execute(
        stmt.on_conflict_do_update(
            index_elements=[CohortTrack.cohort_id, CohortTrack.track_id], set_={"capacity": capacity}
        )
    )


async def create_class(db: OrgDb, cohort_id: uuid.UUID, *, name: str, level: int, capacity: int) -> CohortClass:
    await get_cohort(db, cohort_id)
    row = CohortClass(organization_id=db.org.id, cohort_id=cohort_id, name=name.strip(), level=level, capacity=capacity)
    db.session.add(row)
    try:
        await db.session.flush()
    except Exception:
        raise ConflictError("Tên lớp đã tồn tại trong khoá này") from None
    return row


async def assign_enrollment(
    db: OrgDb,
    enrollment_id: uuid.UUID,
    *,
    class_id: uuid.UUID | None,
    track_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
    meta: RequestMeta,
) -> Enrollment:
    enrollment = await get_enrollment(db, enrollment_id)
    if enrollment.status != "active":
        raise ConflictError("Chỉ học viên đang học mới được xếp lại")
    before = {"class_id": str(enrollment.class_id), "track_id": str(enrollment.track_id)}
    if class_id is not None:
        klass = (
            await db.session.execute(
                select(CohortClass).where(CohortClass.id == class_id, CohortClass.cohort_id == enrollment.cohort_id)
            )
        ).scalar_one_or_none()
        if klass is None:
            raise ValidationFailedError("Lớp không thuộc khoá này", {"class_id": "Không hợp lệ"})
        count = (
            await db.session.execute(
                select(func.count()).select_from(Enrollment).where(Enrollment.class_id == class_id)
            )
        ).scalar_one()
        if count >= klass.capacity and enrollment.class_id != class_id:
            raise ConflictError("Lớp đã đủ sức chứa")
        enrollment.class_id = class_id
    if track_id is not None:
        cap = (
            await db.session.execute(
                select(CohortTrack.capacity).where(
                    CohortTrack.cohort_id == enrollment.cohort_id, CohortTrack.track_id == track_id
                )
            )
        ).scalar_one_or_none()
        if cap is None:
            raise ValidationFailedError("Nhánh chưa được mở cho khoá này", {"track_id": "Không hợp lệ"})
        count = (
            await db.session.execute(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.cohort_id == enrollment.cohort_id, Enrollment.track_id == track_id)
            )
        ).scalar_one()
        if count >= cap and enrollment.track_id != track_id:
            raise ConflictError("Nhánh đã đủ sức chứa")
        enrollment.track_id = track_id
    write_audit(
        db,
        action="enrollment.assigned",
        entity_type="enrollment",
        entity_id=enrollment.id,
        actor_user_id=actor_user_id,
        before=before,
        after={"class_id": str(enrollment.class_id), "track_id": str(enrollment.track_id)},
        meta=meta,
    )
    return enrollment


# ---------- Đối tác và thực chiến ----------
async def upsert_partner(
    db: OrgDb, *, name: str, skills: list[str], actor_user_id: uuid.UUID, meta: RequestMeta
) -> Partner:
    name = name.strip()
    if not name:
        raise ValidationFailedError("Tên đối tác không hợp lệ", {"name": "Bắt buộc"})
    partner = (await db.session.execute(select(Partner).where(Partner.name == name))).scalar_one_or_none()
    if partner is None:
        partner = Partner(
            organization_id=db.org.id, name=name, skills=[s.strip().lower() for s in skills if s.strip()][:30]
        )
        db.session.add(partner)
    else:
        partner.skills = [s.strip().lower() for s in skills if s.strip()][:30]
    await db.session.flush()
    write_audit(
        db, action="partner.saved", entity_type="partner", entity_id=partner.id, actor_user_id=actor_user_id, meta=meta
    )
    return partner


async def set_partner_demand(
    db: OrgDb, cohort_id: uuid.UUID, partner_id: uuid.UUID, track_id: uuid.UUID, slots: int
) -> None:
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(PartnerDemand).values(
        organization_id=db.org.id, cohort_id=cohort_id, partner_id=partner_id, track_id=track_id, slots=slots
    )
    await db.session.execute(
        stmt.on_conflict_do_update(
            index_elements=[PartnerDemand.cohort_id, PartnerDemand.partner_id, PartnerDemand.track_id],
            set_={"slots": slots},
        )
    )


async def place(
    db: OrgDb,
    enrollment_id: uuid.UUID,
    *,
    partner_id: uuid.UUID,
    mentor_membership_id: uuid.UUID | None,
    project: str,
    actor_user_id: uuid.UUID,
    meta: RequestMeta,
) -> Placement:
    enrollment = await get_enrollment(db, enrollment_id)
    existing = (
        await db.session.execute(select(Placement).where(Placement.enrollment_id == enrollment_id))
    ).scalar_one_or_none()
    if existing is None:
        existing = Placement(
            organization_id=db.org.id,
            enrollment_id=enrollment_id,
            partner_id=partner_id,
            mentor_membership_id=mentor_membership_id,
            project=project.strip()[:300],
        )
        db.session.add(existing)
    else:
        existing.partner_id, existing.mentor_membership_id, existing.project = (
            partner_id,
            mentor_membership_id,
            project.strip()[:300],
        )
    await db.session.flush()
    write_audit(
        db,
        action="placement.saved",
        entity_type="enrollment",
        entity_id=enrollment.id,
        actor_user_id=actor_user_id,
        after={"partner_id": str(partner_id)},
        meta=meta,
    )
    return existing


# ---------- Năng lực và xét đạt ----------
async def _targets_by_track(db: OrgDb, track_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[tuple[Competency, int]]]:
    """Năng lực mục tiêu của các nhánh bằng MỘT truy vấn."""
    if not track_ids:
        return {}
    rows = (
        await db.session.execute(
            select(TrackTarget.track_id, Competency, TrackTarget.target_level)
            .join(Competency, Competency.id == TrackTarget.competency_id)
            .where(TrackTarget.track_id.in_(track_ids))
            .order_by(Competency.code)
        )
    ).all()
    out: dict[uuid.UUID, list[tuple[Competency, int]]] = {}
    for track_id, competency, target in rows:
        out.setdefault(track_id, []).append((competency, target))
    return out


async def _latest_assessments(
    db: OrgDb, enrollment_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[uuid.UUID, tuple[int, str]]]:
    """Mức đánh giá mới nhất của từng (học viên, năng lực) bằng MỘT truy vấn (lịch sử chỉ thêm nên lấy bản ghi cuối)."""
    if not enrollment_ids:
        return {}
    rows = (
        await db.session.execute(
            select(
                CompetencyAssessment.enrollment_id,
                CompetencyAssessment.competency_id,
                CompetencyAssessment.level,
                CompetencyAssessment.evidence,
            )
            .where(CompetencyAssessment.enrollment_id.in_(enrollment_ids))
            .order_by(CompetencyAssessment.assessed_at, CompetencyAssessment.id)
        )
    ).all()
    out: dict[uuid.UUID, dict[uuid.UUID, tuple[int, str]]] = {}
    for enrollment_id, competency_id, level, evidence in rows:
        out.setdefault(enrollment_id, {})[competency_id] = (level, evidence)
    return out


def _matrix(targets: list[tuple[Competency, int]], latest: dict[uuid.UUID, tuple[int, str]]) -> list[dict[str, Any]]:
    return [
        {
            "competency_id": c.id,
            "code": c.code,
            "name": c.name,
            "target": target,
            "max_level": c.max_level,
            "level": latest.get(c.id, (None, ""))[0],
            "evidence": latest.get(c.id, (None, ""))[1],
            "met": (latest[c.id][0] >= target) if c.id in latest else None,
        }
        for c, target in targets
    ]


async def competency_matrix(db: OrgDb, enrollment: Enrollment) -> list[dict[str, Any]]:
    """Mức mới nhất của từng năng lực mục tiêu của nhánh học viên so với mức yêu cầu."""
    if enrollment.track_id is None:
        return []
    targets = await _targets_by_track(db, {enrollment.track_id})
    latest = await _latest_assessments(db, [enrollment.id])
    return _matrix(targets.get(enrollment.track_id, []), latest.get(enrollment.id, {}))


def suggestion_from(matrix: list[dict[str, Any]]) -> str:
    if not matrix:
        return "no_targets"
    if any(m["level"] is None for m in matrix):
        return "pending"
    return "qualified" if all(m["met"] for m in matrix) else "not_qualified"


async def can_assess(db: OrgDb, actor: Actor, enrollment_id: uuid.UUID) -> bool:
    """Mentor chỉ làm việc với học viên mình phụ trách (qua vị trí thực chiến); quản lý đào tạo thì với tất cả."""
    if "training.manage" in actor.permissions:
        return True
    mine = await db.session.execute(
        select(Placement.id)
        .where(Placement.enrollment_id == enrollment_id, Placement.mentor_membership_id == actor.membership_id)
        .limit(1)
    )
    return mine.first() is not None


async def add_assessment(
    db: OrgDb,
    enrollment_id: uuid.UUID,
    *,
    competency_id: uuid.UUID,
    level: int,
    evidence: str,
    assessor: Actor,
    meta: RequestMeta,
) -> CompetencyAssessment:
    assert assessor.membership_id is not None
    enrollment = await get_enrollment(db, enrollment_id)
    competency = (
        await db.session.execute(select(Competency).where(Competency.id == competency_id))
    ).scalar_one_or_none()
    if competency is None:
        raise ValidationFailedError("Năng lực không tồn tại", {"competency_id": "Không hợp lệ"})
    if not 1 <= level <= competency.max_level:
        raise ValidationFailedError("Mức không hợp lệ", {"level": f"Từ 1 đến {competency.max_level}"})
    if len(evidence.strip()) < 15:
        raise ValidationFailedError("Cần nêu bằng chứng cho mức đánh giá", {"evidence": "Tối thiểu 15 ký tự"})
    if not await can_assess(db, assessor, enrollment_id):
        raise PermissionDeniedError("Bạn chỉ đánh giá được học viên mình phụ trách")
    row = CompetencyAssessment(
        organization_id=db.org.id,
        enrollment_id=enrollment.id,
        competency_id=competency_id,
        level=level,
        evidence=evidence.strip(),
        assessor_membership_id=assessor.membership_id,
    )
    db.session.add(row)
    await db.session.flush()
    write_audit(
        db,
        action="competency.assessed",
        entity_type="enrollment",
        entity_id=enrollment.id,
        actor_user_id=assessor.user_id,
        after={"competency": competency.code, "level": level},
        meta=meta,
    )
    return row


async def qualification_report(db: OrgDb, cohort_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await db.session.execute(
            select(Enrollment, User.full_name, Application.candidate_code, Track.name)
            .join(OrgMembership, OrgMembership.id == Enrollment.membership_id)
            .join(User, User.id == OrgMembership.user_id)
            .join(Application, Application.id == Enrollment.application_id)
            .outerjoin(Track, Track.id == Enrollment.track_id)
            .where(Enrollment.cohort_id == cohort_id)
            .order_by(User.full_name, Enrollment.id)
        )
    ).all()
    targets = await _targets_by_track(db, {e.track_id for e, *_ in rows if e.track_id is not None})
    latest = await _latest_assessments(db, [e.id for e, *_ in rows])
    out = []
    for e, name, code, track_name in rows:
        matrix = _matrix(targets.get(e.track_id, []) if e.track_id else [], latest.get(e.id, {}))
        out.append(
            {
                "enrollment_id": e.id,
                "name": name,
                "candidate_code": code,
                "track_name": (track_name or {}).get("vi") if track_name else None,
                "status": e.status,
                "suggestion": suggestion_from(matrix),
                "met": sum(1 for m in matrix if m["met"]),
                "total": len(matrix),
            }
        )
    return out


async def decide_qualification(
    db: OrgDb, enrollment_id: uuid.UUID, *, outcome: str, reason: str, actor_user_id: uuid.UUID, meta: RequestMeta
) -> Enrollment:
    if outcome not in ("qualified", "not_qualified"):
        raise ValidationFailedError("Kết quả không hợp lệ", {"outcome": "Chọn qualified hoặc not_qualified"})
    if len(reason.strip()) < 10:
        raise ValidationFailedError("Cần ghi lý do", {"reason": "Tối thiểu 10 ký tự"})
    enrollment = (
        await db.session.execute(select(Enrollment).where(Enrollment.id == enrollment_id).with_for_update())
    ).scalar_one_or_none()
    if enrollment is None:
        raise NotFoundError("Không tìm thấy học viên")
    if enrollment.status != "active":
        raise ConflictError("Học viên đã được xét kết quả hoặc đã rút")
    if enrollment.track_id is None:
        raise ConflictError("Cần gán nhánh trước khi xét kết quả")
    suggestion = suggestion_from(await competency_matrix(db, enrollment))
    enrollment.status = outcome
    enrollment.qualification_reason = reason.strip()
    enrollment.qualification_decided_by = actor_user_id
    enrollment.qualification_decided_at = datetime.now(UTC)
    write_audit(
        db,
        action="enrollment.qualification_decided",
        entity_type="enrollment",
        entity_id=enrollment.id,
        actor_user_id=actor_user_id,
        after={
            "outcome": outcome,
            "suggestion": suggestion,
            "override": suggestion not in (outcome, "no_targets", "pending"),
        },
        meta=meta,
    )
    return enrollment


# ---------- Phụ cấp (chỉ ghi nhận) ----------
async def generate_stipends(
    db: OrgDb, cohort_id: uuid.UUID, period: str, *, actor_user_id: uuid.UUID, meta: RequestMeta
) -> int:
    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        raise ValidationFailedError("Kỳ phụ cấp không hợp lệ", {"period": "Định dạng YYYY-MM"}) from None
    amount = Decimal(str(await org_settings.get(db, "stipend_vnd_per_month")))
    enrollments = (
        (
            await db.session.execute(
                select(Enrollment.id).where(Enrollment.cohort_id == cohort_id, Enrollment.status == "active")
            )
        )
        .scalars()
        .all()
    )
    have = set(
        (
            await db.session.execute(
                select(StipendEntry.enrollment_id).where(
                    StipendEntry.period == period, StipendEntry.enrollment_id.in_(enrollments)
                )
            )
        )
        .scalars()
        .all()
    )
    created = 0
    for enrollment_id in enrollments:
        if enrollment_id in have:
            continue
        db.session.add(
            StipendEntry(
                organization_id=db.org.id,
                enrollment_id=enrollment_id,
                period=period,
                amount_vnd=amount,
                status="eligible",
            )
        )
        created += 1
    write_audit(
        db,
        action="stipend.generated",
        entity_type="cohort",
        entity_id=cohort_id,
        actor_user_id=actor_user_id,
        after={"period": period, "created": created},
        meta=meta,
    )
    return created


async def mark_stipends_paid(
    db: OrgDb, cohort_id: uuid.UUID, period: str, *, actor_user_id: uuid.UUID, meta: RequestMeta
) -> dict[str, Any]:
    """Đánh dấu đã chi cho kỳ; tạo một bút toán chi phí hệ thống cho mỗi khoản để sổ chi phí khớp. Chạy lại không tạo trùng."""
    rows = (
        (
            await db.session.execute(
                select(StipendEntry)
                .join(Enrollment, Enrollment.id == StipendEntry.enrollment_id)
                .where(
                    Enrollment.cohort_id == cohort_id, StipendEntry.period == period, StipendEntry.status == "eligible"
                )
                .with_for_update(of=StipendEntry)
            )
        )
        .scalars()
        .all()
    )
    total = Decimal(0)
    for row in rows:
        cost = CostEntry(
            organization_id=db.org.id,
            category="stipend",
            amount_vnd=row.amount_vnd,
            occurred_on=date.today(),
            cohort_id=cohort_id,
            description=f"Phụ cấp kỳ {period}",
            source="system",
            created_by=actor_user_id,
        )
        db.session.add(cost)
        await db.session.flush()
        row.status, row.paid_at, row.cost_entry_id = "paid", datetime.now(UTC), cost.id
        total += row.amount_vnd
    write_audit(
        db,
        action="stipend.marked_paid",
        entity_type="cohort",
        entity_id=cohort_id,
        actor_user_id=actor_user_id,
        after={"period": period, "count": len(rows), "total_vnd": str(total)},
        meta=meta,
    )
    return {"count": len(rows), "total_vnd": float(total)}


async def stipend_summary(db: OrgDb, cohort_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await db.session.execute(
            select(StipendEntry.period, StipendEntry.status, func.count(), func.sum(StipendEntry.amount_vnd))
            .join(Enrollment, Enrollment.id == StipendEntry.enrollment_id)
            .where(Enrollment.cohort_id == cohort_id)
            .group_by(StipendEntry.period, StipendEntry.status)
            .order_by(StipendEntry.period.desc())
        )
    ).all()
    return [{"period": p, "status": s, "count": c, "total_vnd": float(t)} for p, s, c, t in rows]
