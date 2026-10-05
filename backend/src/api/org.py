"""Thông tin công khai của tổ chức hiện tại, dùng cho trang đăng nhập (tên, ngôn ngữ, nhận diện)."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.config import get_settings
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/org", tags=["org"])


class OrgOut(BaseModel):
    slug: str
    name: str
    default_locale: str
    branding: dict[str, Any]
    login_providers: list[str]


@router.get("", response_model=OrgOut)
async def current_org(request: Request, db: OrgDb = Depends(org_db)) -> OrgOut:
    org = db.org
    providers = (
        ["microsoft"] if getattr(request.app.state, "oidc_provider", None) or get_settings().microsoft_enabled else []
    )
    return OrgOut(
        slug=org.slug,
        name=org.name,
        default_locale=org.default_locale,
        branding=org.branding,
        login_providers=providers,
    )
