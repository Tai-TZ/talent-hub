"""Luồng đăng nhập Microsoft với IdP giả: PKCE/state, tự đăng ký ứng viên, lời mời nhân sự, liên kết, nOAuth, tenant, tổ chức."""

import base64
import hashlib
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.services import oidc

TENANT = "22222222-2222-2222-2222-222222222222"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"


class FakeProvider:
    """Giả lập Microsoft: kiểm tra PKCE và nonce đúng như IdP thật, trả ID token đã 'xác minh' theo mã."""

    def __init__(self) -> None:
        self.codes: dict[str, oidc.IdClaims] = {}
        self._issued: dict[str, tuple[str, str]] = {}  # state -> (nonce, challenge)
        self.last_url = ""

    def add(
        self, code: str, *, sub: str, email: str | None = None, name: str = "Người Dùng Ms", tid: str = TENANT
    ) -> str:
        self.codes[code] = oidc.IdClaims(
            issuer=f"https://login.microsoftonline.com/{tid}/v2.0", subject=sub, tenant_id=tid, name=name, email=email
        )
        return code

    def authorize_url(self, *, state: str, nonce: str, challenge: str) -> str:
        self._issued[state] = (nonce, challenge)
        self.last_url = f"https://idp.test/authorize?state={state}&nonce={nonce}&code_challenge={challenge}&code_challenge_method=S256"
        return self.last_url

    async def exchange(self, *, code: str, verifier: str, nonce: str) -> oidc.IdClaims:
        issued = [v for v in self._issued.values() if v[0] == nonce]
        if not issued:
            raise oidc.OidcError("token_invalid", "nonce lạ")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if issued[0][1] != challenge:
            raise oidc.OidcError("exchange_failed", "PKCE verifier không khớp challenge")
        if code not in self.codes:
            raise oidc.OidcError("exchange_failed", "mã không hợp lệ")
        return self.codes.pop(code)


@pytest_asyncio.fixture
async def idp(app_instance: FastAPI) -> AsyncIterator[FakeProvider]:
    provider = FakeProvider()
    app_instance.state.oidc_provider = provider
    yield provider
    app_instance.state.oidc_provider = None


def _client(app: FastAPI, org: str = "alpha") -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Organization": org})


async def _sign_in(c: AsyncClient, idp: FakeProvider, code: str, *, next: str | None = None, extra: str = "") -> Any:
    """start → (IdP) → callback; trả phản hồi của callback."""
    query = f"?next={next}" if next else ""
    query += ("&" if query else "?") + extra.lstrip("&") if extra else ""
    started = await c.get(f"/api/v1/auth/microsoft/start{query}")
    assert started.status_code == 303, started.text
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    return await c.get(f"/api/v1/auth/microsoft/callback?code={code}&state={state}")


def _error(res: Any) -> str:
    assert res.status_code == 303
    loc = res.headers["location"]
    assert loc.startswith("/login?error="), loc
    return loc.split("=", 1)[1]


async def test_start_redirects_with_pkce_state_nonce_and_sets_signed_cookie(
    app_instance: FastAPI, idp: FakeProvider
) -> None:
    async with _client(app_instance) as c:
        res = await c.get("/api/v1/auth/microsoft/start?next=/staff/queue")
        assert res.status_code == 303
        q = parse_qs(urlparse(res.headers["location"]).query)
        assert q["code_challenge_method"] == ["S256"] and len(q["state"][0]) >= 40 and q["nonce"][0] != q["state"][0]
        cookie = res.headers["set-cookie"]
        assert (
            "ms_oidc=" in cookie
            and "HttpOnly" in cookie
            and "SameSite=lax" in cookie
            and "Path=/api/v1/auth/microsoft" in cookie
        )


async def test_new_applicant_can_sign_up_with_microsoft_and_gets_a_working_session(
    app_instance: FastAPI, idp: FakeProvider
) -> None:
    sub = f"sub-{uuid.uuid4().hex}"
    email = f"{sub}@outlook.test"
    async with _client(app_instance) as c:
        res = await _sign_in(c, idp, idp.add("c1", sub=sub, email=email, name="Lê Thị Ms"), next="/apply")
        assert res.status_code == 303 and res.headers["location"] == "/apply"
        cookies = "".join(res.headers.get_list("set-cookie"))
        assert (
            "access_token=" in cookies and "refresh_token=" in cookies and "ms_oidc=" in cookies
        )  # cookie luồng bị xoá
        me = (await c.get("/api/v1/me")).json()
        assert me["email"] == email and me["roles"] == ["applicant"] and me["full_name"] == "Lê Thị Ms"
        assert me["must_change_password"] is False

    # Lần sau cùng (issuer, subject) vào lại đúng tài khoản cũ, không tạo thêm.
    async with _client(app_instance) as c2:
        res = await _sign_in(c2, idp, idp.add("c2", sub=sub, email="doi-email-khac@outlook.test"))
        assert res.headers["location"] == "/dashboard"
        assert (await c2.get("/api/v1/me")).json()["email"] == email


