"""Thông tin công khai của tổ chức hiện tại, dùng cho trang đăng nhập (tên, ngôn ngữ, nhận diện)."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/org", tags=["org"])


class OrgOut(BaseModel):
    slug: str
    name: str
    default_locale: str
    branding: dict[str, Any]


@router.get("", response_model=OrgOut)
async def current_org(db: OrgDb = Depends(org_db)) -> OrgOut:
    org = db.org
    return OrgOut(slug=org.slug, name=org.name, default_locale=org.default_locale, branding=org.branding)
