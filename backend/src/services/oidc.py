"""Đăng nhập bằng Microsoft Entra ID (OIDC authorization code + PKCE).

Nguyên tắc an toàn:
- Danh tính là (issuer, subject). Không bao giờ khớp hoặc liên kết theo email: claim email của Entra không được xác minh (nOAuth).
- Nhân sự chỉ gắn Microsoft thông qua lời mời (token lời mời chứng minh quyền kiểm soát) hoặc khi đã đăng nhập (chế độ link).
- Ứng viên được tự tạo tài khoản; nếu email trùng tài khoản đã có thì từ chối, không hợp nhất.
- `state` + `nonce` + PKCE verifier nằm trong cookie ký, hết hạn sau 10 phút, gắn với tổ chức.
- ID token: chỉ RS256, kiểm chữ ký bằng JWKS, aud, iss (theo tid), exp, nonce; tenant được kiểm theo danh sách cho phép của tổ chức.
"""

import base64
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.config import Settings
from src.errors import DomainError
from src.models import OAuthAccount, OrgMembership, Role, User, UserRole
from src.services import accounts, org_settings
from src.services import auth as auth_svc
from src.services.audit import RequestMeta, write_audit
from src.services.tenancy import OrgDb

FLOW_COOKIE = "ms_oidc"
FLOW_TTL_S = 600
Mode = Literal["login", "invite", "link"]
CONSUMERS_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"