async def test_open_redirect_in_next_is_neutralised(app_instance: FastAPI, idp: FakeProvider) -> None:
    async with _client(app_instance) as c:
        res = await _sign_in(
            c, idp, idp.add("c1", sub=f"s-{uuid.uuid4().hex}", email=f"{uuid.uuid4().hex}@o.test"), next="//evil.com"
        )
        assert res.headers["location"] == "/dashboard"


async def test_noauth_email_claim_never_logs_into_or_merges_with_an_existing_account(
    app_instance: FastAPI, idp: FakeProvider
) -> None:
    """Kẻ tấn công dựng tenant Entra riêng, đặt email trùng nạn nhân. Không được vào tài khoản nạn nhân."""
    async with _client(app_instance) as c:
        res = await _sign_in(
            c,
            idp,
            idp.add(
                "evil", sub="attacker-sub", email="applicant@alpha.test", tid="99999999-9999-9999-9999-999999999999"
            ),
        )
        assert _error(res) == "account_exists"
        assert (await c.get("/api/v1/me")).status_code == 401  # không có phiên

    # Nạn nhân vẫn đăng nhập bình thường và không có liên kết lạ.
    victim = await _client(app_instance).post(
        "/api/v1/auth/login", json={"email": "applicant@alpha.test", "password": "Passw0rd!test"}
    )
    assert victim.status_code == 200


async def test_state_mismatch_missing_cookie_and_replayed_code_are_rejected(
    app_instance: FastAPI, idp: FakeProvider
) -> None:
    async with _client(app_instance) as c:
        await c.get("/api/v1/auth/microsoft/start")
        res = await c.get("/api/v1/auth/microsoft/callback?code=x&state=state-gia-mao")
        assert _error(res) == "state_mismatch"

    async with _client(app_instance) as fresh:  # không có cookie luồng (mở thẳng callback)
        assert _error(await fresh.get("/api/v1/auth/microsoft/callback?code=x&state=y")) == "expired"

    async with _client(app_instance) as c:
        sub = f"s-{uuid.uuid4().hex}"
        ok = await _sign_in(c, idp, idp.add("once", sub=sub, email=f"{sub}@o.test"))
        assert ok.status_code == 303 and not ok.headers["location"].startswith("/login")
        started = await c.get("/api/v1/auth/microsoft/start")
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        replay = await c.get(f"/api/v1/auth/microsoft/callback?code=once&state={state}")
        assert _error(replay) == "exchange_failed"  # mã chỉ dùng một lần


async def test_user_cancelling_at_microsoft_returns_to_login_with_message_code(
    app_instance: FastAPI, idp: FakeProvider
) -> None:
    async with _client(app_instance) as c:
        started = await c.get("/api/v1/auth/microsoft/start")
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        res = await c.get(f"/api/v1/auth/microsoft/callback?error=access_denied&state={state}")
        assert _error(res) == "cancelled"


async def test_flow_started_in_one_org_cannot_be_completed_in_another(app_instance: FastAPI, idp: FakeProvider) -> None:
    async with _client(app_instance, "alpha") as c:
        started = await c.get("/api/v1/auth/microsoft/start")
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        c.headers["X-Organization"] = "beta"  # cùng cookie, callback đến tổ chức khác
        res = await c.get(
            f"/api/v1/auth/microsoft/callback?code={idp.add('x', sub='s-cross', email='cross@o.test')}&state={state}"
        )
        assert _error(res) == "state_mismatch"


async def test_staff_invitation_binds_microsoft_without_matching_email(
    app_instance: FastAPI, idp: FakeProvider, login_as: Callable[..., Any]
) -> None:
    admin = await login_as("admin")
    invited = f"giangvien.{uuid.uuid4().hex[:8]}@alpha.test"
    created = (
        await admin.post(
            "/api/v1/admin/users", json={"email": invited, "full_name": "Giảng viên", "roles": ["reviewer"]}
        )
    ).json()
    token = created["invite_link"].rsplit("/", 1)[1]
    sub = f"gv-{uuid.uuid4().hex}"

    async with _client(app_instance) as c:
        # Email trong Microsoft hoàn toàn khác email được mời: vẫn gắn được vì token lời mời chứng minh quyền kiểm soát.
        res = await _sign_in(
            c, idp, idp.add("inv", sub=sub, email="ten.khac@truong.edu.vn"), extra=f"mode=invite&token={token}"
        )
        assert res.status_code == 303 and res.headers["location"] == "/dashboard"
        me = (await c.get("/api/v1/me")).json()
        assert me["email"] == invited and me["roles"] == ["reviewer"]

    # Lời mời chỉ dùng một lần; không dùng lại để gắn Microsoft thứ hai.
    async with _client(app_instance) as c2:
        res = await _sign_in(
            c2, idp, idp.add("inv2", sub=f"khac-{uuid.uuid4().hex}", email=None), extra=f"mode=invite&token={token}"
        )
        assert _error(res) == "invite_invalid"

    # Lần sau đăng nhập bằng Microsoft vào đúng nhân sự đó, không thành ứng viên mới.
    async with _client(app_instance) as c3:
        res = await _sign_in(c3, idp, idp.add("again", sub=sub, email="bat-ky@x.test"))
        assert res.headers["location"] == "/dashboard"
        assert (await c3.get("/api/v1/me")).json()["roles"] == ["reviewer"]


