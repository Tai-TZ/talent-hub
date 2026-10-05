"""Phản hồi cho cổng ứng viên: đợt tuyển, hồ sơ của tôi, tiến trình, thông báo."""

import uuid
from datetime import date, datetime
from typing import Any

from src.schemas.responses.common import FlagOut, Out, RoundOut


class IntakeOut(Out):
    id: uuid.UUID
    program_id: uuid.UUID
    cohort_id: uuid.UUID | None
    name: str
    description: str
    opens_at: datetime
    closes_at: datetime
    quota: int
    status: str
    rounds: list[RoundOut]
    approval_mode: str
    ai_screening_enabled: bool
    blind_review: bool
    min_reviews: int
    eligibility_rules: list[dict[str, Any]]
    counts: dict[str, int]


class IntakeRef(Out):
    id: uuid.UUID
    name: str
    rounds: list[RoundOut]
    blind_review: bool | None = None
    closes_at: datetime | None = None


class ApplicationSummaryOut(Out):
    id: uuid.UUID
    status: str
    current_round: str | None
    candidate_code: str
    version: int
    intake: IntakeRef
    submitted_at: datetime | None


class EducationOut(Out):
    school: str = ""
    degree: str = ""
    major: str = ""
    status: str = "student"
    year: int | None = None
    gpa: float | None = None


class ExperienceOut(Out):
    org: str = ""
    role: str = ""
    years: float = 0
    description: str = ""


class ProjectOut(Out):
    title: str = ""
    description: str = ""
    link: str | None = None
    tech: list[str] = []


class EssaysOut(Out):
    motivation: str = ""
    problem_solving: str = ""


class LinksOut(Out):
    github: str | None = None
    linkedin: str | None = None
    portfolio: str | None = None


class PreferencesOut(Out):
    tracks: list[str] = []


class ContentOut(Out):
    education: list[EducationOut] = []
    experience: list[ExperienceOut] = []
    projects: list[ProjectOut] = []
    skills: list[str] = []
    essays: EssaysOut = EssaysOut()
    links: LinksOut = LinksOut()
    cv_text: str = ""
    preferences: PreferencesOut = PreferencesOut()


class ProfileOut(Out):
    full_name: str = ""
    phone: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    city: str | None = None


class ApplicationViewOut(Out):
    id: uuid.UUID
    candidate_code: str
    status: str
    current_round: str | None
    version: int
    intake: IntakeRef
    profile: ProfileOut | None
    content: ContentOut
    flags: list[FlagOut]
    submitted_at: datetime | None
    owner: bool


class TimelineEventOut(Out):
    id: uuid.UUID
    type: str
    from_status: str | None
    to_status: str | None
    at: datetime
    message: str | None
    round: str | None


class NotificationOut(Out):
    id: uuid.UUID
    type: str
    title: str
    body: str
    link: str | None
    read: bool
    created_at: datetime


class NotificationListOut(Out):
    unread: int
    items: list[NotificationOut]


class CohortListItem(Out):
    id: uuid.UUID
    code: str
    name: str
    capacity: int
    starts_on: date | None
    status: str


class ProgramOut(Out):
    id: uuid.UUID
    code: str
    name: dict[str, str]
    cohorts: list[CohortListItem]


class ProgramCreatedOut(Out):
    id: uuid.UUID
    code: str
    name: dict[str, str]


class CohortCreatedOut(Out):
    id: uuid.UUID
    code: str
    name: str
