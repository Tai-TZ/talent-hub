"""Khu vực nhân sự: hàng đợi, chấm điểm, chuyển vòng, đề xuất và phê duyệt."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.deps import Principal, actor_of, request_meta, require
from src.errors import NotFoundError
from src.models import AiAssessment, Application, Decision, Intake, OrgMembership, Review, User
from src.schemas.responses.staff import (
    AdvanceOut,
    ApprovalRowOut,
    ProposalOut,
    QueuePageOut,
    ReviewSavedOut,
    StaffApplicationOut,
    StatusOut,
    StatusVersionOut,
)
from src.services import applications as app_svc
from src.services import decisions as decision_svc
from src.services import reviews as review_svc
from src.services.intakes import active_rubric, get_intake
from src.services.queue import QueueQuery, list_queue
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/staff", tags=["staff"])


class ReviewIn(BaseModel):
    scores: dict[str, float] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=4000)
    # Khớp ràng buộc recommendation_valid của DB; giá trị lạ trả 422 thay vì để DB ném lỗi (500).
    recommendation: Literal["advance", "reject", "waitlist"] | None = None
    submit: bool = False


class VersionIn(BaseModel):
    version: int | None = Field(default=None, ge=1)


class RequestInfoIn(VersionIn):
    message: str = Field(max_length=2000)


class ProposalIn(VersionIn):
    outcome: str
    reason: str = Field(max_length=4000)


class ApproveIn(VersionIn):
    outcome: str
    reason: str = Field(max_length=4000)
    applicant_message: str = Field(max_length=4000)


class ReturnIn(VersionIn):
    note: str = Field(max_length=2000)


def _ai_out(a: AiAssessment) -> dict[str, Any]:
    return {
        "engine": a.engine,
        "model": a.model,
        "prompt_version": a.prompt_version,
        "total_score": a.total_score,
        "confidence": a.confidence,
        "tier": a.tier,
        "needs_attention": a.needs_attention,
        "scores": a.scores,
        "evidence": a.evidence,
        "flags": a.flags,
        "rationale": a.rationale,
        "input_fields": a.input_fields,
        "created_at": a.created_at,
    }


@router.get("/applications", response_model=QueuePageOut, response_model_exclude_unset=True)
async def staff_queue(
    intake_id: uuid.UUID,
    status: str | None = None,
    round_key: str | None = Query(None, alias="round"),
    q: str | None = Query(None, max_length=100),
    needs_attention: bool | None = None,
    mine_pending: bool = False,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    principal: Principal = Depends(require("application.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    intake = await get_intake(db, intake_id)
    items, next_cursor, total = await list_queue(
        db,
        QueueQuery(
            intake_id=intake_id,
            status=status,
            round_key=round_key,
            q=q,
            needs_attention=needs_attention,
            mine_pending=mine_pending,
            limit=limit,
            cursor=cursor,
        ),
        membership_id=principal.membership_id,
        can_see_pii="pii.read" in principal.permissions,
        can_see_tier="triage.read" in principal.permissions,
        intake=intake,
    )
    return {"items": items, "next_cursor": next_cursor, "total": total, "blind_review": intake.blind_review}


@router.get("/applications/{application_id}", response_model=StaffApplicationOut)
async def staff_application(
    application_id: uuid.UUID, principal: Principal = Depends(require("application.read")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    app = await app_svc.get_application(db, application_id)
    if app.status == "DRAFT":
        raise NotFoundError("Không tìm thấy hồ sơ")
    intake = await get_intake(db, app.intake_id)
    view = app_svc.application_view(app, intake, can_see_pii="pii.read" in principal.permissions, owner=False)

    rubric = await active_rubric(db, app.intake_id, app.current_round) if app.current_round else None
    mine = (
        await review_svc.get_review(db, app.id, principal.membership_id, app.current_round)
        if app.current_round
        else None
    )
    i_submitted = bool(mine and mine.submitted_at)
    can_triage = "triage.read" in principal.permissions

    # Chống neo: reviewer chỉ thấy AI sau khi tự chốt điểm; người có triage.read thấy ngay.
    ai = await review_svc.latest_ai(db, app) if app.current_round else None
    ai_block: dict[str, Any] | None
    if ai is None:
        ai_block = None
    elif can_triage or i_submitted:
        ai_block = _ai_out(ai)
    else:
        ai_block = {"locked": True, "needs_attention": ai.needs_attention}

    # Điểm của reviewer khác chỉ hiện sau khi mình chốt (độc lập), hoặc với người phê duyệt/quản trị.
    sees_all = i_submitted or bool(principal.permissions & {"decision.approve", "application.assign"})
    reviews_out: list[dict[str, Any]] = []
    if app.current_round and sees_all:
        rows = (
            await db.session.execute(
                select(Review, User.full_name)
                .join(OrgMembership, OrgMembership.id == Review.reviewer_membership_id)
                .join(User, User.id == OrgMembership.user_id)
                .where(
                    Review.application_id == app.id, Review.round == app.current_round, Review.submitted_at.is_not(None)
                )
                .order_by(Review.submitted_at)
            )
        ).all()
        reviews_out = [
            {
                "reviewer": name
                if ("pii.read" in principal.permissions or r.reviewer_membership_id == principal.membership_id)
                else None,
                "mine": r.reviewer_membership_id == principal.membership_id,
                "scores": r.scores,
                "total_score": r.total_score,
                "comment": r.comment,
                "recommendation": r.recommendation,
                "submitted_at": r.submitted_at,
            }
            for r, name in rows
        ]
    pending = await decision_svc.pending_decision(db, app.id)
    view.update(
        {
            "rubric": {"version": rubric.version, "criteria": rubric.criteria} if rubric else None,
            "my_review": (
                {
                    "scores": mine.scores,
                    "comment": mine.comment,
                    "recommendation": mine.recommendation,
                    "submitted": i_submitted,
                    "total_score": mine.total_score,
                }
                if mine
                else None
            ),
            "reviews": reviews_out,
            "disagreement": review_svc.disagreement(await review_svc.submitted_reviews(db, app))
            if app.current_round and sees_all
            else False,
            "ai": ai_block,
            "pending_decision": (
                {
                    "id": pending.id,
                    "proposed_outcome": pending.proposed_outcome,
                    "proposal_reason": pending.proposal_reason,
                    "proposed_by_me": pending.proposed_by == principal.user_id,
                }
                if pending
                else None
            ),
            "timeline": [
                {
                    "type": e.type,
                    "from_status": e.from_status,
                    "to_status": e.to_status,
                    "at": e.at,
                    "message": (e.payload or {}).get("message"),
                }
                for e in await app_svc.timeline(db, app, applicant_view=False)
            ],
        }
    )
    return view


@router.put("/applications/{application_id}/review", response_model=ReviewSavedOut)
async def save_review(
    application_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    principal: Principal = Depends(require("application.review")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await app_svc.get_application(db, application_id)
    round_key = app.current_round or ""
    review = await review_svc.save_review(
        db,
        app,
        actor=actor_of(principal),
        round_key=round_key,
        scores=body.scores,
        comment=body.comment,
        recommendation=body.recommendation,
        submit=body.submit,
        meta=request_meta(request),
    )
    out = {"submitted": review.submitted_at is not None, "total_score": review.total_score}
    await db.commit()
    return out


@router.post("/applications/{application_id}/advance", response_model=AdvanceOut)
async def advance(
    application_id: uuid.UUID,
    body: VersionIn,
    request: Request,
    principal: Principal = Depends(require("application.review")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await app_svc.get_application(db, application_id)
    await review_svc.advance_round(
        db, app, actor=actor_of(principal), expected_version=body.version, meta=request_meta(request)
    )
    out = {"status": app.status, "current_round": app.current_round, "version": app.version}
    await db.commit()
    return out


@router.post("/applications/{application_id}/request-info", response_model=StatusVersionOut)
async def request_info(
    application_id: uuid.UUID,
    body: RequestInfoIn,
    request: Request,
    principal: Principal = Depends(require("application.review")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await app_svc.get_application(db, application_id)
    await review_svc.request_info(
        db,
        app,
        actor=actor_of(principal),
        message=body.message,
        expected_version=body.version,
        meta=request_meta(request),
    )
    out = {"status": app.status, "version": app.version}
    await db.commit()
    return out


@router.post("/applications/{application_id}/proposals", status_code=201, response_model=ProposalOut)
async def propose(
    application_id: uuid.UUID,
    body: ProposalIn,
    request: Request,
    principal: Principal = Depends(require("decision.propose")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    app = await app_svc.get_application(db, application_id)
    decision = await decision_svc.propose(
        db,
        app,
        actor=actor_of(principal),
        outcome=body.outcome,
        reason=body.reason,
        expected_version=body.version,
        meta=request_meta(request),
    )
    out = {"decision_id": decision.id, "status": app.status, "version": app.version}
    await db.commit()
    return out


@router.get("/approvals", response_model=list[ApprovalRowOut])
async def approvals(
    intake_id: uuid.UUID | None = None,
    principal: Principal = Depends(require("decision.approve")),
    db: OrgDb = Depends(org_db),
) -> list[dict[str, Any]]:
    stmt = (
        select(Decision, Application, Intake)
        .join(Application, Application.id == Decision.application_id)
        .join(Intake, Intake.id == Application.intake_id)
        .where(Decision.status == "pending")
        .order_by(Decision.created_at)
        .limit(200)
    )
    if intake_id:
        stmt = stmt.where(Application.intake_id == intake_id)
    out: list[dict[str, Any]] = []
    for decision, app, intake in (await db.session.execute(stmt)).all():
        reviews = await review_svc.submitted_reviews(db, app)
        ai = await review_svc.latest_ai(db, app)
        scores = [r.total_score for r in reviews if r.total_score is not None]
        out.append(
            {
                "decision_id": decision.id,
                "application_id": app.id,
                "candidate_code": app.candidate_code,
                "name": app.profile.get("full_name")
                if ("pii.read" in principal.permissions or not intake.blind_review)
                else None,
                "intake": {"id": intake.id, "name": intake.name},
                "proposed_outcome": decision.proposed_outcome,
                "proposal_reason": decision.proposal_reason,
                "proposed_by_me": decision.proposed_by == principal.user_id,
                "review_count": len(reviews),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
                "ai_tier": ai.tier if ai else None,
                "ai_score": ai.total_score if ai else None,
                "flag_count": len(app.flags or []),
                "version": app.version,
            }
        )
    return out


@router.post("/decisions/{decision_id}/approve", response_model=StatusOut)
async def approve(
    decision_id: uuid.UUID,
    body: ApproveIn,
    request: Request,
    principal: Principal = Depends(require("decision.approve")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    decision = await decision_svc.get_decision(db, decision_id, for_update=True)
    app = await app_svc.get_application(db, decision.application_id)
    await decision_svc.approve(
        db,
        decision,
        app,
        actor=actor_of(principal),
        outcome=body.outcome,
        reason=body.reason,
        applicant_message=body.applicant_message,
        expected_version=body.version,
        meta=request_meta(request),
    )
    out = {"status": app.status}
    await db.commit()
    return out


@router.post("/decisions/{decision_id}/return", response_model=StatusOut)
async def return_decision(
    decision_id: uuid.UUID,
    body: ReturnIn,
    request: Request,
    principal: Principal = Depends(require("decision.approve")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    decision = await decision_svc.get_decision(db, decision_id, for_update=True)
    app = await app_svc.get_application(db, decision.application_id)
    await decision_svc.return_to_review(
        db,
        decision,
        app,
        actor=actor_of(principal),
        note=body.note,
        expected_version=body.version,
        meta=request_meta(request),
    )
    out = {"status": app.status}
    await db.commit()
    return out
