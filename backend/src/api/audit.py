import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from src.api.deps import Principal, require
from src.errors import ValidationFailedError
from src.models import AuditLog
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/audit-logs", tags=["audit"])


class AuditLogOut(BaseModel):
    id: uuid.UUID
    at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    after: dict[str, Any] | None
    request_id: str | None


class AuditPage(BaseModel):
    items: list[AuditLogOut]
    next_cursor: str | None


@router.get("", response_model=AuditPage)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="id của dòng cuối trang trước"),
    action: str | None = None,
    _: Principal = Depends(require("audit.read")),
    db: OrgDb = Depends(org_db),
) -> AuditPage:
    # UUIDv7 sắp xếp theo thời gian nên dùng id làm cursor; RLS giới hạn trong tổ chức hiện tại.
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    if cursor:
        try:
            stmt = stmt.where(AuditLog.id < uuid.UUID(cursor))
        except ValueError:
            raise ValidationFailedError("Con trỏ phân trang không hợp lệ", {"cursor": "Không hợp lệ"}) from None
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = (await db.session.execute(stmt)).scalars().all()
    page = rows[:limit]
    return AuditPage(
        items=[
            AuditLogOut(
                id=r.id,
                at=r.at,
                actor_user_id=r.actor_user_id,
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                after=r.after,
                request_id=r.request_id,
            )
            for r in page
        ],
        next_cursor=str(page[-1].id) if len(rows) > limit else None,
    )
