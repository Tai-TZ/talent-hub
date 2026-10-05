"""Phản hồi cho khu vực nhân sự: hàng đợi, bàn làm việc hồ sơ, phê duyệt, sàng lọc AI."""

import uuid
from datetime import datetime
from typing import Any, Literal

from src.schemas.responses.applicant import ApplicationViewOut
from src.schemas.responses.common import FlagOut, Out, RoundOut

# ---------- Hàng đợi ----------


class QueueItemOut(Out):
    id: uuid.UUID
    candidate_code: str
    name: str | None
    status: str
    current_round: str | None
    submitted_at: datetime | None
    flag_count: int
    review_count: int
    my_review: Literal["draft", "submitted"] | None
    ai_attention: bool | None
    # Chỉ có khi người xem có quyền triage.read.
    ai_tier: str | None = None
    ai_score: float | None = None


class QueuePageOut(Out):
    items: list[QueueItemOut]
    next_cursor: str | None
    total: int
    blind_review: bool


# ---------- Bàn làm việc hồ sơ ----------


class CriterionOut(Out):
    id: str
    name: str
    description: str = ""
    weight: float
    max: float
    kind: str = "custom"


class RubricOut(Out):
    version: int
    criteria: list[CriterionOut]


class RubricSavedOut(RubricOut):
    round: str


class AiScoreOut(Out):
    score: float
    max: float
    confidence: float
    rationale: str = ""


class EvidenceOut(Out):
    field: str
    quote: str
    start: int
    end: int


class AiAssessmentOut(Out):
    locked: Literal[False] = False
    engine: str
    model: str | None
    prompt_version: str
    total_score: float
    confidence: float
    tier: str
    needs_attention: bool
    scores: dict[str, AiScoreOut]
    evidence: dict[str, list[EvidenceOut]]
    flags: list[FlagOut]
    rationale: str
    input_fields: list[str]
    created_at: datetime


class AiLockedOut(Out):
    """Chống neo: reviewer chưa chốt điểm chỉ thấy cờ trung tính, chưa thấy điểm/nhóm AI."""

    locked: Literal[True] = True
    needs_attention: bool


class MyReviewOut(Out):
    scores: dict[str, float]
    comment: str
    recommendation: str | None
    submitted: bool
    total_score: float | None


class ReviewRowOut(Out):
    reviewer: str | None
    mine: bool
    scores: dict[str, float]
    total_score: float | None
    comment: str
    recommendation: str | None
    submitted_at: datetime | None


class PendingDecisionOut(Out):
    id: uuid.UUID
    proposed_outcome: str
    proposal_reason: str
    proposed_by_me: bool


class StaffTimelineOut(Out):
    type: str
    from_status: str | None
    to_status: str | None
    at: datetime
    message: str | None


class StaffApplicationOut(ApplicationViewOut):
    rubric: RubricOut | None
    my_review: MyReviewOut | None
    reviews: list[ReviewRowOut]
    disagreement: bool
    ai: AiAssessmentOut | AiLockedOut | None
    pending_decision: PendingDecisionOut | None
    timeline: list[StaffTimelineOut]


class ReviewSavedOut(Out):
    submitted: bool
    total_score: float | None


class AdvanceOut(Out):
    status: str
    current_round: str | None
    version: int


class StatusVersionOut(Out):
    status: str
    version: int


class ProposalOut(Out):
    decision_id: uuid.UUID
    status: str
    version: int


class StatusOut(Out):
    status: str


class ApprovalRowOut(Out):
    decision_id: uuid.UUID
    application_id: uuid.UUID
    candidate_code: str
    name: str | None
    intake: dict[str, Any]
    proposed_outcome: str
    proposal_reason: str
    proposed_by_me: bool
    review_count: int
    avg_score: float | None
    ai_tier: str | None
    ai_score: float | None
    flag_count: int
    version: int


# ---------- Sàng lọc AI ----------


class JobOut(Out):
    id: uuid.UUID
    kind: str
    status: str
    total: int
    done: int
    result: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class TriageStartOut(Out):
    job_id: uuid.UUID
    total: int
    round: str
    engine: str


class TierCountOut(Out):
    count: int
    attention: int


class HistogramBucketOut(Out):
    bucket: int
    tier: str
    count: int


class TriageItemOut(Out):
    application_id: uuid.UUID
    candidate_code: str
    name: str | None
    status: str
    total_score: float
    confidence: float
    tier: str
    needs_attention: bool
    flag_count: int
    engine: str


class TriageBoardOut(Out):
    round: str
    pool: int
    scored: int
    tiers: dict[str, TierCountOut]
    histogram: list[HistogramBucketOut]
    items: list[TriageItemOut]
    thresholds: dict[str, float]
    rounds: list[RoundOut]
    ai_enabled: bool
