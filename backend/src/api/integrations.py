"""Tích hợp: quản lý khoá API (admin), export CSV cho Power BI, đồng bộ LMS và CRM bằng khoá có phạm vi."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.deps import Principal, current_principal, request_meta, require
from src.models import IntegrationKey
from src.schemas.responses.integrations import (
    CrmChangesOut,
    IntegrationKeyCreatedOut,
    IntegrationKeyOut,
    LmsLearnerOut,
    LmsPushOut,
)
from src.services import integrations
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/integrations", tags=["integrations"])

Scope = Literal["export.read", "lms.read", "lms.write", "crm.read"]


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


async def _key(request: Request, db: OrgDb) -> IntegrationKey:
    token = _bearer(request)
    key = await integrations.authenticate(db, token) if token else None
    if key is None:
        raise HTTPException(status_code=401, detail="Khoá tích hợp không hợp lệ hoặc đã bị thu hồi")
    return key


def require_scope(scope: Scope) -> Callable[..., Awaitable[IntegrationKey]]:
    async def checker(request: Request, db: OrgDb = Depends(org_db)) -> IntegrationKey:
        key = await _key(request, db)
        if scope not in key.scopes:
            raise HTTPException(status_code=403, detail=f"Khoá không có phạm vi {scope}")
        return key

    return checker


# ---- Quản lý khoá (admin) ----


class KeyIn(BaseModel):
    name: Annotated[str, Field(min_length=3, max_length=120)]
    scopes: Annotated[list[Scope], Field(min_length=1, max_length=4)]


@router.get("/keys", response_model=list[IntegrationKeyOut])
async def list_keys(
    _: Principal = Depends(require("integration.manage")), db: OrgDb = Depends(org_db)
) -> list[dict[str, Any]]:
    return await integrations.list_keys(db)


@router.post("/keys", status_code=201, response_model=IntegrationKeyCreatedOut)
async def create_key(
    body: KeyIn,
    request: Request,
    principal: Principal = Depends(require("integration.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    key, token = await integrations.create_key(
        db, name=body.name, scopes=list(body.scopes), actor_user_id=principal.user_id, meta=request_meta(request)
    )
    await db.commit()
    return {"key": key, "token": token}


@router.post("/keys/{key_id}/revoke", response_model=IntegrationKeyOut)
async def revoke_key(
    key_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("integration.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await integrations.revoke_key(db, key_id, actor_user_id=principal.user_id, meta=request_meta(request))
    await db.commit()
    return out


# ---- Export CSV (Power BI) ----


@router.get("/exports/{dataset}.csv", response_class=Response)
async def export_csv(dataset: str, request: Request, db: OrgDb = Depends(org_db)) -> Response:
    """CSV đã khử định danh. Xác thực bằng khoá có `export.read` (Power BI) hoặc phiên đăng nhập có quyền export.read."""
    # Xác thực trước khi kiểm tra tên bộ dữ liệu: người chưa xác thực không dò được bộ nào tồn tại.
    if _bearer(request):
        key = await _key(request, db)
        if "export.read" not in key.scopes:
            raise HTTPException(status_code=403, detail="Khoá không có phạm vi export.read")
    else:
        principal = await current_principal(request, db)
        if "export.read" not in principal.permissions:
            raise HTTPException(status_code=403, detail="Không đủ quyền thực hiện thao tác này")
    if dataset not in integrations.EXPORTS:
        raise HTTPException(status_code=404, detail="Không có bộ dữ liệu này")
    body = await integrations.EXPORTS[dataset](db)
    await db.commit()  # lưu thời điểm dùng khoá
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="{dataset}.csv"'},
    )


# ---- LMS ----


class LmsAssessmentIn(BaseModel):
    external_ref: Annotated[str, Field(min_length=1, max_length=200)]
    candidate_code: Annotated[str, Field(min_length=1, max_length=16)]
    competency_code: Annotated[str, Field(min_length=1, max_length=40)]
    level: Annotated[int, Field(ge=1, le=10)]
    evidence: Annotated[str, Field(max_length=2000)] = ""
    assessed_at: datetime | None = None


class LmsPushIn(BaseModel):
    items: Annotated[list[LmsAssessmentIn], Field(min_length=1, max_length=1000)]


@router.get("/lms/roster", response_model=list[LmsLearnerOut])
async def lms_roster(
    cohort: Annotated[str, Query(min_length=1, max_length=40)],
    key: IntegrationKey = Depends(require_scope("lms.read")),
    db: OrgDb = Depends(org_db),
) -> list[dict[str, Any]]:
    out = await integrations.lms_roster(db, cohort)
    await db.commit()
    return out


@router.post("/lms/assessments", response_model=LmsPushOut)
async def lms_push(
    body: LmsPushIn,
    request: Request,
    key: IntegrationKey = Depends(require_scope("lms.write")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await integrations.lms_push_assessments(
        db, [i.model_dump() for i in body.items], key=key, meta=request_meta(request)
    )
    await db.commit()
    return out


# ---- CRM ----


@router.get("/crm/applications", response_model=CrmChangesOut)
async def crm_applications(
    request: Request,
    updated_since: datetime | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    key: IntegrationKey = Depends(require_scope("crm.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await integrations.crm_changes(
        db, updated_since=updated_since, cursor=cursor, limit=limit, key=key, meta=request_meta(request)
    )
    await db.commit()
    return out
