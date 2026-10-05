"""Quản lý tài khoản do bộ phận IT: cấp tài khoản bằng lời mời, phân vai trò, khoá/mở khoá, nhập hàng loạt.

Quy tắc an toàn:
- Danh tính (email, mật khẩu) là toàn cục; admin một tổ chức không được kiểm soát thông tin đăng nhập của người khác.
  Vì vậy link lời mời/đặt lại mật khẩu chỉ gửi tới email của chủ tài khoản; với người đã có mật khẩu thì chấp nhận
  lời mời phải nhập đúng mật khẩu hiện có chứ không đặt lại.
- Không tự đổi vai trò/khoá chính mình; không để tổ chức mất admin cuối cùng; không cấp platform_admin.
"""

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from src.config import get_settings
from src.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from src.models import Invitation, OrgMembership, RefreshToken, Role, User, UserRole
from src.services import email as email_svc
from src.services import org_settings
from src.services.audit import RequestMeta, write_audit
from src.services.auth import load_roles
from src.services.security import hash_token
from src.services.sqlutil import LIKE_ESCAPE, contains_pattern
from src.services.tenancy import OrgDb

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
ASSIGNABLE_ROLES = frozenset(
    {"applicant", "reviewer", "approver", "cohort_manager", "training_manager", "mentor", "admin"}
)
STATUSES = ("active", "suspended")


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValidationFailedError("Email không hợp lệ", {"email": "Định dạng email không hợp lệ"})
    return email


def validate_roles(roles: list[str]) -> list[str]:
    unique = sorted(set(roles))
    if not unique:
        raise ValidationFailedError("Cần ít nhất một vai trò", {"roles": "Chọn ít nhất một vai trò"})
    bad = [r for r in unique if r not in ASSIGNABLE_ROLES]
    if bad:
        raise ValidationFailedError("Vai trò không hợp lệ", {"roles": "Không được cấp: " + ", ".join(bad)})
    return unique


async def _role_ids(db: OrgDb, codes: list[str]) -> dict[str, uuid.UUID]:
    rows = (await db.session.execute(select(Role.code, Role.id).where(Role.code.in_(codes)))).all()
    return {code: rid for code, rid in rows}


async def _set_roles(db: OrgDb, membership_id: uuid.UUID, codes: list[str], granted_by: uuid.UUID) -> None:
    ids = await _role_ids(db, codes)
    await db.session.execute(delete(UserRole).where(UserRole.membership_id == membership_id))
    for code in codes:
        db.session.add(
            UserRole(
                organization_id=db.org.id,
                membership_id=membership_id,
                role_id=ids[code],
                granted_by=granted_by,
                granted_at=datetime.now(UTC),
            )
        )


