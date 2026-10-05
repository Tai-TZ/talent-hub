"""Use-case đăng nhập, làm mới phiên, đăng xuất, đổi mật khẩu. Không phụ thuộc FastAPI."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from src.config import get_settings
from src.errors import InvalidCredentialsError, InvalidRefreshTokenError, PasswordPolicyError
from src.models import OrgMembership, RefreshToken, Role, User, UserRole
from src.models.base import uuid7
from src.services.audit import RequestMeta, write_audit
from src.services.rbac import permissions_for
from src.services.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password_async,
    hash_token,
    new_refresh_token,
    verify_password_async,
)
from src.services.tenancy import OrgDb

MIN_PASSWORD_LENGTH = 10


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    refresh_expires: datetime


@dataclass(frozen=True)
class Identity:
    user: User
    membership: OrgMembership
    roles: frozenset[str]

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.roles)


@dataclass(frozen=True)
class SessionResult:
    identity: Identity
    tokens: SessionTokens


async def load_roles(db: OrgDb, membership_id: uuid.UUID) -> frozenset[str]:
    rows = await db.session.execute(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.membership_id == membership_id)
    )
    return frozenset(rows.scalars().all())


async def _active_membership(db: OrgDb, user_id: uuid.UUID) -> OrgMembership | None:
    return (
        await db.session.execute(
            select(OrgMembership).where(OrgMembership.user_id == user_id, OrgMembership.status == "active")
        )
    ).scalar_one_or_none()


def _issue_tokens(
    db: OrgDb, user: User, membership: OrgMembership, family_id: uuid.UUID | None = None
) -> tuple[SessionTokens, uuid.UUID]:
    settings = get_settings()
    raw, hashed = new_refresh_token()
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    token_id = uuid7()
    db.session.add(
        RefreshToken(
            id=token_id,
            organization_id=db.org.id,
            user_id=user.id,
            token_hash=hashed,
            family_id=family_id or uuid7(),
            expires_at=expires,
        )
    )
    access = create_access_token(user_id=user.id, org_id=db.org.id, membership_id=membership.id)
    return SessionTokens(access, raw, expires), token_id


async def _revoke_family(db: OrgDb, family_id: uuid.UUID, now: datetime) -> None:
    await db.session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def login(db: OrgDb, *, email: str, password: str, meta: RequestMeta) -> SessionResult:
    settings = get_settings()
    now = datetime.now(UTC)
    email = email.strip().lower()

    user = (await db.session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    membership = await _active_membership(db, user.id) if user is not None else None
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    usable = (
        user is not None and membership is not None and user.is_active and user.password_hash is not None and not locked
    )

    if not usable:
        # Vẫn băm một mật khẩu giả để thời gian phản hồi không phân biệt được các trường hợp.
        await verify_password_async(DUMMY_HASH, password)
        write_audit(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            after={"email": email, "reason": "locked" if locked else "unusable"},
            meta=meta,
        )
        await db.commit()
        raise InvalidCredentialsError("Email hoặc mật khẩu không đúng")

    assert user is not None and membership is not None and user.password_hash is not None
    if not await verify_password_async(user.password_hash, password):
        user.failed_logins += 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        write_audit(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            after={"reason": "bad_password"},
            meta=meta,
        )
        await db.commit()
        raise InvalidCredentialsError("Email hoặc mật khẩu không đúng")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    tokens, _ = _issue_tokens(db, user, membership)
    write_audit(db, action="auth.login", entity_type="user", entity_id=user.id, actor_user_id=user.id, meta=meta)
    identity = Identity(user, membership, await load_roles(db, membership.id))
    await db.commit()
    return SessionResult(identity, tokens)


async def refresh(db: OrgDb, *, raw_token: str, meta: RequestMeta) -> SessionResult:
    now = datetime.now(UTC)
    token = (
        await db.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
        )
    ).scalar_one_or_none()
    if token is None:
        raise InvalidRefreshTokenError("Refresh token không hợp lệ")

    if token.revoked_at is not None:
        # Token đã dùng rồi mà bị trình lại: nghi ngờ bị đánh cắp, thu hồi cả họ token.
        await _revoke_family(db, token.family_id, now)
        write_audit(db, action="auth.refresh_reuse_detected", entity_type="user", entity_id=token.user_id, meta=meta)
        await db.commit()
        raise InvalidRefreshTokenError("Refresh token không hợp lệ")

    if token.expires_at <= now:
        raise InvalidRefreshTokenError("Refresh token đã hết hạn")

    user = (await db.session.execute(select(User).where(User.id == token.user_id))).scalar_one()
    membership = await _active_membership(db, user.id)
    if membership is None or not user.is_active:
        raise InvalidRefreshTokenError("Tài khoản không còn hiệu lực")

    tokens, new_id = _issue_tokens(db, user, membership, family_id=token.family_id)
    token.revoked_at = now
    token.replaced_by = new_id
    identity = Identity(user, membership, await load_roles(db, membership.id))
    await db.commit()
    return SessionResult(identity, tokens)


async def logout(db: OrgDb, *, raw_token: str, meta: RequestMeta) -> None:
    token = (
        await db.session.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    ).scalar_one_or_none()
    if token is None:
        return
    await _revoke_family(db, token.family_id, datetime.now(UTC))
    write_audit(
        db, action="auth.logout", entity_type="user", entity_id=token.user_id, actor_user_id=token.user_id, meta=meta
    )
    await db.commit()


def check_password_strength(new_password: str, *, email: str) -> None:
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Mật khẩu mới phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự")
    if len(new_password) > 256:
        raise PasswordPolicyError("Mật khẩu quá dài")
    local = email.split("@")[0].lower()
    if new_password.lower() == email.lower() or (len(local) >= 3 and local in new_password.lower()):
        raise PasswordPolicyError("Mật khẩu không được chứa tên tài khoản email")


def validate_new_password(new_password: str, *, current_password: str, email: str) -> None:
    check_password_strength(new_password, email=email)
    if new_password == current_password:
        raise PasswordPolicyError("Mật khẩu mới phải khác mật khẩu hiện tại")


async def change_password(
    db: OrgDb,
    *,
    user_id: uuid.UUID,
    membership_id: uuid.UUID,
    current_password: str,
    new_password: str,
    meta: RequestMeta,
) -> SessionResult:
    user = (await db.session.execute(select(User).where(User.id == user_id))).scalar_one()
    if user.password_hash is None or not await verify_password_async(user.password_hash, current_password):
        raise InvalidCredentialsError("Mật khẩu hiện tại không đúng")
    validate_new_password(new_password, current_password=current_password, email=user.email)

    user.password_hash = await hash_password_async(new_password)
    user.must_change_password = False
    # Thu hồi mọi phiên cũ; phiên hiện tại được cấp lại.
    await db.session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    membership = (await db.session.execute(select(OrgMembership).where(OrgMembership.id == membership_id))).scalar_one()
    tokens, _ = _issue_tokens(db, user, membership)
    write_audit(
        db, action="auth.password_changed", entity_type="user", entity_id=user.id, actor_user_id=user.id, meta=meta
    )
    identity = Identity(user, membership, await load_roles(db, membership.id))
    await db.commit()
    return SessionResult(identity, tokens)
