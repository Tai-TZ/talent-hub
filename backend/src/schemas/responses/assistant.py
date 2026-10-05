"""Phản hồi cho trợ lý hỏi đáp."""

import uuid
from datetime import datetime

from src.schemas.responses.common import Out


class CitationOut(Out):
    n: int
    title: str
    heading: str
    snippet: str


class AskOut(Out):
    id: uuid.UUID
    answer: str
    answered: bool
    citations: list[CitationOut]
    engine: str


class UnansweredOut(Out):
    question: str
    count: int
    last_at: datetime


class AssistantInsightsOut(Out):
    days: int
    total: int
    answered: int
    answer_rate: float | None
    helpful_rate: float | None
    unanswered: list[UnansweredOut]