async def _new_invitation(db: OrgDb, membership_id: uuid.UUID, kind: str, created_by: uuid.UUID) -> str:
    ttl = float(await org_settings.get(db, "invite_ttl_hours"))
    await db.session.execute(
        update(Invitation)
        .where(Invitation.membership_id == membership_id, Invitation.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )  # lời mời cũ chưa dùng bị vô hiệu
    raw = secrets.token_urlsafe(32)
    db.session.add(
        Invitation(
            organization_id=db.org.id,
            membership_id=membership_id,
            kind=kind,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(hours=ttl),
            created_by=created_by,
        )
    )
    return raw


def invitation_link(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/invite/{token}"


def _queue_invitation_email(db: OrgDb, to: str, token: str, kind: str) -> None:
    link = invitation_link(token)
    if kind == "invite":
        subject = f"Lời mời tham gia {db.org.name}"
        body = f"Bạn được mời vào hệ thống tuyển sinh của {db.org.name}.\n\nĐặt mật khẩu và kích hoạt tài khoản tại:\n{link}\n\nLink có hiệu lực trong thời gian giới hạn. Nếu bạn không mong đợi email này, hãy bỏ qua."
    else:
        subject = f"Đặt lại mật khẩu cho {db.org.name}"
        body = f"Có yêu cầu đặt lại mật khẩu cho tài khoản của bạn.\n\nĐặt mật khẩu mới tại:\n{link}\n\nNếu không phải bạn yêu cầu, hãy bỏ qua email này."
    email_svc.enqueue(db, to=to, subject=subject, body=body)


def expose_link() -> bool:
    """Chỉ hiển thị link cho admin khi chạy local hoặc email chỉ ghi log; môi trường thật chỉ gửi qua email."""
    s = get_settings()
    return s.is_local or s.email_backend == "console"


async def create_account(
    db: OrgDb, *, actor_user_id: uuid.UUID, email: str, full_name: str, roles: list[str], meta: RequestMeta
) -> dict[str, Any]:
    email = normalize_email(email)
    roles = validate_roles(roles)
    full_name = full_name.strip()
    if not full_name or len(full_name) > 200:
        raise ValidationFailedError("Họ tên không hợp lệ", {"full_name": "Nhập họ tên (tối đa 200 ký tự)"})

    user = (await db.session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=full_name, password_hash=None, must_change_password=False)
        db.session.add(user)
        await db.session.flush()
    else:
        existing = (
            await db.session.execute(select(OrgMembership).where(OrgMembership.user_id == user.id))
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("Tài khoản đã tồn tại trong tổ chức này")

    membership = OrgMembership(organization_id=db.org.id, user_id=user.id, status="invited")
    db.session.add(membership)
    try:
        await db.session.flush()
    except IntegrityError:
        raise ConflictError("Tài khoản đã tồn tại trong tổ chức này") from None
    await _set_roles(db, membership.id, roles, actor_user_id)
    token = await _new_invitation(db, membership.id, "invite", actor_user_id)
    _queue_invitation_email(db, email, token, "invite")
    write_audit(
        db,
        action="account.created",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor_user_id,
        after={"email": email, "roles": roles},
        meta=meta,
    )
    return {
        "membership_id": membership.id,
        "email": email,
        "roles": roles,
        "status": "invited",
        "invite_link": invitation_link(token) if expose_link() else None,
    }


async def _get_membership(db: OrgDb, membership_id: uuid.UUID) -> tuple[OrgMembership, User]:
    row = (
        await db.session.execute(
            select(OrgMembership, User)
            .join(User, User.id == OrgMembership.user_id)
            .where(OrgMembership.id == membership_id)
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Không tìm thấy tài khoản")
    return row[0], row[1]


async def _active_admin_count(db: OrgDb) -> int:
    return (
        await db.session.execute(
            select(func.count(func.distinct(OrgMembership.id)))
            .select_from(OrgMembership)
            .join(UserRole, UserRole.membership_id == OrgMembership.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == "admin", OrgMembership.status == "active")
        )
    ).scalar_one()


async def update_account(
    db: OrgDb,
    *,
    actor_user_id: uuid.UUID,
    membership_id: uuid.UUID,
    roles: list[str] | None,
    status: str | None,
    meta: RequestMeta,
) -> dict[str, Any]:
    membership, user = await _get_membership(db, membership_id)
    if user.id == actor_user_id:
        raise PermissionDeniedError("Không thể tự đổi vai trò hoặc khoá chính tài khoản của mình")
    if status is not None and status not in STATUSES:
        raise ValidationFailedError("Trạng thái không hợp lệ", {"status": "Chọn active hoặc suspended"})
    if status == "active" and membership.status == "invited":
        raise ConflictError("Tài khoản chưa chấp nhận lời mời nên chưa thể kích hoạt thủ công")

    before_roles = sorted(await load_roles(db, membership.id))
    new_roles = validate_roles(roles) if roles is not None else before_roles
    was_admin = "admin" in before_roles and membership.status == "active"
    will_be_admin = "admin" in new_roles and (status or membership.status) == "active"
    if was_admin and not will_be_admin and await _active_admin_count(db) <= 1:
        raise ConflictError("Không thể bỏ admin cuối cùng của tổ chức")

    before = {"roles": before_roles, "status": membership.status}
    if roles is not None:
        await _set_roles(db, membership.id, new_roles, actor_user_id)
    if status is not None and status != membership.status:
        membership.status = status
        if status == "suspended":  # khoá thì thu hồi mọi phiên làm mới ngay
            await db.session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
    write_audit(
        db,
        action="account.updated",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor_user_id,
        before=before,
        after={"roles": new_roles, "status": membership.status},
        meta=meta,
    )
    return {"membership_id": membership.id, "roles": new_roles, "status": membership.status}


async def resend_invitation(
    db: OrgDb, *, actor_user_id: uuid.UUID, membership_id: uuid.UUID, meta: RequestMeta
) -> dict[str, Any]:
    membership, user = await _get_membership(db, membership_id)
    if membership.status != "invited":
        raise ConflictError("Tài khoản đã kích hoạt; hãy dùng chức năng đặt lại mật khẩu")
    token = await _new_invitation(db, membership.id, "invite", actor_user_id)
    _queue_invitation_email(db, user.email, token, "invite")
    write_audit(
        db,
        action="account.invite_resent",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor_user_id,
        meta=meta,
    )
    return {"invite_link": invitation_link(token) if expose_link() else None}


async def request_password_reset(
    db: OrgDb, *, actor_user_id: uuid.UUID, membership_id: uuid.UUID, meta: RequestMeta
) -> None:
    """Gửi link đặt lại mật khẩu tới email của chủ tài khoản. Admin không nhận được link."""
    membership, user = await _get_membership(db, membership_id)
    if membership.status == "invited":
        raise ConflictError("Tài khoản chưa kích hoạt; hãy gửi lại lời mời")
    token = await _new_invitation(db, membership.id, "reset", actor_user_id)
    _queue_invitation_email(db, user.email, token, "reset")
    write_audit(
        db,
        action="account.reset_requested",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor_user_id,
        meta=meta,
    )


async def list_accounts(
    db: OrgDb,
    *,
    q: str | None,
    role: str | None,
    status: str | None,
    limit: int,
    cursor: uuid.UUID | None,
    audience: str | None = None,
) -> tuple[list[dict[str, Any]], uuid.UUID | None, int]:
    """`audience`: "staff" = có ít nhất một vai trò ngoài ứng viên; "applicant" = chỉ là ứng viên (số lượng rất lớn)."""
    conditions: list[ColumnElement[bool]] = []
    if audience in ("staff", "applicant"):
        has_staff_role = OrgMembership.id.in_(
            select(UserRole.membership_id).join(Role, Role.id == UserRole.role_id).where(Role.code != "applicant")
        )
        conditions.append(has_staff_role if audience == "staff" else ~has_staff_role)
    if q:
        like = contains_pattern(q)
        conditions.append(User.email.ilike(like, escape=LIKE_ESCAPE) | User.full_name.ilike(like, escape=LIKE_ESCAPE))
    if status:
        conditions.append(OrgMembership.status == status)
    if role:
        conditions.append(
            OrgMembership.id.in_(
                select(UserRole.membership_id).join(Role, Role.id == UserRole.role_id).where(Role.code == role)
            )
        )
    total = (
        await db.session.execute(
            select(func.count())
            .select_from(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(and_(True, *conditions))
        )
    ).scalar_one()
    stmt = (
        select(OrgMembership, User)
        .join(User, User.id == OrgMembership.user_id)
        .where(and_(True, *conditions))
        .order_by(OrgMembership.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        stmt = stmt.where(OrgMembership.id < cursor)
    rows = (await db.session.execute(stmt)).all()
    page = rows[:limit]
    role_rows = (
        await db.session.execute(
            select(UserRole.membership_id, Role.code)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.membership_id.in_([m.id for m, _ in page]))
        )
    ).all()
    roles_by: dict[uuid.UUID, list[str]] = {}
    for mid, code in role_rows:
        roles_by.setdefault(mid, []).append(code)
    items = [
        {
            "membership_id": m.id,
            "email": u.email,
            "full_name": u.full_name,
            "status": m.status,
            "roles": sorted(roles_by.get(m.id, [])),
            "last_login_at": u.last_login_at,
            "locked": u.locked_until is not None and u.locked_until > datetime.now(UTC),
            "has_password": u.password_hash is not None,
            "created_at": m.created_at,
        }
        for m, u in page
    ]
    return items, (page[-1][0].id if len(rows) > limit else None), total


async def import_accounts(
    db: OrgDb, *, actor_user_id: uuid.UUID, rows: list[dict[str, Any]], dry_run: bool, meta: RequestMeta
) -> dict[str, Any]:
    """Nhập hàng loạt. Mỗi dòng trong một savepoint riêng: dòng lỗi không làm hỏng các dòng khác."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        email_raw = str(row.get("email", ""))
        entry: dict[str, Any] = {"row": index, "email": email_raw.strip().lower()}
        try:
            email = normalize_email(email_raw)
            validate_roles(list(row.get("roles", [])))
            if email in seen:
                raise ConflictError("Email bị lặp trong tệp")
            seen.add(email)
            if dry_run:
                exists = (await db.session.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
                if exists:
                    already = (
                        await db.session.execute(select(OrgMembership.id).where(OrgMembership.user_id == exists))
                    ).scalar_one_or_none()
                    if already:
                        raise ConflictError("Tài khoản đã tồn tại trong tổ chức này")
                entry["status"] = "ok"
            else:
                async with db.session.begin_nested():
                    created = await create_account(
                        db,
                        actor_user_id=actor_user_id,
                        email=email,
                        full_name=str(row.get("full_name", "")),
                        roles=list(row.get("roles", [])),
                        meta=meta,
                    )
                entry["status"] = "created"
                entry["invite_link"] = created["invite_link"]
        except (ValidationFailedError, ConflictError) as exc:
            entry["status"] = "error"
            fields = exc.fields if isinstance(exc, ValidationFailedError) else {}
            entry["error"] = "; ".join(fields.values()) or exc.message
        results.append(entry)
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("ok", "created", "error")}
    return {"dry_run": dry_run, "summary": summary, "rows": results}


async def accept_invitation(db: OrgDb, *, token: str, password: str | None) -> tuple[Invitation, OrgMembership, User]:
    """Kiểm tra token lời mời. Việc đặt mật khẩu do tầng gọi thực hiện (cần băm bất đồng bộ)."""
    inv = (
        await db.session.execute(select(Invitation).where(Invitation.token_hash == hash_token(token)).with_for_update())
    ).scalar_one_or_none()
    if inv is None or inv.used_at is not None or inv.expires_at <= datetime.now(UTC):
        raise NotFoundError("Link không hợp lệ hoặc đã hết hạn")
    membership, user = await _get_membership(db, inv.membership_id)
    return inv, membership, user


async def accept(db: OrgDb, *, token: str, password: str, meta: RequestMeta) -> Any:
    """Chấp nhận lời mời hoặc đặt lại mật khẩu bằng token, rồi mở phiên đăng nhập."""
    from src.errors import InvalidCredentialsError
    from src.services import auth as auth_svc
    from src.services.security import hash_password_async, verify_password_async

    inv, membership, user = await accept_invitation(db, token=token, password=password)
    if inv.kind == "invite":
        if user.password_hash is None:
            auth_svc.check_password_strength(password, email=user.email)
            user.password_hash = await hash_password_async(password)
        elif not await verify_password_async(user.password_hash, password):
            # Người đã có tài khoản ở nơi khác: phải chứng minh biết mật khẩu hiện có, không được đặt lại.
            raise InvalidCredentialsError("Mật khẩu không đúng")
        if membership.status == "invited":
            membership.status = "active"
    else:
        if membership.status != "active":
            raise ConflictError("Tài khoản không ở trạng thái hoạt động")
        auth_svc.check_password_strength(password, email=user.email)
        user.password_hash = await hash_password_async(password)
        await db.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    now = datetime.now(UTC)
    user.must_change_password = False
    user.email_verified_at = user.email_verified_at or now
    user.failed_logins, user.locked_until = 0, None
    inv.used_at = now
    tokens, _ = auth_svc._issue_tokens(db, user, membership)  # noqa: SLF001 - cùng gói dịch vụ xác thực
    write_audit(
        db,
        action="account.invitation_accepted" if inv.kind == "invite" else "account.password_reset",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        meta=meta,
    )
    return auth_svc.SessionResult(auth_svc.Identity(user, membership, await load_roles(db, membership.id)), tokens)
