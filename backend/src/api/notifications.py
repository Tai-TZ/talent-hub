import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from src.api.deps import Principal, current_principal
from src.models import Notification
from src.schemas.responses.applicant import NotificationListOut
from src.services import notifications as svc
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


class ReadIn(BaseModel):
    id: uuid.UUID | None = None  # bỏ trống = đánh dấu đã đọc tất cả


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    principal: Principal = Depends(current_principal),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    rows = (
        (
            await db.session.execute(
                select(Notification)
                .where(Notification.recipient_membership_id == principal.membership_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "unread": await svc.unread_count(db, principal.membership_id),
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "read": n.read_at is not None,
                "created_at": n.created_at,
            }
            for n in rows
        ],
    }


@router.post("/read", status_code=204)
async def mark_read(
    body: ReadIn, principal: Principal = Depends(current_principal), db: OrgDb = Depends(org_db)
) -> None:
    await svc.mark_read(db, principal.membership_id, body.id)
    await db.commit()
