import uuid
from dataclasses import dataclass
from typing import Any

from src.models import AuditLog
from src.services.tenancy import OrgDb


@dataclass(frozen=True)
class RequestMeta:
    """Thông tin yêu cầu cần cho audit, tách khỏi framework HTTP."""

    ip: str | None = None
    request_id: str | None = None


def write_audit(
    db: OrgDb,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: RequestMeta | None = None,
) -> None:
    """Thêm một dòng audit vào transaction hiện tại (commit cùng thay đổi nghiệp vụ)."""
    meta = meta or RequestMeta()
    db.session.add(
        AuditLog(
            organization_id=db.org.id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=before,
            after=after,
            ip=meta.ip,
            request_id=meta.request_id,
        )
    )