async def test_link_mode_requires_login_and_prevents_double_linking(
    app_instance: FastAPI, idp: FakeProvider, login_as: Callable[..., Any]
) -> None:
    sub = f"lk-{uuid.uuid4().hex}"
    async with _client(app_instance) as anonymous:
        res = await _sign_in(anonymous, idp, idp.add("a1", sub=sub), extra="mode=link")
        assert _error(res) == "login_required"

    reviewer = await login_as("reviewer")
    res = await _sign_in(reviewer, idp, idp.add("a2", sub=sub, email="whatever@x.test"), extra="mode=link")
    assert res.status_code == 303 and res.headers["location"] == "/account/password?linked=1"

    async with _client(app_instance) as c:  # từ nay đăng nhập bằng Microsoft vào đúng reviewer
        res = await _sign_in(c, idp, idp.add("a3", sub=sub))
        assert res.headers["location"] == "/dashboard"
        assert (await c.get("/api/v1/me")).json()["email"] == "reviewer@alpha.test"

    other = await login_as("reviewer2")  # tài khoản Microsoft đã gắn người khác không gắn được cho người thứ hai
    res = await _sign_in(other, idp, idp.add("a4", sub=sub), extra="mode=link")
    assert _error(res) == "already_linked"


async def test_tenant_allowlist_and_signup_switch_from_org_settings(
    app_instance: FastAPI, idp: FakeProvider, login_as: Callable[..., Any]
) -> None:
    admin = await login_as("admin", "beta")
    allowed = "55555555-5555-5555-5555-555555555555"
    try:
        assert (
            await admin.put("/api/v1/admin/settings", json={"values": {"microsoft_allowed_tenants": allowed}})
        ).status_code == 200
        async with _client(app_instance, "beta") as c:
            res = await _sign_in(
                c, idp, idp.add("t1", sub=f"s-{uuid.uuid4().hex}", email=f"{uuid.uuid4().hex}@o.test", tid=TENANT)
            )
            assert _error(res) == "tenant_not_allowed"
            res = await _sign_in(
                c, idp, idp.add("t2", sub=f"s-{uuid.uuid4().hex}", email=f"{uuid.uuid4().hex}@o.test", tid=allowed)
            )
            assert res.headers["location"] == "/dashboard"

        assert (
            await admin.put(
                "/api/v1/admin/settings", json={"values": {"microsoft_allowed_tenants": "", "microsoft_signup": "off"}}
            )
        ).status_code == 200
        async with _client(app_instance, "beta") as c:
            res = await _sign_in(c, idp, idp.add("t3", sub=f"s-{uuid.uuid4().hex}", email=f"{uuid.uuid4().hex}@o.test"))
            assert _error(res) == "signup_disabled"
        bad = await admin.put(
            "/api/v1/admin/settings", json={"values": {"microsoft_allowed_tenants": "khong-phai-guid"}}
        )
        assert bad.status_code == 422
    finally:
        await admin.put(
            "/api/v1/admin/settings", json={"values": {"microsoft_allowed_tenants": "", "microsoft_signup": "on"}}
        )


async def test_suspended_member_cannot_sign_in_with_microsoft(
    app_instance: FastAPI, idp: FakeProvider, login_as: Callable[..., Any]
) -> None:
    sub = f"sus-{uuid.uuid4().hex}"
    email = f"{sub}@o.test"
    async with _client(app_instance) as c:
        await _sign_in(c, idp, idp.add("s1", sub=sub, email=email))
    admin = await login_as("admin")
    users = (await admin.get(f"/api/v1/admin/users?q={email}&audience=applicant")).json()["items"]
    assert len(users) == 1
    assert (
        await admin.patch(f"/api/v1/admin/users/{users[0]['membership_id']}", json={"status": "suspended"})
    ).status_code == 200
    async with _client(app_instance) as c2:
        assert _error(await _sign_in(c2, idp, idp.add("s2", sub=sub))) == "not_allowed"


async def test_org_endpoint_advertises_microsoft_only_when_enabled(app_instance: FastAPI, idp: FakeProvider) -> None:
    async with _client(app_instance) as c:
        assert (await c.get("/api/v1/org")).json()["login_providers"] == ["microsoft"]
    app_instance.state.oidc_provider = None
    async with _client(app_instance) as c:
        res = await c.get("/api/v1/org")
        assert res.json()["login_providers"] == []  # chưa cấu hình client_id nên không hiện nút
        assert (await c.get("/api/v1/auth/microsoft/start")).status_code == 404
