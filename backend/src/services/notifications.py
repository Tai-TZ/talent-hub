import uuid

from sqlalchemy import func, select, update

from src.models import Notification
from src.services.tenancy import OrgDb


def notify(
    db: OrgDb,
    recipient_membership_id: uuid.UUID,
    *,
    type: str,  # noqa: A002
    title: str,
    body: str = "",
    link: str | None = None,
) -> None:
    """Thêm thông báo trong ứng dụng; commit cùng transaction nghiệp vụ gây ra nó."""
    db.session.add(
        Notification(
            organization_id=db.org.id,
            recipient_membership_id=recipient_membership_id,
            type=type,
            title=title,
            body=body,
            link=link,
        )
    )


async def unread_count(db: OrgDb, membership_id: uuid.UUID) -> int:
    return (
        await db.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_membership_id == membership_id, Notification.read_at.is_(None))
        )
    ).scalar_one()


async def mark_read(db: OrgDb, membership_id: uuid.UUID, notification_id: uuid.UUID | None) -> None:
    stmt = update(Notification).where(
        Notification.recipient_membership_id == membership_id, Notification.read_at.is_(None)
    )
    if notification_id is not None:
        stmt = stmt.where(Notification.id == notification_id)
    await db.session.execute(stmt.values(read_at=func.now()))
