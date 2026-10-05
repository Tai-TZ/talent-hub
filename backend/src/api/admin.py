"""Khu quản trị cho bộ phận IT: tài khoản, tài liệu, chi phí, cài đặt, tổng quan."""

import base64
import binascii
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.api.deps import Principal, request_meta, require
from src.errors import ValidationFailedError
from src.schemas.responses.admin import (
    AccountCreatedOut,
    AccountPageOut,
    AccountUpdatedOut,
    AiUsageRowOut,
    CostEntryOut,
    CostEntryPageOut,
    CostSummaryOut,
    DocumentDetailOut,
    DocumentOut,
    DocumentPageOut,
    ImportResultOut,
    InviteLinkOut,
    OverviewOut,
    QueuedOut,
    SearchHitOut,
    SettingsOut,
    SettingsValuesOut,
)
from src.services import accounts, costs, jobs, kb, org_settings, overview
from src.services import email as email_svc
from src.services.tenancy import OrgDb, org_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- Tổng quan ----------
@router.get("/overview", response_model=OverviewOut)
async def get_overview(_: Principal = Depends(require("audit.read")), db: OrgDb = Depends(org_db)) -> dict[str, Any]:
    return await overview.overview(db)


# ---------- Cài đặt ----------
class SettingsIn(BaseModel):
    values: dict[str, Any]


@router.get("/settings", response_model=SettingsOut)
async def get_settings_(_: Principal = Depends(require("user.manage")), db: OrgDb = Depends(org_db)) -> dict[str, Any]:
    values = await org_settings.get_all(db)
    spec = {
        k: {"description": v[2], "kind": v[1].kind, "options": list(v[1].options)} for k, v in org_settings.SPEC.items()
    }
    return {"values": values, "spec": spec}


