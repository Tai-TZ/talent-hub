"""Điểm vào đăng nhập Microsoft: /auth/microsoft/start và /auth/microsoft/callback.

Cả hai là GET điều hướng trình duyệt nên kết quả luôn là chuyển hướng (không trả JSON):
thành công về trang đích, thất bại về /login?error=<mã> để giao diện hiển thị thông báo.
"""

import hmac
import uuid
from typing import cast
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from src.api.auth import set_auth_cookies, throttle_login
from src.api.deps import request_meta
from src.config import get_settings
from src.errors import DomainError, NotFoundError
from src.services import oidc
from src.services import security as security_svc
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/auth/microsoft", tags=["auth"])
FLOW_COOKIE_PATH = "/api/v1/auth/microsoft"


def _provider(request: Request) -> oidc.OidcProvider:
    provider = getattr(request.app.state, "oidc_provider", None)
    if provider is not None:
        return cast(oidc.OidcProvider, provider)
    settings = get_settings()
    if not settings.microsoft_enabled:
        raise NotFoundError("Chưa bật đăng nhập Microsoft")
    provider = oidc.MicrosoftProvider(settings)
    request.app.state.oidc_provider = provider
    return provider


def _signed_in_user(request: Request, db: OrgDb) -> uuid.UUID | None:
    """Người đang đăng nhập (cho chế độ liên kết). Token của tổ chức khác không được chấp nhận."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = security_svc.decode_access_token(token)
        return uuid.UUID(payload["sub"]) if payload["org"] == str(db.org.id) else None
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def _to_login(code: str, response: RedirectResponse | None = None) -> RedirectResponse:
    out = response or RedirectResponse(f"/login?error={quote(code)}", status_code=303)
    out.delete_cookie(oidc.FLOW_COOKIE, path=FLOW_COOKIE_PATH)
    return out


@router.get("/start")
async def start(
    request: Request,
    mode: oidc.Mode = "login",
    token: str | None = Query(None, max_length=200),
    next: str | None = Query(None, max_length=300),
    db: OrgDb = Depends(org_db),
) -> RedirectResponse:
    await throttle_login(request, request_meta(request))
    provider = _provider(request)
    settings = get_settings()
    state, nonce, verifier, challenge = oidc.new_flow_secrets()
    flow = oidc.sign_flow(
        settings.jwt_secret,
        state=state,
        nonce=nonce,
        verifier=verifier,
        mode=mode,
        invite=token if mode == "invite" else None,
        next=oidc.safe_next(next),
        org=db.org.slug,
    )
    response = RedirectResponse(provider.authorize_url(state=state, nonce=nonce, challenge=challenge), status_code=303)
    response.set_cookie(
        oidc.FLOW_COOKIE,
        flow,
        max_age=oidc.FLOW_TTL_S,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",  # callback là điều hướng cấp cao từ miền khác: Strict sẽ không gửi cookie
        path=FLOW_COOKIE_PATH,
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = Query(None, max_length=4096),
    state: str | None = Query(None, max_length=256),
    error: str | None = Query(None, max_length=100),
    db: OrgDb = Depends(org_db),
) -> RedirectResponse:
    settings = get_settings()
    meta = request_meta(request)
    try:
        await throttle_login(request, meta)
        flow = oidc.read_flow(settings.jwt_secret, request.cookies.get(oidc.FLOW_COOKIE))
        if error:  # người dùng huỷ hoặc Microsoft từ chối
            raise oidc.OidcError("cancelled", "Đăng nhập Microsoft đã bị huỷ")
        if not state or not hmac.compare_digest(state, str(flow.get("state", ""))):
            raise oidc.OidcError("state_mismatch", "Phiên đăng nhập Microsoft không khớp, hãy thử lại")
        if flow.get("org") != db.org.slug:
            raise oidc.OidcError("state_mismatch", "Phiên đăng nhập thuộc tổ chức khác")
        if not code:
            raise oidc.OidcError("exchange_failed", "Microsoft không trả mã xác thực")

        claims = await _provider(request).exchange(code=code, verifier=str(flow["verifier"]), nonce=str(flow["nonce"]))

        current_user_id = _signed_in_user(request, db) if flow["mode"] == "link" else None
        result = await oidc.complete_login(
            db,
            claims,
            mode=flow["mode"],
            invite_token=flow.get("invite"),
            current_user_id=current_user_id,
            meta=meta,
        )
        await db.commit()
    except oidc.OidcError as exc:
        await db.session.rollback()
        return _to_login(exc.code)
    except DomainError:
        await db.session.rollback()
        return _to_login("failed")

    target = flow["next"] if result is not None else "/account/password?linked=1"
    response = RedirectResponse(str(target), status_code=303)
    response.delete_cookie(oidc.FLOW_COOKIE, path=FLOW_COOKIE_PATH)
    if result is not None:
        set_auth_cookies(response, result.tokens)
    return response
