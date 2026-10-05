"""Vận hành khoá học: học viên, lớp, nhánh, đối tác, đánh giá năng lực, xét đạt, phụ cấp, bộ giải Composer."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.deps import Principal, actor_of, request_meta, require
from src.models import Competency, ComposerRun, Enrollment, OrgMembership, Partner, Placement, Track, TrackTarget, User
from src.schemas.responses.cohorts import (
    AssignedOut,
    CohortOverviewOut,
    CompetenciesOut,
    ComposerAppliedOut,
    ComposerRunDetailOut,
    ComposerRunOut,
    CreatedOut,
    EnrolledOut,
    EnrollmentPageOut,
    EnrollmentStatusOut,
    IdKeyOut,
    IdNameOut,
    IdOut,
    MentorLearnerOut,
    PaidOut,
    PartnerOut,
    QualificationRowOut,
    SavedOut,
    StipendSummaryOut,
    TrackOut,
)
from src.services import cohort_ops as ops
from src.services import composer_service as composer
from src.services.tenancy import OrgDb, org_db

router = APIRouter(tags=["cohorts"])


class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    level: int = Field(default=1, ge=1, le=20)
    capacity: int = Field(gt=0, le=10000)


class AssignIn(BaseModel):
    class_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = None


class TrackIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    name_vi: str = Field(min_length=1, max_length=120)
    keywords: list[str] = Field(default_factory=list, max_length=30)


class CapacityIn(BaseModel):
    capacity: int = Field(gt=0, le=100000)


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=30)


class DemandIn(BaseModel):
    partner_id: uuid.UUID
    track_id: uuid.UUID
    slots: int = Field(gt=0, le=1000)


class PlaceIn(BaseModel):
    partner_id: uuid.UUID
    mentor_membership_id: uuid.UUID | None = None
    project: str = Field(default="", max_length=300)


class AssessmentIn(BaseModel):
    competency_id: uuid.UUID
    level: int = Field(ge=1, le=10)
    evidence: str = Field(max_length=2000)


class QualificationIn(BaseModel):
    outcome: str
    reason: str = Field(max_length=2000)


class PeriodIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


class ComposerIn(BaseModel):
    class_count: int = Field(default=3, ge=1, le=30)
    class_mode: str = Field(default="levels", pattern="^(levels|balanced)$")
    pref_weight: float = Field(default=0.6, ge=0, le=1)
    fit_weight: float = Field(default=0.4, ge=0, le=1)
    track_capacity: dict[str, int] | None = None


@router.get("/cohorts/{cohort_id}/overview", response_model=CohortOverviewOut)
async def cohort_overview(
    cohort_id: uuid.UUID, _: Principal = Depends(require("cohort.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    return await ops.cohort_overview(db, cohort_id)


@router.get("/cohorts/{cohort_id}/enrollments", response_model=EnrollmentPageOut)
async def enrollments(
    cohort_id: uuid.UUID,
    status: str | None = Query(None, pattern="^(active|withdrawn|qualified|not_qualified)$"),
    class_id: uuid.UUID | None = None,
    track_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100000),
    _: Principal = Depends(require("cohort.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    items, total = await ops.list_enrollments(
        db, cohort_id, status=status, class_id=class_id, track_id=track_id, q=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.post("/cohorts/{cohort_id}/enroll-accepted", response_model=EnrolledOut)
async def enroll_accepted(
    cohort_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, int]:
    count = await ops.enroll_all_accepted(db, cohort_id, actor=actor_of(principal), meta=request_meta(request))
    await db.commit()
    return {"enrolled": count}


@router.patch("/enrollments/{enrollment_id}", response_model=AssignedOut)
async def assign(
    enrollment_id: uuid.UUID,
    body: AssignIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    e = await ops.assign_enrollment(
        db,
        enrollment_id,
        class_id=body.class_id,
        track_id=body.track_id,
        actor_user_id=principal.user_id,
        meta=request_meta(request),
    )
    out = {"id": e.id, "class_id": e.class_id, "track_id": e.track_id}
    await db.commit()
    return out


# ---------- Nhánh, lớp ----------
@router.get("/tracks", response_model=list[TrackOut])
async def list_tracks(
    _: Principal = Depends(require("intake.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    tracks = (await db.session.execute(select(Track).order_by(Track.key))).scalars().all()
    targets = (
        await db.session.execute(
            select(TrackTarget, Competency).join(Competency, Competency.id == TrackTarget.competency_id)
        )
    ).all()
    return [
        {
            "id": t.id,
            "key": t.key,
            "name": t.name,
            "keywords": t.keywords,
            "targets": [
                {"competency_id": c.id, "code": c.code, "name": c.name, "target": tt.target_level}
                for tt, c in targets
                if tt.track_id == t.id
            ],
        }
        for t in tracks
    ]


@router.post("/programs/{program_id}/tracks", status_code=201, response_model=IdKeyOut)
async def create_track(
    program_id: uuid.UUID,
    body: TrackIn,
    request: Request,
    principal: Principal = Depends(require("training.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    t = await ops.upsert_track(
        db,
        program_id=program_id,
        key=body.key,
        name_vi=body.name_vi,
        keywords=body.keywords,
        actor_user_id=principal.user_id,
        meta=request_meta(request),
    )
    out = {"id": t.id, "key": t.key}
    await db.commit()
    return out


@router.put("/cohorts/{cohort_id}/tracks/{track_id}", response_model=SavedOut)
async def set_track_capacity(
    cohort_id: uuid.UUID,
    track_id: uuid.UUID,
    body: CapacityIn,
    _: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, str]:
    await ops.set_cohort_track_capacity(db, cohort_id, track_id, body.capacity)
    await db.commit()
    return {"status": "saved"}


@router.post("/cohorts/{cohort_id}/classes", status_code=201, response_model=IdNameOut)
async def create_class(
    cohort_id: uuid.UUID, body: ClassIn, _: Principal = Depends(require("cohort.manage")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    klass = await ops.create_class(db, cohort_id, name=body.name, level=body.level, capacity=body.capacity)
    out = {"id": klass.id, "name": klass.name}
    await db.commit()
    return out


# ---------- Đối tác và thực chiến ----------
@router.get("/partners", response_model=list[PartnerOut])
async def list_partners(
    _: Principal = Depends(require("cohort.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    rows = (await db.session.execute(select(Partner).order_by(Partner.name))).scalars().all()
    return [{"id": p.id, "name": p.name, "skills": p.skills, "status": p.status} for p in rows]


@router.post("/partners", status_code=201, response_model=IdNameOut)
async def save_partner(
    body: PartnerIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    p = await ops.upsert_partner(
        db, name=body.name, skills=body.skills, actor_user_id=principal.user_id, meta=request_meta(request)
    )
    out = {"id": p.id, "name": p.name}
    await db.commit()
    return out


@router.put("/cohorts/{cohort_id}/partner-demand", response_model=SavedOut)
async def set_demand(
    cohort_id: uuid.UUID, body: DemandIn, _: Principal = Depends(require("cohort.manage")), db: OrgDb = Depends(org_db)
) -> dict[str, str]:
    await ops.set_partner_demand(db, cohort_id, body.partner_id, body.track_id, body.slots)
    await db.commit()
    return {"status": "saved"}


@router.post("/enrollments/{enrollment_id}/placement", response_model=IdOut)
async def place(
    enrollment_id: uuid.UUID,
    body: PlaceIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    p = await ops.place(
        db,
        enrollment_id,
        partner_id=body.partner_id,
        mentor_membership_id=body.mentor_membership_id,
        project=body.project,
        actor_user_id=principal.user_id,
        meta=request_meta(request),
    )
    out = {"id": p.id}
    await db.commit()
    return out


# ---------- Năng lực, mentor, xét đạt ----------
@router.get("/enrollments/{enrollment_id}/competencies", response_model=CompetenciesOut)
async def competencies(
    enrollment_id: uuid.UUID, principal: Principal = Depends(require("mentor.assess")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    e = await ops.get_enrollment(db, enrollment_id)
    matrix = await ops.competency_matrix(db, e)
    return {
        "enrollment_id": e.id,
        "track_id": e.track_id,
        "matrix": matrix,
        "suggestion": ops.suggestion_from(matrix),
        "status": e.status,
    }


@router.post("/enrollments/{enrollment_id}/assessments", status_code=201, response_model=IdOut)
async def assess(
    enrollment_id: uuid.UUID,
    body: AssessmentIn,
    request: Request,
    principal: Principal = Depends(require("mentor.assess")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    row = await ops.add_assessment(
        db,
        enrollment_id,
        competency_id=body.competency_id,
        level=body.level,
        evidence=body.evidence,
        assessor=actor_of(principal),
        meta=request_meta(request),
    )
    out = {"id": row.id}
    await db.commit()
    return out


@router.get("/mentor/learners", response_model=list[MentorLearnerOut])
async def mentor_learners(
    principal: Principal = Depends(require("mentor.assess")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    stmt = (
        select(Enrollment, User, Placement)
        .join(Placement, Placement.enrollment_id == Enrollment.id)
        .join(OrgMembership, OrgMembership.id == Enrollment.membership_id)
        .join(User, User.id == OrgMembership.user_id)
        .where(Enrollment.status == "active")
    )
    if "training.manage" not in principal.permissions:
        stmt = stmt.where(Placement.mentor_membership_id == principal.membership_id)
    rows = (await db.session.execute(stmt.order_by(User.full_name).limit(200))).all()
    return [
        {
            "enrollment_id": e.id,
            "name": u.full_name,
            "track_id": e.track_id,
            "project": p.project,
            "partner_id": p.partner_id,
        }
        for e, u, p in rows
    ]


@router.get("/cohorts/{cohort_id}/qualification", response_model=list[QualificationRowOut])
async def qualification(
    cohort_id: uuid.UUID, _: Principal = Depends(require("cohort.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    return await ops.qualification_report(db, cohort_id)


@router.post("/enrollments/{enrollment_id}/qualification", response_model=EnrollmentStatusOut)
async def decide(
    enrollment_id: uuid.UUID,
    body: QualificationIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    e = await ops.decide_qualification(
        db,
        enrollment_id,
        outcome=body.outcome,
        reason=body.reason,
        actor_user_id=principal.user_id,
        meta=request_meta(request),
    )
    out = {"id": e.id, "status": e.status}
    await db.commit()
    return out


# ---------- Phụ cấp ----------
@router.get("/cohorts/{cohort_id}/stipends", response_model=list[StipendSummaryOut])
async def stipends(
    cohort_id: uuid.UUID, _: Principal = Depends(require("cohort.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    return await ops.stipend_summary(db, cohort_id)


@router.post("/cohorts/{cohort_id}/stipends/generate", response_model=CreatedOut)
async def stipends_generate(
    cohort_id: uuid.UUID,
    body: PeriodIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, int]:
    created = await ops.generate_stipends(
        db, cohort_id, body.period, actor_user_id=principal.user_id, meta=request_meta(request)
    )
    await db.commit()
    return {"created": created}


@router.post("/cohorts/{cohort_id}/stipends/pay", response_model=PaidOut)
async def stipends_pay(
    cohort_id: uuid.UUID,
    body: PeriodIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await ops.mark_stipends_paid(
        db, cohort_id, body.period, actor_user_id=principal.user_id, meta=request_meta(request)
    )
    await db.commit()
    return out


# ---------- Cohort Composer ----------
@router.post("/cohorts/{cohort_id}/composer/runs", status_code=201, response_model=ComposerRunOut)
async def composer_run(
    cohort_id: uuid.UUID,
    body: ComposerIn,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    row = await composer.run(
        db, cohort_id, body.model_dump(), actor_user_id=principal.user_id, meta=request_meta(request)
    )
    out = composer.run_out(row, include_assignments=False)
    await db.commit()
    return out


@router.get("/cohorts/{cohort_id}/composer/runs", response_model=list[ComposerRunOut])
async def composer_runs(
    cohort_id: uuid.UUID, _: Principal = Depends(require("cohort.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    rows = (
        (
            await db.session.execute(
                select(ComposerRun)
                .where(ComposerRun.cohort_id == cohort_id)
                .order_by(ComposerRun.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return [composer.run_out(r) for r in rows]


@router.get("/composer/runs/{run_id}", response_model=ComposerRunDetailOut)
async def composer_get(
    run_id: uuid.UUID, _: Principal = Depends(require("cohort.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    row = await composer.get_run(db, run_id)
    names = {
        str(e.id): u.full_name
        for e, u in (
            await db.session.execute(
                select(Enrollment, User)
                .join(OrgMembership, OrgMembership.id == Enrollment.membership_id)
                .join(User, User.id == OrgMembership.user_id)
                .where(Enrollment.cohort_id == row.cohort_id)
            )
        ).all()
    }
    out = composer.run_out(row, include_assignments=True)
    out["assignments"] = [{**a, "name": names.get(a["learner_id"])} for a in row.assignments]
    return out


@router.post("/composer/runs/{run_id}/apply", response_model=ComposerAppliedOut)
async def composer_apply(
    run_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("cohort.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await composer.apply_run(db, run_id, actor_user_id=principal.user_id, meta=request_meta(request))
    await db.commit()
    return out
