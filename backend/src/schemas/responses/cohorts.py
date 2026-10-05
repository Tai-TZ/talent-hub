"""Phản hồi cho vận hành khoá học và bộ giải Composer."""

import uuid
from datetime import date, datetime
from typing import Any

from src.schemas.responses.common import Out

# ---------- Tổng quan khoá, học viên ----------


class CohortRef(Out):
    id: uuid.UUID
    code: str
    name: str
    capacity: int
    starts_on: date | None
    status: str


class ClassStat(Out):
    id: uuid.UUID
    name: str
    level: int
    capacity: int
    assigned: int


class TrackStat(Out):
    id: uuid.UUID
    key: str
    name: dict[str, str]
    capacity: int | None
    assigned: int


class CohortOverviewOut(Out):
    cohort: CohortRef
    enrollments: dict[str, int]
    accepted_waiting_enrollment: int
    classes: list[ClassStat]
    tracks: list[TrackStat]
    unplaced: int


class EnrollmentOut(Out):
    id: uuid.UUID
    name: str
    email: str
    candidate_code: str
    status: str
    class_id: uuid.UUID | None
    track_id: uuid.UUID | None
    enrolled_at: datetime


class EnrollmentPageOut(Out):
    items: list[EnrollmentOut]
    total: int


class EnrolledOut(Out):
    enrolled: int


class AssignedOut(Out):
    id: uuid.UUID
    class_id: uuid.UUID | None
    track_id: uuid.UUID | None


# ---------- Nhánh, lớp, đối tác ----------


class TrackTargetOut(Out):
    competency_id: uuid.UUID
    code: str
    name: str
    target: int


class TrackOut(Out):
    id: uuid.UUID
    key: str
    name: dict[str, str]
    keywords: list[str]
    targets: list[TrackTargetOut]


class PartnerOut(Out):
    id: uuid.UUID
    name: str
    skills: list[str]
    status: str


class IdOut(Out):
    id: uuid.UUID


class IdNameOut(Out):
    id: uuid.UUID
    name: str


class IdKeyOut(Out):
    id: uuid.UUID
    key: str


class SavedOut(Out):
    status: str


# ---------- Năng lực, mentor, xét đạt ----------


class MatrixRowOut(Out):
    competency_id: uuid.UUID
    code: str
    name: str
    target: int
    max_level: int
    level: int | None
    evidence: str
    met: bool | None


class CompetenciesOut(Out):
    enrollment_id: uuid.UUID
    name: str
    track_id: uuid.UUID | None
    track_name: str | None
    matrix: list[MatrixRowOut]
    suggestion: str
    status: str


class MentorLearnerOut(Out):
    enrollment_id: uuid.UUID
    name: str
    track_id: uuid.UUID | None
    track_name: str | None
    project: str
    partner_id: uuid.UUID
    partner_name: str


class QualificationRowOut(Out):
    enrollment_id: uuid.UUID
    name: str
    candidate_code: str
    track_name: str | None
    status: str
    suggestion: str
    met: int
    total: int


class EnrollmentStatusOut(Out):
    id: uuid.UUID
    status: str


# ---------- Phụ cấp ----------


class StipendSummaryOut(Out):
    period: str
    status: str
    count: int
    total_vnd: float


class CreatedOut(Out):
    created: int


class PaidOut(Out):
    count: int
    total_vnd: float


# ---------- Cohort Composer ----------


class ComposerClassMetric(Out):
    index: int
    size: int
    mean_score: float
    std_score: float
    min_score: float
    max_score: float
    background: dict[str, int]


class TrackFillOut(Out):
    assigned: int
    capacity: int


class ComposerMetricsOut(Out):
    learners: int
    classes: list[ComposerClassMetric]
    class_mean_spread: float
    pref_first_rate: float | None
    pref_top2_rate: float | None
    avg_fit: float | None
    track_fill: dict[str, TrackFillOut]
    placed: int
    placement_rate: float | None


class ComposerRunOut(Out):
    id: uuid.UUID
    cohort_id: uuid.UUID
    params: dict[str, Any]
    metrics: ComposerMetricsOut
    created_at: datetime
    applied_at: datetime | None


class ComposerAssignmentOut(Out):
    learner_id: str
    class_index: int
    track: str | None
    partner_id: str | None
    explanation: str
    name: str | None = None


class ComposerRunDetailOut(ComposerRunOut):
    assignments: list[ComposerAssignmentOut]


class ComposerAppliedOut(Out):
    applied: int
    skipped: int
