"""Sàng lọc AI hàng loạt: chạy nền có tiến độ, bảng phân nhóm gợi ý và theo dõi tác vụ."""

import functools
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from src.ai.factory import get_engine
from src.api.deps import Principal, request_meta, require
from src.config import get_settings
from src.errors import ConflictError
from src.services import jobs, triage
from src.services.audit import write_audit
from src.services.intakes import get_intake
from src.services.tenancy import OrgDb, org_db

router = APIRouter(tags=["triage"])


class TriageIn(BaseModel):
    round: str | None = None
    force: bool = False


def _job_out(job: Any) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "total": job.total,
        "done": job.done,
        "result": job.result,
        "error": job.error,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


@router.post("/intakes/{intake_id}/triage", status_code=202)
async def start_triage(
    intake_id: uuid.UUID,
    body: TriageIn,
    request: Request,
    principal: Principal = Depends(require("triage.run")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    round_key, total = await triage.preflight(db, intake_id, body.round)
    if await jobs.active_job(db, "triage", "intake_id", str(intake_id)) is not None:
        raise ConflictError("Đang có một lượt sàng lọc chạy cho đợt tuyển này")
    job = await jobs.create_job(
        db,
        kind="triage",
        created_by=principal.user_id,
        params={"intake_id": str(intake_id), "round": round_key, "force": body.force},
    )
    job.total = total
    write_audit(
        db,
        action="triage.started",
        entity_type="intake",
        entity_id=intake_id,
        actor_user_id=principal.user_id,
        after={"round": round_key, "total": total, "force": body.force},
        meta=request_meta(request),
    )
    org_id, job_id = db.org.id, job.id
    await db.commit()

    engine = getattr(request.app.state, "screening_engine", None) or get_engine(get_settings())
    work = functools.partial(
        triage.run_triage, engine=engine, intake_id=intake_id, round_key=round_key, force=body.force
    )
    jobs.spawn(org_id, job_id, work)
    return {"job_id": job_id, "total": total, "round": round_key, "engine": engine.name}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID, _: Principal = Depends(require("job.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    return _job_out(await jobs.get_job(db, job_id))


@router.get("/intakes/{intake_id}/triage")
async def triage_board(
    intake_id: uuid.UUID,
    round_key: str | None = Query(None, alias="round"),
    tier: str | None = Query(None, pattern="^(invite|review|decline_likely)$"),
    attention: bool | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    principal: Principal = Depends(require("triage.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await get_intake(db, intake_id)
    round_key = round_key or intake.rounds[0]["key"]
    summary = await triage.board(db, intake_id, round_key)
    items = await triage.board_items(
        db,
        intake_id,
        round_key,
        tier=tier,
        attention=attention,
        limit=limit,
        offset=offset,
        can_see_pii="pii.read" in principal.permissions,
        blind=intake.blind_review,
    )
    return {
        **summary,
        "items": items,
        "thresholds": triage.thresholds_of(intake.triage_config),
        "rounds": intake.rounds,
        "ai_enabled": intake.ai_screening_enabled,
    }
