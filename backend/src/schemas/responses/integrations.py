"""Phản hồi cho tích hợp: khoá API, LMS, CRM."""

import uuid
from datetime import datetime

from src.schemas.responses.common import Out


class IntegrationKeyOut(Out):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class IntegrationKeyCreatedOut(Out):
    key: IntegrationKeyOut
    token: str  # chỉ trả về đúng một lần khi tạo


class LmsLearnerOut(Out):
    enrollment_id: uuid.UUID
    candidate_code: str
    email: str
    full_name: str
    status: str
    track: str | None
    class_name: str | None


class LmsPushError(Out):
    index: int
    external_ref: str
    error: str


class LmsPushOut(Out):
    created: int
    duplicates: int
    errors: list[LmsPushError]


class CrmApplicationOut(Out):
    application_id: uuid.UUID
    candidate_code: str
    full_name: str | None
    email: str
    phone: str | None
    intake: str
    status: str
    current_round: str | None
    submitted_at: datetime | None
    updated_at: datetime


class CrmChangesOut(Out):
    items: list[CrmApplicationOut]
    next_cursor: str | None