class OidcError(DomainError):
    """Lỗi luồng đăng nhập ngoài. `code` được giao diện chuyển thành thông báo thân thiện."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class IdClaims:
    issuer: str
    subject: str
    tenant_id: str | None
    name: str | None
    email: str | None  # Chỉ để hiển thị/đặt tên; KHÔNG dùng để định danh.


class OidcProvider(Protocol):
    def authorize_url(self, *, state: str, nonce: str, challenge: str) -> str: ...

    async def exchange(self, *, code: str, verifier: str, nonce: str) -> IdClaims: ...


# ---------- PKCE và cookie luồng ----------


def new_flow_secrets() -> tuple[str, str, str, str]:
    """(state, nonce, verifier, challenge S256)."""
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return state, nonce, verifier, challenge


def safe_next(value: str | None) -> str:
    """Chỉ chấp nhận đường dẫn nội bộ; chặn open redirect (//host, \\host, scheme)."""
    if not value or len(value) > 300 or not value.startswith("/") or value.startswith(("//", "/\\")):
        return "/dashboard"
    if any(ord(c) < 32 or c == "\\" for c in value) or value.startswith("/api/") or value.startswith("/login"):
        return "/dashboard"
    return value


def sign_flow(secret: str, **claims: Any) -> str:
    return jwt.encode({**claims, "exp": int(time.time()) + FLOW_TTL_S, "typ": "oidc-flow"}, secret, algorithm="HS256")


def read_flow(secret: str, token: str | None) -> dict[str, Any]:
    if not token:
        raise OidcError("expired", "Phiên đăng nhập Microsoft đã hết hạn, hãy thử lại")
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError:
        raise OidcError("expired", "Phiên đăng nhập Microsoft đã hết hạn, hãy thử lại") from None
    if claims.get("typ") != "oidc-flow":
        raise OidcError("expired", "Phiên đăng nhập Microsoft không hợp lệ")
    return claims


# ---------- Nhà cung cấp Microsoft ----------


class MicrosoftProvider:
    JWKS_TTL_S = 3600

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._s = settings
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._jwks: dict[str, Any] = {}
        self._jwks_at = 0.0

    @property
    def _base(self) -> str:
        return f"{self._s.microsoft_authority.rstrip('/')}/{self._s.microsoft_tenant}"

    def authorize_url(self, *, state: str, nonce: str, challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self._s.microsoft_client_id,
                "response_type": "code",
                "redirect_uri": self._s.microsoft_callback_url,
                "response_mode": "query",
                "scope": "openid profile email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{self._base}/oauth2/v2.0/authorize?{query}"

    async def _signing_key(self, kid: str) -> Any:
        for attempt in (0, 1):
            fresh = time.monotonic() - self._jwks_at < self.JWKS_TTL_S
            if attempt == 1 or not fresh or kid not in self._jwks:
                resp = await self._http.get(f"{self._base}/discovery/v2.0/keys")
                resp.raise_for_status()
                self._jwks = {k["kid"]: k for k in resp.json()["keys"] if k.get("kty") == "RSA"}
                self._jwks_at = time.monotonic()
            if kid in self._jwks:
                return jwt.PyJWK.from_dict(self._jwks[kid]).key
        raise OidcError("token_invalid", "Không xác minh được chữ ký của Microsoft")

    async def exchange(self, *, code: str, verifier: str, nonce: str) -> IdClaims:
        try:
            resp = await self._http.post(
                f"{self._base}/oauth2/v2.0/token",
                data={
                    "client_id": self._s.microsoft_client_id,
                    "client_secret": self._s.microsoft_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._s.microsoft_callback_url,
                    "code_verifier": verifier,
                },
            )
        except httpx.HTTPError:
            raise OidcError("provider_unavailable", "Không kết nối được Microsoft, hãy thử lại sau") from None
        if resp.status_code != 200:
            raise OidcError("exchange_failed", "Microsoft từ chối yêu cầu đăng nhập")
        id_token = resp.json().get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("token_invalid", "Phản hồi của Microsoft thiếu ID token")
        return await self._verify(id_token, nonce)

    async def _verify(self, id_token: str, nonce: str) -> IdClaims:
        try:
            header = jwt.get_unverified_header(id_token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise OidcError("token_invalid", "ID token không hợp lệ")
            key = await self._signing_key(str(header["kid"]))
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self._s.microsoft_client_id,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
                leeway=60,
            )
        except OidcError:
            raise
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError):
            raise OidcError("token_invalid", "ID token không hợp lệ hoặc đã hết hạn") from None
        return validate_claims(
            claims, nonce=nonce, configured_tenant=self._s.microsoft_tenant, authority=self._s.microsoft_authority
        )


def validate_claims(
    claims: dict[str, Any],
    *,
    nonce: str,
    configured_tenant: str,
    authority: str = "https://login.microsoftonline.com",
) -> IdClaims:
    """Kiểm tra phần nội dung ID token sau khi đã xác minh chữ ký (tách riêng để kiểm thử độc lập)."""
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OidcError("token_invalid", "ID token không khớp phiên đăng nhập")
    tid = claims.get("tid")
    issuer = str(claims["iss"])
    # Với endpoint chung ("common"), iss chứa tid của chính token; phải khớp, nếu không là token giả mạo tenant.
    if not isinstance(tid, str) or issuer != f"{authority.rstrip('/')}/{tid}/v2.0":
        raise OidcError("token_invalid", "Nhà phát hành ID token không hợp lệ")
    if configured_tenant not in ("common", "organizations", "consumers") and tid != configured_tenant:
        raise OidcError("tenant_not_allowed", "Tài khoản Microsoft thuộc tenant không được phép")
    return IdClaims(
        issuer=issuer,
        subject=str(claims["sub"]),
        tenant_id=tid,
        name=str(claims["name"]) if claims.get("name") else None,
        email=str(claims.get("email") or claims.get("preferred_username") or "").lower() or None,
    )


# ---------- Giải quyết danh tính ----------


async def _tenant_allowed(db: OrgDb, claims: IdClaims) -> bool:
    allowed = str(await org_settings.get(db, "microsoft_allowed_tenants")).split(",")
    allowed = [a for a in allowed if a]
    return not allowed or (claims.tenant_id or "") in allowed


async def _find_account(db: OrgDb, claims: IdClaims) -> OAuthAccount | None:
    return (
        await db.session.execute(
            select(OAuthAccount).where(OAuthAccount.issuer == claims.issuer, OAuthAccount.subject == claims.subject)
        )
    ).scalar_one_or_none()


async def _link(db: OrgDb, user: User, claims: IdClaims) -> None:
    db.session.add(
        OAuthAccount(
            user_id=user.id,
            provider="microsoft",
            issuer=claims.issuer,
            subject=claims.subject,
            tenant_id=claims.tenant_id,
        )
    )
    try:
        await db.session.flush()
    except IntegrityError:
        raise OidcError("already_linked", "Tài khoản Microsoft này đã được liên kết với người dùng khác") from None


async def _session_for(db: OrgDb, user: User, meta: RequestMeta, *, action: str) -> auth_svc.SessionResult:
    membership = (
        await db.session.execute(select(OrgMembership).where(OrgMembership.user_id == user.id))
    ).scalar_one_or_none()
    if membership is None or membership.status != "active" or not user.is_active:
        raise OidcError("not_allowed", "Tài khoản không có quyền truy cập tổ chức này hoặc đã bị khoá")
    user.last_login_at = datetime.now(UTC)
    user.failed_logins, user.locked_until = 0, None
    tokens, _ = auth_svc._issue_tokens(db, user, membership)  # noqa: SLF001 - cùng gói dịch vụ xác thực
    write_audit(
        db,
        action=action,
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        after={"provider": "microsoft"},
        meta=meta,
    )
    return auth_svc.SessionResult(
        auth_svc.Identity(user, membership, await auth_svc.load_roles(db, membership.id)), tokens
    )


async def _add_applicant_membership(db: OrgDb, user: User) -> OrgMembership:
    membership = OrgMembership(organization_id=db.org.id, user_id=user.id, status="active")
    db.session.add(membership)
    await db.session.flush()
    role_id = (await db.session.execute(select(Role.id).where(Role.code == "applicant"))).scalar_one()
    db.session.add(
        UserRole(organization_id=db.org.id, membership_id=membership.id, role_id=role_id, granted_at=datetime.now(UTC))
    )
    await db.session.flush()
    return membership


async def _self_signup(db: OrgDb, claims: IdClaims, meta: RequestMeta) -> User:
    if await org_settings.get(db, "microsoft_signup") != "on":
        raise OidcError(
            "signup_disabled", "Tổ chức không cho tự tạo tài khoản bằng Microsoft. Hãy liên hệ quản trị viên"
        )
    email = claims.email or f"ms-{hashlib.sha256(claims.subject.encode()).hexdigest()[:16]}@microsoft.invalid"
    existing = (await db.session.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        # Không hợp nhất theo email: email trong ID token không đáng tin để chứng minh quyền sở hữu.
        raise OidcError(
            "account_exists",
            "Email này đã có tài khoản. Hãy đăng nhập bằng mật khẩu rồi liên kết Microsoft trong phần tài khoản",
        )
    user = User(email=email, full_name=(claims.name or email.split("@")[0])[:200], password_hash=None)
    db.session.add(user)
    await db.session.flush()
    await _add_applicant_membership(db, user)
    await _link(db, user, claims)
    write_audit(
        db,
        action="account.self_registered",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        after={"provider": "microsoft", "tenant": claims.tenant_id},
        meta=meta,
    )
    return user


async def complete_login(
    db: OrgDb,
    claims: IdClaims,
    *,
    mode: Mode,
    invite_token: str | None,
    current_user_id: uuid.UUID | None,
    meta: RequestMeta,
) -> auth_svc.SessionResult | None:
    """Hoàn tất đăng nhập/gắn tài khoản. Trả về phiên mới, hoặc None cho chế độ `link` (giữ phiên hiện tại)."""
    if not await _tenant_allowed(db, claims):
        raise OidcError("tenant_not_allowed", "Tài khoản Microsoft thuộc tenant không được tổ chức này cho phép")

    account = await _find_account(db, claims)

    if mode == "link":
        if current_user_id is None:
            raise OidcError("login_required", "Hãy đăng nhập trước khi liên kết Microsoft")
        if account is not None and account.user_id != current_user_id:
            raise OidcError("already_linked", "Tài khoản Microsoft này đã được liên kết với người dùng khác")
        if account is None:
            user = (await db.session.execute(select(User).where(User.id == current_user_id))).scalar_one()
            await _link(db, user, claims)
            write_audit(
                db,
                action="auth.microsoft_linked",
                entity_type="user",
                entity_id=user.id,
                actor_user_id=user.id,
                meta=meta,
            )
        return None

    if mode == "invite":
        if not invite_token:
            raise OidcError("invite_invalid", "Thiếu lời mời")
        try:
            inv, membership, user = await accounts.accept_invitation(db, token=invite_token, password=None)
        except DomainError:
            raise OidcError("invite_invalid", "Lời mời không hợp lệ hoặc đã hết hạn") from None
        if inv.kind != "invite":
            raise OidcError("invite_invalid", "Liên kết này không phải lời mời tham gia")
        if account is not None and account.user_id != user.id:
            raise OidcError("already_linked", "Tài khoản Microsoft này đã được liên kết với người dùng khác")
        if account is None:
            await _link(db, user, claims)
        if membership.status == "invited":
            membership.status = "active"
        inv.used_at = datetime.now(UTC)
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)
        user.must_change_password = False
        return await _session_for(db, user, meta, action="auth.microsoft_invite_accepted")

    # mode == "login"
    if account is not None:
        user = (await db.session.execute(select(User).where(User.id == account.user_id))).scalar_one()
        has_membership = (
            await db.session.execute(select(OrgMembership.id).where(OrgMembership.user_id == user.id))
        ).scalar_one_or_none()
        if has_membership is None:
            # Đã có tài khoản ở tổ chức khác: vào tổ chức này với tư cách ứng viên nếu được phép tự đăng ký.
            if await org_settings.get(db, "microsoft_signup") != "on":
                raise OidcError("signup_disabled", "Tổ chức không cho tự tạo tài khoản bằng Microsoft")
            await _add_applicant_membership(db, user)
        return await _session_for(db, user, meta, action="auth.microsoft_login")

    user = await _self_signup(db, claims, meta)
    return await _session_for(db, user, meta, action="auth.microsoft_login")


__all__ = [
    "FLOW_COOKIE",
    "IdClaims",
    "MicrosoftProvider",
    "OidcError",
    "OidcProvider",
    "complete_login",
    "new_flow_secrets",
    "read_flow",
    "safe_next",
    "sign_flow",
    "validate_claims",
]
