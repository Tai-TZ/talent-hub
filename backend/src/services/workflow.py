"""Bảng chuyển trạng thái hồ sơ và thực thi chuyển trạng thái an toàn (docs/02-architecture.md mục 3).

Mọi thay đổi `status` của hồ sơ đi qua `apply_transition`: kiểm tra chuyển hợp lệ, quyền theo từng bước,
khoá lạc quan (version), ghi sự kiện timeline bất biến.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import update

from src.errors import ConflictError, InvalidTransitionError, PermissionDeniedError
from src.models import Application, ApplicationEvent
from src.services.tenancy import OrgDb


@dataclass(frozen=True)
class Rule:
    """Điều kiện cho một bước chuyển."""

    permission: str | None = None  # quyền cần có
    owner_only: bool = False  # chỉ chủ hồ sơ (ứng viên)
    system: bool = False  # chỉ hệ thống thực hiện (không do người dùng gọi trực tiếp)
    visible: bool = True  # có hiện trong timeline của ứng viên


TRANSITIONS: Mapping[tuple[str, str], Rule] = {
    ("DRAFT", "SUBMITTED"): Rule(owner_only=True),
    ("SUBMITTED", "IN_ROUND"): Rule(permission="application.assign"),
    ("IN_ROUND", "IN_ROUND"): Rule(permission="application.review", visible=True),  # sang vòng kế
    ("IN_ROUND", "NEEDS_INFO"): Rule(permission="application.review"),
    ("NEEDS_INFO", "IN_ROUND"): Rule(owner_only=True),
    ("IN_ROUND", "PENDING_APPROVAL"): Rule(permission="decision.propose", visible=False),
    ("WAITLISTED", "PENDING_APPROVAL"): Rule(permission="decision.propose", visible=False),
    ("PENDING_APPROVAL", "ACCEPTED"): Rule(permission="decision.approve"),
    ("PENDING_APPROVAL", "REJECTED"): Rule(permission="decision.approve"),
    ("PENDING_APPROVAL", "WAITLISTED"): Rule(permission="decision.approve"),
    ("PENDING_APPROVAL", "IN_ROUND"): Rule(permission="decision.approve", visible=False),  # trả lại
    ("ACCEPTED", "ENROLLED"): Rule(permission="cohort.manage"),
    **{
        (state, "WITHDRAWN"): Rule(owner_only=True)
        for state in ("DRAFT", "SUBMITTED", "IN_ROUND", "NEEDS_INFO", "ACCEPTED", "WAITLISTED")
    },
}

TERMINAL = frozenset({"REJECTED", "ENROLLED", "WITHDRAWN"})


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID | None
    membership_id: uuid.UUID | None
    permissions: frozenset[str] = field(default_factory=frozenset)


SYSTEM = Actor(user_id=None, membership_id=None)


def check_transition(application: Application, to: str, actor: Actor, *, allow_system: bool = False) -> Rule:
    rule = TRANSITIONS.get((application.status, to))
    if rule is None:
        raise InvalidTransitionError(f"Không thể chuyển hồ sơ từ {application.status} sang {to}")
    if actor is SYSTEM:
        if not allow_system:
            raise PermissionDeniedError("Bước này không do hệ thống thực hiện")
        return rule
    if rule.owner_only and application.applicant_membership_id != actor.membership_id:
        raise PermissionDeniedError("Chỉ chủ hồ sơ được thực hiện thao tác này")
    if rule.permission and rule.permission not in actor.permissions:
        raise PermissionDeniedError("Không đủ quyền thực hiện thao tác này")
    return rule


async def apply_transition(
    db: OrgDb,
    application: Application,
    to: str,
    *,
    actor: Actor,
    expected_version: int | None = None,
    next_round: str | None = None,
    event_type: str | None = None,
    payload: dict[str, Any] | None = None,
    visible: bool | None = None,
    allow_system: bool = False,
) -> Application:
    """Chuyển trạng thái có kiểm tra. `expected_version=None` dùng version đang đọc (thao tác nội bộ)."""
    rule = check_transition(application, to, actor, allow_system=allow_system)
    version = application.version if expected_version is None else expected_version
    from_status = application.status

    values: dict[str, Any] = {"status": to, "version": Application.version + 1}
    if to in ("IN_ROUND",) and next_round is not None:
        values["current_round"] = next_round
    if to in ("WITHDRAWN",):
        values["current_round"] = None

    result = await db.session.execute(
        update(Application)
        .where(Application.id == application.id, Application.version == version)
        .values(**values)
        .returning(Application.version)
    )
    new_version = result.scalar_one_or_none()
    if new_version is None:
        raise ConflictError("Hồ sơ vừa được người khác cập nhật. Hãy tải lại và thử lại.")

    db.session.add(
        ApplicationEvent(
            organization_id=db.org.id,
            application_id=application.id,
            actor_user_id=actor.user_id,
            type=event_type or f"status.{to.lower()}",
            from_status=from_status,
            to_status=to,
            payload={**(payload or {}), **({"round": next_round} if next_round else {})},
            visible_to_applicant=rule.visible if visible is None else visible,
        )
    )
    await db.session.flush()
    await db.session.refresh(application)
    return application
