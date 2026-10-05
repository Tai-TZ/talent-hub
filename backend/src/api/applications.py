"""Hồ sơ của ứng viên: tạo nháp, chỉnh sửa, nộp, bổ sung, rút, theo dõi."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.deps import Principal, actor_of, current_principal, request_meta, require
from src.models import Application, Intake
from src.services import applications as svc
from src.services.intakes import get_intake
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/applications", tags=["applications"])


class CreateIn(BaseModel):
    intake_id: uuid.UUID


class PatchIn(BaseModel):
    profile: dict[str, Any] | None = None
    content: dict[str, Any] | None = None


class SubmitIn(BaseModel):
    consent: bool
    version: int | None = Field(default=None, ge=1)


class VersionIn(BaseModel):
    version: int | None = Field(default=None, ge=1)


class WithdrawIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _summary(app: Application, intake: Intake) -> dict[str, Any]:
    return {
        "id": app.id,
        "status": app.status,
        "current_round": app.current_round,
        "candidate_code": app.candidate_code,
        "version": app.version,
        "intake": {"id": intake.id, "name": intake.name, "closes_at": intake.closes_at, "rounds": intake.rounds},
        "submitted_at": app.submitted_at,
    }


@router.post("", status_code=201)
async def create_application(
    body: CreateIn,
    request: Request,
    principal: Principal = Depends(require("application.create")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await svc.create_draft(
        db,
        intake_id=body.intake_id,
        membership_id=principal.membership_id,
        user_id=principal.user_id,
        full_name=principal.full_name,
        meta=request_meta(request),
    )
    intake = await get_intake(db, app.intake_id)
    out = svc.application_view(app, intake, can_see_pii=True, owner=True)
    await db.commit()
    return out


@router.get("/mine")
async def my_applications(
    principal: Principal = Depends(require("application.read.own")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    rows = (
        await db.session.execute(
            select(Application, Intake)
            .join(Intake, Intake.id == Application.intake_id)
            .where(Application.applicant_membership_id == principal.membership_id)
            .order_by(Application.created_at.desc())
        )
    ).all()
    return [_summary(app, intake) for app, intake in rows]


@router.get("/{application_id}")
async def get_my_application(
    application_id: uuid.UUID,
    principal: Principal = Depends(require("application.read.own")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await svc.get_own_application(db, application_id, principal.membership_id)
    intake = await get_intake(db, app.intake_id)
    return svc.application_view(app, intake, can_see_pii=True, owner=True)


@router.patch("/{application_id}")
async def save_application(
    application_id: uuid.UUID,
    body: PatchIn,
    principal: Principal = Depends(require("application.write.own")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await svc.get_own_application(db, application_id, principal.membership_id)
    await svc.save_draft(db, app, profile=body.profile, content=body.content)
    intake = await get_intake(db, app.intake_id)
    out = svc.application_view(app, intake, can_see_pii=True, owner=True)
    await db.commit()
    return out


@router.post("/{application_id}/submit")
async def submit_application(
    application_id: uuid.UUID,
    body: SubmitIn,
    request: Request,
    principal: Principal = Depends(require("application.write.own")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await svc.get_own_application(db, application_id, principal.membership_id)
    await svc.submit(
        db,
        app,
        actor=actor_of(principal),
        consent=body.consent,
        expected_version=body.version,
        meta=request_meta(request),
    )
    intake = await get_intake(db, app.intake_id)
    out = svc.application_view(app, intake, can_see_pii=True, owner=True)
    await db.commit()
    return out


@router.post("/{application_id}/resubmit")
async def resubmit_application(
    application_id: uuid.UUID,
    body: VersionIn,
    principal: Principal = Depends(require("application.write.own")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await svc.get_own_application(db, application_id, principal.membership_id)
    await svc.resubmit_after_info(db, app, actor=actor_of(principal), expected_version=body.version)
    intake = await get_intake(db, app.intake_id)
    out = svc.application_view(app, intake, can_see_pii=True, owner=True)
    await db.commit()
    return out


@router.post("/{application_id}/withdraw")
async def withdraw_application(
    application_id: uuid.UUID,
    body: WithdrawIn,
    request: Request,
    principal: Principal = Depends(require("application.write.own")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await svc.get_own_application(db, application_id, principal.membership_id)
    await svc.withdraw(db, app, actor=actor_of(principal), reason=body.reason, meta=request_meta(request))
    intake = await get_intake(db, app.intake_id)
    out = svc.application_view(app, intake, can_see_pii=True, owner=True)
    await db.commit()
    return out


@router.get("/{application_id}/timeline")
async def application_timeline(
    application_id: uuid.UUID, principal: Principal = Depends(current_principal), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    app = await svc.get_application(db, application_id)
    owner = app.applicant_membership_id == principal.membership_id
    if not owner and "application.read" not in principal.permissions:
        from src.errors import NotFoundError

        raise NotFoundError("Không tìm thấy hồ sơ")
    events = await svc.timeline(db, app, applicant_view=owner)
    return [
        {
            "id": e.id,
            "type": e.type,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "at": e.at,
            "message": (e.payload or {}).get("message"),
            "round": (e.payload or {}).get("round"),
        }
        for e in events
    ]
