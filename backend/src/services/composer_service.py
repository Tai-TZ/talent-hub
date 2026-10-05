"""Cầu nối giữa bộ giải (hàm thuần) và dữ liệu thật: nạp học viên, chạy, lưu phương án, áp dụng khi được xác nhận."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from src.ai.heuristic import RELEVANT_MAJORS
from src.composer.solver import ComposerError, Learner, Params, PartnerSlot, compose
from src.errors import ConflictError, NotFoundError, ValidationFailedError
from src.models import (
    AiAssessment,
    Application,
    CohortClass,
    CohortTrack,
    ComposerRun,
    Enrollment,
    Intake,
    Partner,
    PartnerDemand,
    Placement,
    Review,
    Track,
)
from src.services.audit import RequestMeta, write_audit
from src.services.cohort_ops import get_cohort
from src.services.tenancy import OrgDb


def _fit(keywords: list[str], text: str) -> float:
    if not keywords:
        return 0.0
    hits = sum(1 for k in keywords if k.lower() in text)
    return min(1.0, hits / max(3, min(len(keywords), 8)))


async def load_learners(db: OrgDb, cohort_id: uuid.UUID) -> tuple[list[Learner], dict[str, Track]]:
    tracks = {t.key: t for t in (await db.session.execute(select(Track))).scalars().all()}
    rows = (
        await db.session.execute(
            select(Enrollment, Application, Intake)
            .join(Application, Application.id == Enrollment.application_id)
            .join(Intake, Intake.id == Application.intake_id)
            .where(Enrollment.cohort_id == cohort_id, Enrollment.status == "active")
            .order_by(Enrollment.id)
        )
    ).all()
    app_ids = [a.id for _, a, _ in rows]
    reviews: dict[uuid.UUID, list[tuple[str, float]]] = {}
    for app_id, rnd, total in (
        await db.session.execute(
            select(Review.application_id, Review.round, Review.total_score).where(
                Review.application_id.in_(app_ids), Review.submitted_at.is_not(None), Review.total_score.is_not(None)
            )
        )
    ).all():
        reviews.setdefault(app_id, []).append((rnd, float(total or 0.0)))
    ai_scores = dict(
        (
            await db.session.execute(
                select(AiAssessment.application_id, func.max(AiAssessment.total_score))
                .where(AiAssessment.application_id.in_(app_ids))
                .group_by(AiAssessment.application_id)
            )
        ).all()
    )

    learners: list[Learner] = []
    for enrollment, app, intake in rows:
        keys = [r["key"] for r in intake.rounds]
        entries = reviews.get(app.id, [])
        last_round = max((r for r, _ in entries), key=lambda r: keys.index(r) if r in keys else -1, default=None)
        in_last = [t for r, t in entries if r == last_round]
        score = sum(in_last) / len(in_last) if in_last else float(ai_scores.get(app.id, 0.0))
        content = app.content or {}
        skills = {str(s).lower() for s in content.get("skills", [])}
        for project in content.get("projects", []):
            skills |= {str(t).lower() for t in project.get("tech", [])}
        text = " ".join(
            [" ".join(skills)]
            + [str(p.get("description", "")).lower() for p in content.get("projects", [])]
            + [str(content.get("essays", {}).get("motivation", "")).lower()]
        )
        prefs = tuple(t for t in (content.get("preferences", {}) or {}).get("tracks", []) if t in tracks)
        major = " ".join(str(e.get("major", "")).lower() for e in content.get("education", []))
        learners.append(
            Learner(
                id=str(enrollment.id),
                score=float(score),
                prefs=prefs,
                fit={key: _fit(list(track.keywords), text) for key, track in tracks.items()},
                skills=frozenset(skills),
                background="tech" if any(m in major for m in RELEVANT_MAJORS[:8]) else "non_tech",
            )
        )
    return learners, tracks


async def run(
    db: OrgDb, cohort_id: uuid.UUID, raw: dict[str, Any], *, actor_user_id: uuid.UUID, meta: RequestMeta
) -> ComposerRun:
    await get_cohort(db, cohort_id)
    learners, tracks = await load_learners(db, cohort_id)
    if not learners:
        raise ConflictError("Khoá chưa có học viên đang học để xếp")

    caps = {
        t.key: cap
        for t, cap in (
            await db.session.execute(
                select(Track, CohortTrack.capacity)
                .join(CohortTrack, CohortTrack.track_id == Track.id)
                .where(CohortTrack.cohort_id == cohort_id)
            )
        ).all()
    }
    caps = {**caps, **{k: int(v) for k, v in (raw.get("track_capacity") or {}).items() if k in tracks}}
    if not caps:
        raise ValidationFailedError(
            "Chưa cấu hình sức chứa nhánh cho khoá", {"track_capacity": "Thiết lập sức chứa các nhánh trước"}
        )

    demand_rows = (
        await db.session.execute(
            select(PartnerDemand, Partner, Track)
            .join(Partner, Partner.id == PartnerDemand.partner_id)
            .join(Track, Track.id == PartnerDemand.track_id)
            .where(PartnerDemand.cohort_id == cohort_id)
        )
    ).all()
    slots = [
        PartnerSlot(partner_id=str(p.id), track=t.key, slots=d.slots, skills=frozenset(p.skills))
        for d, p, t in demand_rows
    ]

    try:
        params = Params(
            track_capacity=caps,
            class_count=int(raw.get("class_count", 3)),
            class_mode=str(raw.get("class_mode", "levels")),
            pref_weight=float(raw.get("pref_weight", 0.6)),
            fit_weight=float(raw.get("fit_weight", 0.4)),
        )
        result = compose(learners, params, slots or None)
    except ComposerError as exc:
        raise ValidationFailedError(str(exc)) from None

    run_row = ComposerRun(
        organization_id=db.org.id,
        cohort_id=cohort_id,
        params={
            "track_capacity": caps,
            "class_count": params.class_count,
            "class_mode": params.class_mode,
            "pref_weight": params.pref_weight,
            "fit_weight": params.fit_weight,
        },
        metrics=result["metrics"],
        assignments=result["assignments"],
        created_by=actor_user_id,
    )
    db.session.add(run_row)
    await db.session.flush()
    write_audit(
        db,
        action="composer.run",
        entity_type="cohort",
        entity_id=cohort_id,
        actor_user_id=actor_user_id,
        after={"run_id": str(run_row.id), "learners": len(learners)},
        meta=meta,
    )
    return run_row


async def get_run(db: OrgDb, run_id: uuid.UUID) -> ComposerRun:
    row = (await db.session.execute(select(ComposerRun).where(ComposerRun.id == run_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Không tìm thấy phương án")
    return row


async def apply_run(db: OrgDb, run_id: uuid.UUID, *, actor_user_id: uuid.UUID, meta: RequestMeta) -> dict[str, Any]:
    row = (
        await db.session.execute(select(ComposerRun).where(ComposerRun.id == run_id).with_for_update())
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Không tìm thấy phương án")
    if row.applied_at is not None:
        raise ConflictError("Phương án này đã được áp dụng")
    tracks = {t.key: t for t in (await db.session.execute(select(Track))).scalars().all()}
    class_names = _class_names(row.params["class_mode"], row.params["class_count"])
    existing = {
        c.name: c
        for c in (await db.session.execute(select(CohortClass).where(CohortClass.cohort_id == row.cohort_id)))
        .scalars()
        .all()
    }
    size = -(-len(row.assignments) // max(1, row.params["class_count"]))
    classes: list[CohortClass] = []
    for level, name in enumerate(class_names, start=1):
        klass = existing.get(name)
        if klass is None:
            klass = CohortClass(
                organization_id=db.org.id, cohort_id=row.cohort_id, name=name, level=level, capacity=size
            )
            db.session.add(klass)
        else:
            klass.capacity = max(klass.capacity, size)
        classes.append(klass)
    await db.session.flush()

    applied = skipped = 0
    for item in row.assignments:
        enrollment = (
            await db.session.execute(
                select(Enrollment).where(Enrollment.id == uuid.UUID(item["learner_id"])).with_for_update()
            )
        ).scalar_one_or_none()
        if enrollment is None or enrollment.status != "active":
            skipped += 1  # học viên đã rút hoặc đã xét kết quả từ lúc chạy phương án
            continue
        enrollment.class_id = classes[item["class_index"]].id
        if item.get("track"):
            enrollment.track_id = tracks[item["track"]].id
        if item.get("partner_id"):
            placement = (
                await db.session.execute(select(Placement).where(Placement.enrollment_id == enrollment.id))
            ).scalar_one_or_none()
            if placement is None:
                db.session.add(
                    Placement(
                        organization_id=db.org.id,
                        enrollment_id=enrollment.id,
                        partner_id=uuid.UUID(item["partner_id"]),
                        project="",
                    )
                )
            else:
                placement.partner_id = uuid.UUID(item["partner_id"])
        applied += 1
    row.applied_at = datetime.now(UTC)
    write_audit(
        db,
        action="composer.applied",
        entity_type="cohort",
        entity_id=row.cohort_id,
        actor_user_id=actor_user_id,
        after={"run_id": str(row.id), "applied": applied, "skipped": skipped},
        meta=meta,
    )
    return {"applied": applied, "skipped": skipped}


def _class_names(mode: str, count: int) -> list[str]:
    return [f"Mức {i}" for i in range(1, count + 1)] if mode == "levels" else [f"Lớp {i}" for i in range(1, count + 1)]


def run_out(row: ComposerRun, *, include_assignments: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "cohort_id": row.cohort_id,
        "params": row.params,
        "metrics": row.metrics,
        "created_at": row.created_at,
        "applied_at": row.applied_at,
    }
    if include_assignments:
        out["assignments"] = row.assignments
    return out
