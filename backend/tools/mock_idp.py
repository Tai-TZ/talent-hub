"""IdP OIDC giả (giống Microsoft Entra v2.0) CHỈ để phát triển và kiểm thử cục bộ, không cần tài khoản Entra.

Chạy:  python tools/mock_idp.py            (cổng 9100, chỉ lắng nghe 127.0.0.1)
Backend:  MICROSOFT_AUTHORITY=http://localhost:9100 MICROSOFT_CLIENT_ID=dev-client MICROSOFT_CLIENT_SECRET=dev-secret

Hỗ trợ đúng phần của giao thức mà backend dùng: authorize (trang chọn người dùng), token (kiểm PKCE S256 và
client_secret, mã dùng một lần), JWKS, ID token RS256 có nonce/aud/iss/tid. KHÔNG dùng ngoài máy phát triển.
"""

import base64
import hashlib
import html
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

CLIENT_ID = "dev-client"
CLIENT_SECRET = "dev-secret"
DEFAULT_TENANT = "7a1f0c2e-5b6d-4e8a-9c3b-1d2e3f4a5b6c"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "mock-idp-key"
CODES: dict[str, dict[str, Any]] = {}

PERSONAS = [
    ("Nguyễn Minh Anh", "minhanh@outlook.com", DEFAULT_TENANT, "Ứng viên (tài khoản Microsoft)"),
    ("Trần Giang Viên", "giangvien@northwind.example.edu", DEFAULT_TENANT, "Giảng viên (tài khoản cơ quan)"),
    (
        "Kẻ Mạo Danh",
        "applicant@northwind.test",
        "99999999-9999-9999-9999-999999999999",
        "Tenant lạ đặt email trùng người khác (nOAuth)",
    ),
]

app = FastAPI(title="Mock Entra IdP (dev only)")


def _b64(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()


@app.get("/{tenant}/discovery/v2.0/keys")
def keys(tenant: str) -> dict[str, Any]:
    nums = KEY.public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID, "n": _b64(nums.n), "e": _b64(nums.e)}]}


@app.get("/{tenant}/oauth2/v2.0/authorize", response_class=HTMLResponse)
def authorize(
    tenant: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    code_challenge_method: str = "S256",
    response_type: str = "code",
    scope: str = "",
    response_mode: str = "query",
    prompt: str = "",
) -> str:
    if client_id != CLIENT_ID or code_challenge_method != "S256" or response_type != "code":
        raise HTTPException(400, "invalid_request")
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(v)}">'
        for k, v in {"redirect_uri": redirect_uri, "state": state, "nonce": nonce, "challenge": code_challenge}.items()
    )
    cards = "".join(
        f'<form method="post" action="/confirm">{hidden}<input type="hidden" name="name" value="{html.escape(n)}">'
        f'<input type="hidden" name="email" value="{html.escape(e)}"><input type="hidden" name="tid" value="{t}">'
        f'<button type="submit" style="width:100%;text-align:left;padding:12px;margin:6px 0"><b>{html.escape(n)}</b><br>{html.escape(e)}<br><small>{html.escape(d)}</small></button></form>'
        for n, e, t, d in PERSONAS
    )
    return (
        '<!doctype html><meta charset="utf-8"><title>Mock Microsoft</title>'
        '<body style="font-family:system-ui;max-width:420px;margin:40px auto">'
        "<h2>Đăng nhập Microsoft (GIẢ LẬP, chỉ để dev)</h2><p>Chọn một tài khoản để mô phỏng:</p>"
        f"{cards}<hr><form method='post' action='/confirm'>{hidden}"
        "<label>Họ tên <input name='name' value='Người Dùng Thử'></label><br>"
        "<label>Email <input name='email' value='thu@example.com'></label><br>"
        f"<input type='hidden' name='tid' value='{DEFAULT_TENANT}'><button type='submit'>Đăng nhập</button></form></body>"
    )


async def _form(request: Request) -> dict[str, str]:
    """Đọc application/x-www-form-urlencoded không cần python-multipart (công cụ dev, tránh thêm phụ thuộc)."""
    parsed = parse_qs((await request.body()).decode(), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


@app.post("/confirm")
async def confirm(request: Request) -> RedirectResponse:
    f = await _form(request)
    code = secrets.token_urlsafe(24)
    sub = (
        base64.urlsafe_b64encode(hashlib.sha256(f"{f['tid']}:{f['email']}".encode()).digest())
        .rstrip(b"=")
        .decode()[:30]
    )
    CODES[code] = {
        "nonce": f["nonce"],
        "challenge": f["challenge"],
        "name": f["name"],
        "email": f["email"],
        "tid": f["tid"],
        "sub": sub,
    }
    return RedirectResponse(f"{f['redirect_uri']}?{urlencode({'code': code, 'state': f['state']})}", status_code=303)


@app.post("/{tenant}/oauth2/v2.0/token")
async def token(tenant: str, request: Request) -> dict[str, Any]:
    f = await _form(request)
    entry = CODES.pop(f.get("code", ""), None)  # dùng một lần
    if (
        f.get("grant_type") != "authorization_code"
        or entry is None
        or f.get("client_id") != CLIENT_ID
        or f.get("client_secret") != CLIENT_SECRET
    ):
        raise HTTPException(400, "invalid_grant")
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(f.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
    )
    if expected != entry["challenge"]:
        raise HTTPException(400, "invalid_grant: PKCE")
    now = int(time.time())
    claims = {
        "iss": f"http://localhost:9100/{entry['tid']}/v2.0",
        "aud": CLIENT_ID,
        "sub": entry["sub"],
        "tid": entry["tid"],
        "nonce": entry["nonce"],
        "name": entry["name"],
        "preferred_username": entry["email"],
        "iat": now,
        "exp": now + 3600,
    }
    return {"token_type": "Bearer", "id_token": jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": KID})}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9100, log_level="warning")
