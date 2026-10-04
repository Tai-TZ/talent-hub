import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from src.config import get_settings

_hasher = PasswordHasher()
# Dùng để tốn thời gian tương đương khi email không tồn tại, tránh lộ thông tin qua độ trễ.
DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

ALGORITHM = "HS256"
_hash_slots: asyncio.Semaphore | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _slots() -> asyncio.Semaphore:
    global _hash_slots
    if _hash_slots is None:
        _hash_slots = asyncio.Semaphore(get_settings().password_hash_concurrency)
    return _hash_slots


async def hash_password_async(password: str) -> str:
    """Argon2 chạy ngoài event loop và bị giới hạn đồng thời (mỗi lần băm tốn ~64 MiB)."""
    async with _slots():
        return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password_hash: str, password: str) -> bool:
    async with _slots():
        return await asyncio.to_thread(verify_password, password_hash, password)


def create_access_token(*, user_id: uuid.UUID, org_id: uuid.UUID, membership_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user_id),
        "org": str(org_id),
        "mid": str(membership_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    claims: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "org", "mid", "typ"]},
    )
    if claims["typ"] != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
