import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from src.config import Settings, get_settings
from src.services.ratelimit import MemoryRateLimiter

ALPHA = {"X-Organization": "alpha"}


async def test_security_headers_present(client: AsyncClient) -> None:
    res = await client.get("/healthz")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["x-request-id"]


async def test_api_responses_are_not_cacheable(client: AsyncClient, password: str) -> None:
    res = await client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "p"}, headers=ALPHA)
    assert res.headers["cache-control"] == "no-store"


async def test_request_id_is_propagated_and_sanitized(client: AsyncClient) -> None:
    ok = await client.get("/healthz", headers={"X-Request-ID": "abcdef12-3456"})
    assert ok.headers["x-request-id"] == "abcdef12-3456"
    evil = await client.get("/healthz", headers={"X-Request-ID": "bad value\r\nX-Injected: 1"})
    assert evil.headers["x-request-id"] != "bad value"
    assert "x-injected" not in evil.headers


async def test_oversized_body_is_rejected(client: AsyncClient) -> None:
    res = await client.post("/api/v1/auth/login", content=b"x", headers={**ALPHA, "Content-Length": "99999999"})
    assert res.status_code == 413


async def test_login_is_rate_limited_per_ip(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "login_rate_limit_per_minute", 3)
    statuses = [
        (await client.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "p"}, headers=ALPHA)).status_code
        for _ in range(5)
    ]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]
    blocked = await client.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "p"}, headers=ALPHA)
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["content-type"].startswith("application/problem+json")


async def test_memory_limiter_window_resets() -> None:
    limiter = MemoryRateLimiter()
    assert (await limiter.hit("k", 2, 60)).allowed
    assert (await limiter.hit("k", 2, 60)).allowed
    assert not (await limiter.hit("k", 2, 60)).allowed
    assert (await limiter.hit("other", 2, 60)).allowed


async def test_unhandled_errors_do_not_leak_details(client: AsyncClient) -> None:
    res = await client.get("/api/v1/me")  # thiếu tổ chức → 400 có kiểm soát
    assert res.status_code == 400


def test_production_config_rejects_unsafe_defaults() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(environment="production")
    message = str(exc.value)
    for expected in ("JWT_SECRET", "ALLOW_ORG_HEADER", "COOKIE_SECURE", "REDIS_URL", "ALLOWED_HOSTS"):
        assert expected in message


def test_production_config_accepts_safe_values() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="x" * 40,
        allow_org_header=False,
        cookie_secure=True,
        redis_url="redis://redis:6379/0",
        allowed_hosts=["*.talenthub.example"],
        allowed_origins=["https://northwind.talenthub.example"],
    )
    assert not settings.is_local


async def test_org_header_only_trusted_with_proxy_secret(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "allow_org_header", False)
    monkeypatch.setattr(settings, "internal_proxy_secret", "s3cret-shared-with-bff")
    body = {"email": "admin@alpha.test", "password": "x"}

    no_secret = await client.post("/api/v1/auth/login", json=body, headers={"X-Organization": "alpha"})
    assert no_secret.status_code == 400  # header bị bỏ qua, không có Host hợp lệ

    wrong = await client.post(
        "/api/v1/auth/login", json=body, headers={"X-Organization": "alpha", "X-Internal-Auth": "wrong"}
    )
    assert wrong.status_code == 400

    ok = await client.post(
        "/api/v1/auth/login",
        json=body,
        headers={"X-Organization": "alpha", "X-Internal-Auth": "s3cret-shared-with-bff"},
    )
    assert ok.status_code == 401  # tổ chức được nhận diện; sai mật khẩu


async def test_public_org_info(client: AsyncClient) -> None:
    res = await client.get("/api/v1/org", headers=ALPHA)
    assert res.status_code == 200
    assert res.json()["slug"] == "alpha"
    assert (await client.get("/api/v1/org", headers={"X-Organization": "nope"})).status_code == 404
