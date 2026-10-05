"""Phản hồi cho khu quản trị IT: tổng quan, tài khoản, tài liệu, chi phí, cài đặt."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from src.schemas.responses.common import Out

# ---------- Tổng quan ----------


class OverviewUsers(Out):
    by_status: dict[str, int]
    active_by_role: dict[str, int]
    locked: int


class OverviewSecurity(Out):
    logins: int
    failed_logins: int


class OverviewEmail(Out):
    backend: str
    queue: dict[str, int]


class OverviewAi(Out):
    engine: str
    llm_configured: bool
    model: str
    month_to_date_usd: float
    monthly_budget_usd: float


class OverviewOut(Out):
    users: OverviewUsers
    intakes: dict[str, int]
    pending_decisions: int
    jobs_24h: dict[str, int]
    security_24h: OverviewSecurity
    email: OverviewEmail
    documents: dict[str, int]
    ai: OverviewAi


# ---------- Cài đặt ----------


class SettingsOut(Out):
    values: dict[str, Any]
    spec: dict[str, str]


class SettingsValuesOut(Out):
    values: dict[str, Any]


# ---------- Tài khoản ----------


class AccountOut(Out):
    membership_id: uuid.UUID
    email: str
    full_name: str
    status: str
    roles: list[str]
    last_login_at: datetime | None
    locked: bool
    has_password: bool
    created_at: datetime


class AccountPageOut(Out):
    items: list[AccountOut]
    next_cursor: uuid.UUID | None
    total: int
    assignable_roles: list[str]


class AccountCreatedOut(Out):
    membership_id: uuid.UUID
    email: str
    roles: list[str]
    status: str
    invite_link: str | None


class AccountUpdatedOut(Out):
    membership_id: uuid.UUID
    roles: list[str]
    status: str


class InviteLinkOut(Out):
    invite_link: str | None


class QueuedOut(Out):
    status: str


class ImportRowOut(Out):
    row: int
    email: str
    status: Literal["ok", "created", "error"]
    error: str | None = None
    invite_link: str | None = None


class ImportSummaryOut(Out):
    ok: int
    created: int
    error: int


class ImportResultOut(Out):
    dry_run: bool
    summary: ImportSummaryOut
    rows: list[ImportRowOut]


# ---------- Tài liệu ----------


class DocumentOut(Out):
    id: uuid.UUID
    title: str
    visibility: str
    filename: str
    size_bytes: int
    char_count: int
    chunk_count: int
    status: str
    version: int
    created_at: datetime


class DocumentPageOut(Out):
    items: list[DocumentOut]
    total: int


class ChunkPreviewOut(Out):
    ordinal: int
    heading: str | None
    content: str


class DocumentDetailOut(DocumentOut):
    preview: list[ChunkPreviewOut]


class SearchHitOut(Out):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    visibility: str
    heading: str | None
    snippet: str
    score: float


# ---------- Chi phí ----------


class CostEntryOut(Out):
    id: uuid.UUID
    category: str
    amount_vnd: float
    occurred_on: date
    cohort_id: uuid.UUID | None
    description: str
    source: str
    voided: bool
    void_reason: str | None
    created_at: datetime


class CostEntryPageOut(Out):
    items: list[CostEntryOut]
    total: int


class BurnOut(Out):
    budget: float | None
    spent: float
    ratio: float | None
    status: Literal["none", "ok", "warning", "over"]


class CategoryBurnOut(BurnOut):
    amount: float


class CostAlertOut(Out):
    scope: str
    status: str
    ratio: float | None


class CostTimelineOut(Out):
    month: str
    total: float
    by_category: dict[str, float]


class CostAiOut(Out):
    usd: float
    vnd: float
    tokens: int
    calls: int
    month_to_date_usd: float


class CostSummaryOut(Out):
    currency: str
    usd_vnd_rate: float
    total: float
    overall: BurnOut
    by_category: dict[str, CategoryBurnOut]
    timeline: list[CostTimelineOut]
    ai: CostAiOut
    accepted_count: int
    cost_per_accepted: float | None
    alerts: list[CostAlertOut]


class AiUsageRowOut(Out):
    key: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    calls: int
