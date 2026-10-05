"""Trợ lý hỏi đáp có trích nguồn cho ứng viên và nhân sự."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.api.deps import Principal, require
from src.config import get_settings
from src.errors import NotFoundError, RateLimitedError
from src.schemas.responses.assistant import AskOut, AssistantInsightsOut
from src.services import assistant as svc
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/assistant", tags=["assistant"])

ASK_PER_MINUTE = 20


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class FeedbackIn(BaseModel):
    helpful: bool


@router.post("/ask", response_model=AskOut)
async def ask(
    body: AskIn,
    request: Request,
    principal: Principal = Depends(require("assistant.use")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    # Giới hạn theo thành viên: chặn lạm dụng gây tốn chi phí AI hoặc quét kho tài liệu.
    hit = await request.app.state.limiter.hit(f"assistant:{principal.membership_id}", ASK_PER_MINUTE, 60)
    if not hit.allowed:
        raise RateLimitedError(hit.retry_after_s)
    # app.state.assistant_answerer cho phép tiêm động cơ giả khi kiểm thử; thực tế chọn theo cài đặt tổ chức.
    answerer = getattr(request.app.state, "assistant_answerer", None) or await svc.pick_answerer(db, get_settings())
    result = await svc.ask(
        db,
        question=body.question,
        permissions=frozenset(principal.permissions),
        membership_id=principal.membership_id,
        answerer=answerer,
        release_connection=True,
    )
    await db.commit()
    return result


@router.post("/queries/{query_id}/feedback", status_code=204)
async def feedback(
    query_id: uuid.UUID,
    body: FeedbackIn,
    principal: Principal = Depends(require("assistant.use")),
    db: OrgDb = Depends(org_db),
) -> None:
    if not await svc.set_feedback(db, query_id, principal.membership_id, body.helpful):
        raise NotFoundError("Không tìm thấy câu hỏi")
    await db.commit()


insights_router = APIRouter(prefix="/admin/assistant", tags=["admin"])


@insights_router.get("/insights", response_model=AssistantInsightsOut)
async def insights(
    days: int = Query(30, ge=1, le=365),
    _: Principal = Depends(require("kb.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    return await svc.insights(db, days=days)