@router.put("/settings", response_model=SettingsValuesOut)
async def put_settings(
    body: SettingsIn,
    request: Request,
    principal: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    from src.services.audit import write_audit

    values = await org_settings.update(db, body.values, actor_user_id=principal.user_id)
    write_audit(
        db,
        action="settings.updated",
        entity_type="org_settings",
        actor_user_id=principal.user_id,
        after=body.values,
        meta=request_meta(request),
    )
    await db.commit()
    return {"values": values}


# ---------- Tài khoản ----------
class AccountIn(BaseModel):
    email: str = Field(max_length=254)
    full_name: str = Field(max_length=200)
    roles: list[str] = Field(min_length=1, max_length=8)


class AccountPatch(BaseModel):
    roles: list[str] | None = Field(default=None, max_length=8)
    status: str | None = None


class ImportRow(BaseModel):
    email: str = Field(max_length=254)
    full_name: str = Field(max_length=200)
    roles: list[str] = Field(max_length=8)


class ImportIn(BaseModel):
    rows: Annotated[list[ImportRow], Field(min_length=1, max_length=1000)]
    dry_run: bool = True


@router.get("/users", response_model=AccountPageOut)
async def list_users(
    q: str | None = Query(None, max_length=100),
    role: str | None = None,
    status: str | None = Query(None, pattern="^(invited|active|suspended)$"),
    audience: str | None = Query(None, pattern="^(staff|applicant)$"),
    limit: int = Query(25, ge=1, le=100),
    cursor: uuid.UUID | None = None,
    _: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    items, next_cursor, total = await accounts.list_accounts(
        db, q=q, role=role, status=status, limit=limit, cursor=cursor, audience=audience
    )
    return {
        "items": items,
        "next_cursor": next_cursor,
        "total": total,
        "assignable_roles": sorted(accounts.ASSIGNABLE_ROLES),
    }


@router.post("/users", status_code=201, response_model=AccountCreatedOut)
async def create_user(
    body: AccountIn,
    request: Request,
    principal: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await accounts.create_account(
        db,
        actor_user_id=principal.user_id,
        email=body.email,
        full_name=body.full_name,
        roles=body.roles,
        meta=request_meta(request),
    )
    org_id = db.org.id
    await db.commit()
    jobs.background(email_svc.flush_outbox(org_id))
    return out


@router.post("/users/import", response_model=ImportResultOut)
async def import_users(
    body: ImportIn,
    request: Request,
    principal: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await accounts.import_accounts(
        db,
        actor_user_id=principal.user_id,
        rows=[r.model_dump() for r in body.rows],
        dry_run=body.dry_run,
        meta=request_meta(request),
    )
    org_id = db.org.id
    await db.commit()
    if not body.dry_run:
        jobs.background(email_svc.flush_outbox(org_id))
    return out


@router.patch("/users/{membership_id}", response_model=AccountUpdatedOut)
async def patch_user(
    membership_id: uuid.UUID,
    body: AccountPatch,
    request: Request,
    principal: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await accounts.update_account(
        db,
        actor_user_id=principal.user_id,
        membership_id=membership_id,
        roles=body.roles,
        status=body.status,
        meta=request_meta(request),
    )
    await db.commit()
    return out


@router.post("/users/{membership_id}/invite", response_model=InviteLinkOut)
async def resend_invite(
    membership_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    out = await accounts.resend_invitation(
        db, actor_user_id=principal.user_id, membership_id=membership_id, meta=request_meta(request)
    )
    org_id = db.org.id
    await db.commit()
    jobs.background(email_svc.flush_outbox(org_id))
    return out


@router.post("/users/{membership_id}/reset-password", status_code=202, response_model=QueuedOut)
async def reset_password(
    membership_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("user.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, str]:
    await accounts.request_password_reset(
        db, actor_user_id=principal.user_id, membership_id=membership_id, meta=request_meta(request)
    )
    org_id = db.org.id
    await db.commit()
    jobs.background(email_svc.flush_outbox(org_id))
    return {"status": "queued"}


# ---------- Tài liệu ----------
class DocumentIn(BaseModel):
    title: str = Field(max_length=200)
    visibility: str = "public"
    filename: str = Field(max_length=255)
    content_base64: str


@router.get("/documents", response_model=DocumentPageOut)
async def list_documents(
    status: str | None = Query(None, pattern="^(ready|failed|retired)$"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    _: Principal = Depends(require("kb.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    docs, total = await kb.list_documents(db, status=status, limit=limit, offset=offset)
    return {"items": [kb.doc_out(d) for d in docs], "total": total}


@router.post("/documents", status_code=201, response_model=DocumentOut)
async def add_document(
    body: DocumentIn,
    request: Request,
    principal: Principal = Depends(require("kb.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationFailedError("Nội dung tệp không hợp lệ", {"file": "Không giải mã được"}) from None
    doc = await kb.create_document(
        db,
        actor_user_id=principal.user_id,
        title=body.title,
        visibility=body.visibility,
        filename=body.filename,
        data=data,
        meta=request_meta(request),
    )
    out = kb.doc_out(doc)
    await db.commit()
    return out


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
async def get_document(
    doc_id: uuid.UUID, _: Principal = Depends(require("kb.manage")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    doc = await kb.get_document(db, doc_id)
    return {**kb.doc_out(doc), "preview": await kb.preview_chunks(db, doc_id)}


@router.post("/documents/{doc_id}/retire", response_model=DocumentOut)
async def retire_document(
    doc_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("kb.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    doc = await kb.set_status(db, doc_id, "retired", actor_user_id=principal.user_id, meta=request_meta(request))
    out = kb.doc_out(doc)
    await db.commit()
    return out


@router.post("/documents/{doc_id}/restore", response_model=DocumentOut)
async def restore_document(
    doc_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require("kb.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    doc = await kb.set_status(db, doc_id, "ready", actor_user_id=principal.user_id, meta=request_meta(request))
    out = kb.doc_out(doc)
    await db.commit()
    return out


@router.get("/documents-search", response_model=list[SearchHitOut])
async def search_documents(
    q: str = Query(min_length=1, max_length=300),
    _: Principal = Depends(require("kb.manage")),
    db: OrgDb = Depends(org_db),
) -> list[dict[str, Any]]:
    """Cho IT thử tìm kiếm để kiểm tra tài liệu đã được lập chỉ mục đúng (gồm cả tài liệu nội bộ)."""
    return await kb.search(db, q, visibility=["public", "internal"], limit=8)


# ---------- Chi phí ----------
class CostIn(BaseModel):
    category: str
    amount_vnd: Decimal
    occurred_on: date
    cohort_id: uuid.UUID | None = None
    description: str = Field(default="", max_length=500)


class VoidIn(BaseModel):
    reason: str = Field(max_length=300)


class BudgetIn(BaseModel):
    cohort_id: uuid.UUID | None = None
    category: str | None = None
    amount_vnd: Decimal


def _entry_out(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "category": e.category,
        "amount_vnd": float(e.amount_vnd),
        "occurred_on": e.occurred_on,
        "cohort_id": e.cohort_id,
        "description": e.description,
        "source": e.source,
        "voided": e.voided_at is not None,
        "void_reason": e.void_reason,
        "created_at": e.created_at,
    }


@router.get("/costs/summary", response_model=CostSummaryOut)
async def costs_summary(
    cohort_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _: Principal = Depends(require("cost.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    return await costs.summary(db, cohort_id=cohort_id, date_from=date_from, date_to=date_to)


@router.get("/costs/entries", response_model=CostEntryPageOut)
async def costs_entries(
    category: str | None = None,
    cohort_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    _: Principal = Depends(require("cost.read")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    rows, total = await costs.list_entries(
        db, category=category, cohort_id=cohort_id, date_from=date_from, date_to=date_to, limit=limit, offset=offset
    )
    return {"items": [_entry_out(e) for e in rows], "total": total}


@router.post("/costs/entries", status_code=201, response_model=CostEntryOut)
async def costs_add(
    body: CostIn, request: Request, principal: Principal = Depends(require("cost.manage")), db: OrgDb = Depends(org_db)
) -> dict[str, Any]:
    entry = await costs.add_entry(
        db,
        actor_user_id=principal.user_id,
        category=body.category,
        amount_vnd=body.amount_vnd,
        occurred_on=body.occurred_on,
        cohort_id=body.cohort_id,
        description=body.description,
        meta=request_meta(request),
    )
    out = _entry_out(entry)
    await db.commit()
    return out


@router.post("/costs/entries/{entry_id}/void", response_model=CostEntryOut)
async def costs_void(
    entry_id: uuid.UUID,
    body: VoidIn,
    request: Request,
    principal: Principal = Depends(require("cost.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, Any]:
    entry = await costs.void_entry(
        db, entry_id, reason=body.reason, actor_user_id=principal.user_id, meta=request_meta(request)
    )
    out = _entry_out(entry)
    await db.commit()
    return out


@router.put("/costs/budgets", response_model=QueuedOut)
async def costs_budget(
    body: BudgetIn,
    request: Request,
    principal: Principal = Depends(require("cost.manage")),
    db: OrgDb = Depends(org_db),
) -> dict[str, str]:
    await costs.upsert_budget(
        db,
        actor_user_id=principal.user_id,
        cohort_id=body.cohort_id,
        category=body.category,
        amount_vnd=body.amount_vnd,
        meta=request_meta(request),
    )
    await db.commit()
    return {"status": "saved"}


@router.get("/costs/ai", response_model=list[AiUsageRowOut])
async def costs_ai(
    group: str = Query("feature", pattern="^(feature|model|day)$"),
    _: Principal = Depends(require("cost.read")),
    db: OrgDb = Depends(org_db),
) -> list[dict[str, Any]]:
    return await costs.ai_breakdown(db, group=group)
