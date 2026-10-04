from httpx import AsyncClient

from src.models import Organization

ALPHA = {"X-Organization": "alpha"}
BETA = {"X-Organization": "beta"}


async def login(client: AsyncClient, email: str, password: str, org: dict[str, str] = ALPHA):  # type: ignore[no-untyped-def]
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=org)


async def test_login_sets_cookies_and_returns_roles(client: AsyncClient, password: str) -> None:
    res = await login(client, "reviewer@alpha.test", password)
    assert res.status_code == 200
    body = res.json()
    assert body["roles"] == ["reviewer"]
    assert "application.review" in body["permissions"]
    assert body["organization"] == "alpha"
    set_cookie = res.headers.get_list("set-cookie")
    assert any("access_token=" in c and "HttpOnly" in c for c in set_cookie)
    assert any("refresh_token=" in c and "HttpOnly" in c for c in set_cookie)

    me = await client.get("/api/v1/me", headers=ALPHA)
    assert me.status_code == 200
    assert me.json()["email"] == "reviewer@alpha.test"


async def test_wrong_password_and_unknown_user_look_the_same(client: AsyncClient, password: str) -> None:
    bad = await login(client, "approver@alpha.test", "wrong-password")
    unknown = await login(client, "nobody@alpha.test", password)
    assert bad.status_code == unknown.status_code == 401
    strip = lambda body: {k: v for k, v in body.items() if k != "request_id"}  # noqa: E731
    assert strip(bad.json()) == strip(unknown.json())


async def test_user_of_other_org_cannot_login_here(client: AsyncClient, password: str) -> None:
    # tài khoản chỉ là thành viên của beta
    res = await login(client, "mentor@beta.test", password, ALPHA)
    assert res.status_code == 401


async def test_unknown_org_is_404_and_missing_org_is_400(client: AsyncClient, password: str) -> None:
    res = await login(client, "admin@alpha.test", password, {"X-Organization": "does-not-exist"})
    assert res.status_code == 404
    res = await client.post("/api/v1/auth/login", json={"email": "admin@alpha.test", "password": password})
    assert res.status_code == 400


async def test_token_is_not_valid_in_another_org(client: AsyncClient, password: str) -> None:
    res = await login(client, "admin@alpha.test", password)
    assert res.status_code == 200
    # cùng cookie, nhưng yêu cầu thuộc tổ chức beta
    cross = await client.get("/api/v1/me", headers=BETA)
    assert cross.status_code == 403


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/me", headers=ALPHA)).status_code == 401
    assert (await client.get("/api/v1/audit-logs", headers=ALPHA)).status_code == 401


async def test_permission_is_enforced(client: AsyncClient, password: str) -> None:
    await login(client, "applicant@alpha.test", password)
    assert (await client.get("/api/v1/audit-logs", headers=ALPHA)).status_code == 403
    client.cookies.clear()
    await login(client, "admin@alpha.test", password)
    res = await client.get("/api/v1/audit-logs", headers=ALPHA)
    assert res.status_code == 200
    assert any(item["action"] == "auth.login" for item in res.json()["items"])


async def test_audit_log_is_scoped_to_org(client: AsyncClient, password: str, orgs: dict[str, Organization]) -> None:
    await login(client, "admin@beta.test", password, BETA)
    res = await client.get("/api/v1/audit-logs?limit=200", headers=BETA)
    assert res.status_code == 200
    emails_in_alpha_only = [
        i
        for i in res.json()["items"]
        if i["entity_type"] == "user" and i["after"] and i["after"].get("email") == "reviewer@alpha.test"
    ]
    assert emails_in_alpha_only == []


async def test_lockout_after_repeated_failures(client: AsyncClient, password: str) -> None:
    for _ in range(5):
        assert (await login(client, "cohort_manager@alpha.test", "nope")).status_code == 401
    # đã khoá: ngay cả mật khẩu đúng cũng bị từ chối
    assert (await login(client, "cohort_manager@alpha.test", password)).status_code == 401


async def test_refresh_rotation_and_reuse_detection(client: AsyncClient, password: str) -> None:
    res = await login(client, "training_manager@alpha.test", password)
    first_refresh = client.cookies.get("refresh_token", path="/api/v1/auth")
    assert first_refresh

    rotated = await client.post("/api/v1/auth/refresh", headers=ALPHA)
    assert rotated.status_code == 200
    second_refresh = client.cookies.get("refresh_token", path="/api/v1/auth")
    assert second_refresh and second_refresh != first_refresh

    # trình lại token cũ đã được dùng: bị từ chối và thu hồi cả họ token
    client.cookies.set("refresh_token", first_refresh, path="/api/v1/auth")
    reuse = await client.post("/api/v1/auth/refresh", headers=ALPHA)
    assert reuse.status_code == 401
    client.cookies.set("refresh_token", second_refresh, path="/api/v1/auth")
    after = await client.post("/api/v1/auth/refresh", headers=ALPHA)
    assert after.status_code == 401
    assert res.status_code == 200


async def test_logout_revokes_refresh_token(client: AsyncClient, password: str) -> None:
    await login(client, "approver@alpha.test", password)
    refresh = client.cookies.get("refresh_token", path="/api/v1/auth")
    out = await client.post("/api/v1/auth/logout", headers=ALPHA)
    assert out.status_code == 204
    client.cookies.set("refresh_token", refresh, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh", headers=ALPHA)).status_code == 401


async def test_must_change_password_blocks_until_changed(client: AsyncClient, password: str) -> None:
    res = await login(client, "newbie@alpha.test", password)
    assert res.json()["must_change_password"] is True
    assert (await client.get("/api/v1/audit-logs", headers=ALPHA)).status_code == 403

    same = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": password, "new_password": password},
        headers=ALPHA,
    )
    assert same.status_code == 400
    short = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": password, "new_password": "short"},
        headers=ALPHA,
    )
    assert short.status_code == 400
    assert short.headers["content-type"].startswith("application/problem+json")
    own_name = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": password, "new_password": "newbie-is-me-123"},
        headers=ALPHA,
    )
    assert own_name.status_code == 400

    ok = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": password, "new_password": "A-new-strong-pass-1"},
        headers=ALPHA,
    )
    assert ok.status_code == 204
    assert (await client.get("/api/v1/audit-logs", headers=ALPHA)).status_code == 200


async def test_cross_origin_write_is_rejected(client: AsyncClient, password: str) -> None:
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.test", "password": password},
        headers={**ALPHA, "Origin": "https://evil.example"},
    )
    assert res.status_code == 403
    ok = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.test", "password": password},
        headers={**ALPHA, "Origin": "http://localhost:3000"},
    )
    assert ok.status_code == 200


async def test_health(client: AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).json() == {"status": "ready"}
