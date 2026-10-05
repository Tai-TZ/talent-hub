"""Router HTTP cho xác thực. Nghiệp vụ nằm ở src/services/auth.py."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.api.deps import Principal, current_principal, request_meta
from src.config import get_settings
from src.errors import InvalidCredentialsError, InvalidRefreshTokenError, RateLimitedError
from src.services import accounts
from src.services import auth as auth_service
from src.services.audit import RequestMeta
from src.services.auth import SessionResult, SessionTokens
from src.services.rbac import permissions_for
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["auth"])

REFRESH_COOKIE_PATH = "/api/v1/auth"


class LoginIn(BaseModel):
    # Đăng nhập không kiểm tra định dạng email (sai thì chỉ là xác thực thất bại); chỉ giới hạn độ dài.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    organization: str
    roles: list[str]
    permissions: list[str]
    must_change_password: bool


def _me_from_session(result: SessionResult, db: OrgDb) -> MeOut:
    identity = result.identity
    return MeOut(
        user_id=identity.user.id,
        email=identity.user.email,
        full_name=identity.user.full_name,
        organization=db.org.slug,
        roles=sorted(identity.roles),
        permissions=sorted(identity.permissions),
        must_change_password=identity.user.must_change_password,
    )


def _set_cookies(response: Response, tokens: SessionTokens) -> None:
    settings = get_settings()
    response.set_cookie(
        "access_token",
        tokens.access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        expires=tokens.refresh_expires,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path=REFRESH_COOKIE_PATH)


async def _throttle_login(request: Request, meta: RequestMeta) -> None:
    result = await request.app.state.limiter.hit(f"login:{meta.ip}", get_settings().login_rate_limit_per_minute, 60)
    if not result.allowed:
        raise RateLimitedError(result.retry_after_s)


@router.post("/login", response_model=MeOut)
async def login(body: LoginIn, request: Request, response: Response, db: OrgDb = Depends(org_db)) -> MeOut:
    meta = request_meta(request)
    await _throttle_login(request, meta)
    result = await auth_service.login(db, email=body.email, password=body.password, meta=meta)
    _set_cookies(response, result.tokens)
    return _me_from_session(result, db)


@router.post("/refresh", response_model=MeOut)
async def refresh(request: Request, response: Response, db: OrgDb = Depends(org_db)) -> MeOut:
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise InvalidRefreshTokenError("Thiếu refresh token")
    result = await auth_service.refresh(db, raw_token=raw, meta=request_meta(request))
    _set_cookies(response, result.tokens)
    return _me_from_session(result, db)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: OrgDb = Depends(org_db)) -> None:
    raw = request.cookies.get("refresh_token")
    if raw:
        await auth_service.logout(db, raw_token=raw, meta=request_meta(request))
    _clear_cookies(response)


@router.post("/password/change", status_code=204)
async def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    principal: Principal = Depends(current_principal),
    db: OrgDb = Depends(org_db),
) -> None:
    try:
        result = await auth_service.change_password(
            db,
            user_id=principal.user_id,
            membership_id=principal.membership_id,
            current_password=body.current_password,
            new_password=body.new_password,
            meta=request_meta(request),
        )
    except InvalidCredentialsError as exc:
        # Sai mật khẩu hiện tại là lỗi của yêu cầu, không phải phiên hết hạn.
        raise HTTPException(status_code=400, detail=exc.message) from None
    _set_cookies(response, result.tokens)


@me_router.get("/me", response_model=MeOut)
async def me(principal: Principal = Depends(current_principal), db: OrgDb = Depends(org_db)) -> MeOut:
    return MeOut(
        user_id=principal.user_id,
        email=principal.email,
        full_name=principal.full_name,
        organization=db.org.slug,
        roles=sorted(principal.roles),
        permissions=sorted(permissions_for(principal.roles)),
        must_change_password=principal.must_change_password,
    )


class AcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=1, max_length=256)


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 2)}@{domain}"


@router.get("/invitations/{token}")
async def invitation_preview(token: str, request: Request, db: OrgDb = Depends(org_db)) -> dict[str, object]:
    await _throttle_login(request, request_meta(request))
    _, membership, user = await accounts.accept_invitation(db, token=token, password=None)
    inv_kind = "reset" if membership.status == "active" else "invite"
    return {
        "organization": db.org.name,
        "email": _mask_email(user.email),
        "kind": inv_kind,
        # Người đã có mật khẩu ở nơi khác phải nhập đúng mật khẩu đó, không được đặt lại.
        "has_password": user.password_hash is not None and inv_kind == "invite",
    }


@router.post("/invitations/accept", response_model=MeOut)
async def accept_invitation(body: AcceptIn, request: Request, response: Response, db: OrgDb = Depends(org_db)) -> MeOut:
    meta = request_meta(request)
    await _throttle_login(request, meta)
    result = await accounts.accept(db, token=body.token, password=body.password, meta=meta)
    out = _me_from_session(result, db)
    await db.commit()
    _set_cookies(response, result.tokens)
    return out
