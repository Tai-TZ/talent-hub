"""Xác định tổ chức của request và mở session có ngữ cảnh RLS (docs/09-multi-tenancy.md)."""

import hmac
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db import get_sessionmaker, set_org_context
from src.models import Organization


@dataclass
class OrgDb:
    session: AsyncSession
    org: Organization

    async def commit(self) -> None:
        """Commit rồi mở transaction mới và đặt lại ngữ cảnh tổ chức (SET LOCAL mất khi commit)."""
        await self.session.commit()
        await set_org_context(self.session, self.org.id)


def _is_trusted_proxy(request: Request) -> bool:
    secret = get_settings().internal_proxy_secret
    provided = request.headers.get("x-internal-auth")
    return bool(secret and provided and hmac.compare_digest(secret, provided))


def resolve_org_slug(request: Request) -> str | None:
    settings = get_settings()
    header = request.headers.get("x-organization")
    if header and (settings.allow_org_header or _is_trusted_proxy(request)):
        return header.strip().lower()
    host = request.headers.get("host", "").split(":")[0].lower()
    suffix = "." + settings.base_domain
    if host.endswith(suffix):
        label = host[: -len(suffix)]
        if label and "." not in label:
            return label
    return None


async def org_db(request: Request) -> AsyncIterator[OrgDb]:
    """Dependency: session đã đặt ngữ cảnh tổ chức. Handler tự commit khi ghi dữ liệu."""
    slug = resolve_org_slug(request)
    if not slug:
        raise HTTPException(status_code=400, detail="Không xác định được tổ chức của yêu cầu")
    async with get_sessionmaker()() as session:
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == slug, Organization.status == "active")
            )
        ).scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=404, detail="Tổ chức không tồn tại")
        await set_org_context(session, org.id)
        try:
            yield OrgDb(session=session, org=org)
        finally:
            await session.rollback()
