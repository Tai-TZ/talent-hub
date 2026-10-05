import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from src.models import OrgMembership, User
from src.services.audit import RequestMeta
from src.services.auth import load_roles
from src.services.rbac import permissions_for
from src.services.security import decode_access_token
from src.services.tenancy import OrgDb, org_db
from src.services.workflow import Actor


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    org_id: uuid.UUID
    email: str
    full_name: str
    must_change_password: bool
    roles: frozenset[str]
    permissions: frozenset[str]


def request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
    )


def actor_of(principal: Principal) -> Actor:
    return Actor(user_id=principal.user_id, membership_id=principal.membership_id, permissions=principal.permissions)


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="Chưa đăng nhập hoặc phiên đã hết hạn")


async def current_principal(request: Request, db: OrgDb = Depends(org_db)) -> Principal:
    token = request.cookies.get("access_token")
    if not token:
        raise _unauthenticated()
    try:
        claims = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise _unauthenticated() from None

    # Tổ chức theo tên miền phải trùng tổ chức trong token (chặn dùng token chéo tổ chức).
    if claims["org"] != str(db.org.id):
        raise HTTPException(status_code=403, detail="Phiên đăng nhập không thuộc tổ chức này")

    try:
        membership_id, user_id = uuid.UUID(claims["mid"]), uuid.UUID(claims["sub"])
    except ValueError:
        raise _unauthenticated() from None

    row = (
        await db.session.execute(
            select(OrgMembership, User)
            .join(User, User.id == OrgMembership.user_id)
            .where(OrgMembership.id == membership_id, OrgMembership.user_id == user_id)
        )
    ).one_or_none()
    if row is None:
        raise _unauthenticated()
    membership, user = row
    if membership.status != "active" or not user.is_active:
        raise _unauthenticated()

    roles = await load_roles(db, membership.id)
    return Principal(
        user_id=user.id,
        membership_id=membership.id,
        org_id=db.org.id,
        email=user.email,
        full_name=user.full_name,
        must_change_password=user.must_change_password,
        roles=roles,
        permissions=permissions_for(roles),
    )


def require(permission: str) -> Callable[[Principal], Awaitable[Principal]]:
    async def checker(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.must_change_password:
            raise HTTPException(status_code=403, detail="Cần đổi mật khẩu trước khi tiếp tục")
        if permission not in principal.permissions:
            raise HTTPException(status_code=403, detail="Không đủ quyền thực hiện thao tác này")
        return principal

    return checker
