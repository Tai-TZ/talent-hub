"""Xác minh ID token Microsoft: chữ ký RS256, aud, iss theo tid, nonce, hạn dùng, chống hạ cấp thuật toán."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.config import Settings
from src.services import oidc

CLIENT_ID = "11111111-1111-1111-1111-111111111111"
TENANT = "22222222-2222-2222-2222-222222222222"
NONCE = "nonce-abc"


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _make_key(kid: str) -> tuple[Any, dict[str, str]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": _b64(numbers.n), "e": _b64(numbers.e)}
    return key, jwk


KEY, JWK = _make_key("kid-1")
OTHER_KEY, _ = _make_key("kid-1")  # cùng kid nhưng khoá khác: chữ ký không được khớp


def _claims(**override: Any) -> dict[str, Any]:
    now = int(time.time())
    base = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT_ID,
        "sub": "subject-1",
        "tid": TENANT,
        "nonce": NONCE,
        "iat": now,
        "exp": now + 600,
        "name": "Nguyễn An",
        "preferred_username": "An@Example.com",
    }
    return {**base, **override}


def _token(claims: dict[str, Any], key: Any = KEY, kid: str = "kid-1", alg: str = "RS256") -> str:
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


def _provider(tenant: str = "common", fetches: list[str] | None = None) -> oidc.MicrosoftProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if fetches is not None:
            fetches.append(str(request.url))
        return httpx.Response(200, json={"keys": [JWK]})

    settings = Settings(microsoft_client_id=CLIENT_ID, microsoft_client_secret="s", microsoft_tenant=tenant)
    return oidc.MicrosoftProvider(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def _verify(provider: oidc.MicrosoftProvider, token: str) -> oidc.IdClaims:
    return await provider._verify(token, NONCE)  # noqa: SLF001 - kiểm thử bước xác minh độc lập với bước đổi mã


async def test_valid_token_yields_identity_from_issuer_and_subject() -> None:
    claims = await _verify(_provider(), _token(_claims()))
    assert (claims.issuer, claims.subject, claims.tenant_id) == (
        f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "subject-1",
        TENANT,
    )
    assert claims.email == "an@example.com" and claims.name == "Nguyễn An"  # chỉ để hiển thị, không để định danh


@pytest.mark.parametrize(
    ("label", "token"),
    [
        ("sai chữ ký", _token(_claims(), key=OTHER_KEY)),
        ("sai audience", _token(_claims(aud="99999999-9999-9999-9999-999999999999"))),
        ("hết hạn", _token(_claims(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600))),
        ("thiếu sub", _token({k: v for k, v in _claims().items() if k != "sub"})),
        ("kid lạ", _token(_claims(), kid="khong-co")),
    ],
)
async def test_invalid_tokens_are_rejected(label: str, token: str) -> None:
    with pytest.raises(oidc.OidcError) as exc:
        await _verify(_provider(), token)
    assert exc.value.code == "token_invalid", label


def _forge_hs256_with_public_key() -> str:
    """Tấn công hạ cấp kinh điển: ký HS256 với khoá công khai RSA làm bí mật HMAC.

    PyJWT từ chối tự tạo token này nên dựng thủ công để mô phỏng đúng kẻ tấn công.
    """
    public_pem = KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    def enc(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    signing_input = f"{enc({'alg': 'HS256', 'typ': 'JWT', 'kid': 'kid-1'})}.{enc(_claims())}"
    signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


async def test_algorithm_downgrade_is_rejected() -> None:
    with pytest.raises(oidc.OidcError):
        await _verify(_provider(), _forge_hs256_with_public_key())
    unsigned = jwt.encode(_claims(), key=None, algorithm="none", headers={"kid": "kid-1"})
    with pytest.raises(oidc.OidcError):
        await _verify(_provider(), unsigned)


async def test_nonce_mismatch_and_issuer_tid_mismatch_are_rejected() -> None:
    with pytest.raises(oidc.OidcError):
        await _verify(_provider(), _token(_claims(nonce="khac")))
    # iss trỏ tenant này nhưng tid khai tenant khác: token giả mạo tenant.
    with pytest.raises(oidc.OidcError):
        await _verify(_provider(), _token(_claims(tid="33333333-3333-3333-3333-333333333333")))
    with pytest.raises(oidc.OidcError):
        await _verify(_provider(), _token(_claims(iss="https://evil.example.com/v2.0")))


async def test_configured_tenant_restricts_accepted_tenants() -> None:
    await _verify(_provider(tenant=TENANT), _token(_claims()))
    with pytest.raises(oidc.OidcError) as exc:
        await _verify(_provider(tenant="44444444-4444-4444-4444-444444444444"), _token(_claims()))
    assert exc.value.code == "tenant_not_allowed"


async def test_jwks_is_cached_and_refetched_only_for_unknown_kid() -> None:
    fetches: list[str] = []
    provider = _provider(fetches=fetches)
    await _verify(provider, _token(_claims()))
    await _verify(provider, _token(_claims(sub="subject-2")))
    assert len(fetches) == 1  # lần hai dùng bộ đệm
    with pytest.raises(oidc.OidcError):
        await _verify(provider, _token(_claims(), kid="moi-xoay-khoa"))
    assert len(fetches) == 3  # kid lạ: tải lại một lần rồi vẫn không thấy thì từ chối (không lặp vô hạn)


def test_pkce_challenge_is_s256_of_verifier() -> None:
    state, nonce, verifier, challenge = oidc.new_flow_secrets()
    assert len({state, nonce, verifier}) == 3 and len(verifier) >= 43
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/staff/queue?intake=1", "/staff/queue?intake=1"),
        ("//evil.com/phish", "/dashboard"),
        ("/\\evil.com", "/dashboard"),
        ("https://evil.com", "/dashboard"),
        ("javascript:alert(1)", "/dashboard"),
        ("/api/v1/admin/users", "/dashboard"),
        ("/login?error=x", "/dashboard"),
        ("/a\nb", "/dashboard"),
        (None, "/dashboard"),
        ("", "/dashboard"),
    ],
)
def test_safe_next_blocks_open_redirects(raw: str | None, expected: str) -> None:
    assert oidc.safe_next(raw) == expected


def test_flow_cookie_is_signed_and_expires() -> None:
    secret = "x" * 40
    token = oidc.sign_flow(secret, state="s", nonce="n")
    assert oidc.read_flow(secret, token)["state"] == "s"
    with pytest.raises(oidc.OidcError):
        oidc.read_flow("y" * 40, token)  # chữ ký sai
    with pytest.raises(oidc.OidcError):
        oidc.read_flow(secret, None)
    expired = jwt.encode({"exp": int(time.time()) - 5, "typ": "oidc-flow"}, secret, algorithm="HS256")
    with pytest.raises(oidc.OidcError):
        oidc.read_flow(secret, expired)
    other_type = jwt.encode({"exp": int(time.time()) + 50, "typ": "access"}, secret, algorithm="HS256")
    with pytest.raises(oidc.OidcError):
        oidc.read_flow(secret, other_type)
