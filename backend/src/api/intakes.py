"""Đợt tuyển, rubric và danh mục chương trình/khoá."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.api.deps import Principal, current_principal, request_meta, require
from src.models import Application, Cohort, Intake, Program, Rubric
from src.schemas.intake import IntakeIn, IntakePatch, RubricIn
from src.schemas.responses.applicant import CohortCreatedOut, IntakeOut, ProgramCreatedOut, ProgramOut
from src.schemas.responses.common import MovedOut
from src.schemas.responses.staff import RubricOut, RubricSavedOut
from src.services import intakes as svc
from src.services.tenancy import OrgDb, org_db

router = APIRouter(tags=["intakes"])


class ProgramIn(BaseModel):
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")]
    name_vi: Annotated[str, Field(min_length=1, max_length=200)]
    name_en: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class CohortIn(BaseModel):
    code: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    capacity: int = Field(ge=0, le=100000)
    starts_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def _intake_out(intake: Intake, counts: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": intake.id,
        "program_id": intake.program_id,
        "cohort_id": intake.cohort_id,
        "name": intake.name,
        "description": intake.description,
        "opens_at": intake.opens_at,
        "closes_at": intake.closes_at,
        "quota": intake.quota,
        "status": intake.status,
        "rounds": intake.rounds,
        "approval_mode": intake.approval_mode,
        "ai_screening_enabled": intake.ai_screening_enabled,
        "blind_review": intake.blind_review,
        "min_reviews": intake.min_reviews,
        "eligibility_rules": intake.eligibility_rules,
        "counts": counts or {},
    }


async def _counts(db: OrgDb, intake_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    if not intake_ids:
        return {}
    rows = await db.session.execute(
        select(Application.intake_id, Application.status, func.count())
        .where(Application.intake_id.in_(intake_ids))
        .group_by(Application.intake_id, Application.status)
    )
    out: dict[uuid.UUID, dict[str, int]] = {}
    for intake_id, status, count in rows.all():
        out.setdefault(intake_id, {})[status] = count
    return out


@router.get("/programs", response_model=list[ProgramOut])
async def list_programs(
    _: Principal = Depends(require("intake.read")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    programs = (await db.session.execute(select(Program).order_by(Program.code))).scalars().all()
    cohorts = (await db.session.execute(select(Cohort).order_by(Cohort.code))).scalars().all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "cohorts": [
                {
                    "id": c.id,
                    "code": c.code,
                    "name": c.name,
                    "capacity": c.capacity,
                    "starts_on": c.starts_on,
                    "status": c.status,
                }
                for c in cohorts
                if c.program_id == p.id
            ],
        }
        for p in programs
    ]


@router.post("/programs", status_code=201, response_model=ProgramCreatedOut)
async def create_program(
    body: ProgramIn, _: Principal = Depends(require("intake.manage")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    program = Program(
        organization_id=db.org.id,
        code=body.code,
        name={"vi": body.name_vi, "en": body.name_en or body.name_vi},
    )
    db.session.add(program)
    await db.session.flush()
    out = {"id": program.id, "code": program.code, "name": program.name}
    await db.commit()
    return out


@router.post("/programs/{program_id}/cohorts", status_code=201, response_model=CohortCreatedOut)
async def create_cohort(
    program_id: uuid.UUID, body: CohortIn, _: Principal = Depends(require("intake.manage")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    from datetime import date

    cohort = Cohort(
        organization_id=db.org.id,
        program_id=program_id,
        code=body.code,
        name=body.name,
        capacity=body.capacity,
        starts_on=date.fromisoformat(body.starts_on) if body.starts_on else None,
    )
    db.session.add(cohort)
    await db.session.flush()
    out = {"id": cohort.id, "code": cohort.code, "name": cohort.name}
    await db.commit()
    return out


@router.get("/intakes", response_model=list[IntakeOut])
async def list_intakes(
    principal: Principal = Depends(current_principal), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    staff = bool(principal.permissions & {"intake.manage", "application.read"})
    stmt = select(Intake).order_by(Intake.opens_at.desc())
    if not staff:
        stmt = stmt.where(Intake.status == "open")
    intakes = (await db.session.execute(stmt)).scalars().all()
    counts = await _counts(db, [i.id for i in intakes]) if staff else {}
    return [_intake_out(i, counts.get(i.id)) for i in intakes]


@router.post("/intakes", status_code=201, response_model=IntakeOut)
async def create_intake(
    body: IntakeIn,
    request: Request,
    principal: Principal = Depends(require("intake.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await svc.create_intake(db, body, actor_user_id=principal.user_id, meta=request_meta(request))
    out = _intake_out(intake)
    await db.commit()
    return out


@router.get("/intakes/{intake_id}", response_model=IntakeOut)
async def get_intake(
    intake_id: uuid.UUID, principal: Principal = Depends(current_principal), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    intake = await svc.get_intake(db, intake_id)
    staff = bool(principal.permissions & {"intake.manage", "application.read"})
    if not staff and intake.status != "open":
        from src.errors import NotFoundError

        raise NotFoundError("Không tìm thấy đợt tuyển")
    counts = await _counts(db, [intake.id]) if staff else {}
    return _intake_out(intake, counts.get(intake.id))


@router.patch("/intakes/{intake_id}", response_model=IntakeOut)
async def patch_intake(
    intake_id: uuid.UUID,
    body: IntakePatch,
    request: Request,
    principal: Principal = Depends(require("intake.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await svc.update_intake(db, intake_id, body, actor_user_id=principal.user_id, meta=request_meta(request))
    out = _intake_out(intake)
    await db.commit()
    return out


@router.get("/intakes/{intake_id}/rubrics", response_model=dict[str, RubricOut])
async def get_rubrics(
    intake_id: uuid.UUID,
    _: Principal = Depends(require("intake.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await svc.get_intake(db, intake_id)
    rubrics = (
        (await db.session.execute(select(Rubric).where(Rubric.intake_id == intake_id, Rubric.is_active.is_(True))))
        .scalars()
        .all()
    )
    return {
        r.round: {"version": r.version, "criteria": r.criteria}
        for r in rubrics
        if r.round in {x["key"] for x in intake.rounds}
    }


@router.put("/intakes/{intake_id}/rubrics/{round_key}", response_model=RubricSavedOut)
async def put_rubric(
    intake_id: uuid.UUID,
    round_key: str,
    body: RubricIn,
    request: Request,
    principal: Principal = Depends(require("intake.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    rubric = await svc.set_rubric(
        db, intake_id, round_key, body, actor_user_id=principal.user_id, meta=request_meta(request)
    )
    out = {"round": rubric.round, "version": rubric.version, "criteria": rubric.criteria}
    await db.commit()
    return out


@router.post("/intakes/{intake_id}/publish", response_model=IntakeOut)
async def publish_intake(
    intake_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("intake.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await svc.publish(db, intake_id, actor_user_id=principal.user_id, meta=request_meta(request))
    out = _intake_out(intake)
    await db.commit()
    return out


@router.post("/intakes/{intake_id}/close", response_model=IntakeOut)
async def close_intake(
    intake_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("intake.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await svc.close(db, intake_id, actor_user_id=principal.user_id, meta=request_meta(request))
    out = _intake_out(intake)
    await db.commit()
    return out


@router.post("/intakes/{intake_id}/start", response_model=MovedOut)
async def start_round(
    intake_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("application.assign")),
    db: OrgDb = Depends(org_db),
) -> dict[str, int]:
    moved = await svc.start_first_round(db, intake_id, actor_user_id=principal.user_id, meta=request_meta(request))
    await db.commit()
    return {"moved": moved}
