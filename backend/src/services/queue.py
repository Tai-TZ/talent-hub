"""Hàng đợi hồ sơ cho nhân sự: lọc, tìm kiếm, phân trang keyset, chịu được hàng nghìn hồ sơ mỗi đợt."""

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, exists, func, or_, select, tuple_
from sqlalchemy.sql.elements import ColumnElement

from src.models import AiAssessment, Application, Intake, Review
from src.services.tenancy import OrgDb


@dataclass(frozen=True)
class QueueQuery:
    intake_id: uuid.UUID
    status: str | None = None
    round_key: str | None = None
    q: str | None = None
    needs_attention: bool | None = None
    mine_pending: bool = False  # chỉ hồ sơ tôi chưa chốt điểm
    limit: int = 50
    cursor: str | None = None


def encode_cursor(submitted_at: datetime, app_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{submitted_at.isoformat()}|{app_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    stamp, _, raw_id = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
    return datetime.fromisoformat(stamp), uuid.UUID(raw_id)


def _latest_ai(column: Any) -> Any:
    return (
        select(column)
        .where(AiAssessment.application_id == Application.id, AiAssessment.round == Application.current_round)
        .order_by(AiAssessment.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )


def build_filters(query: QueueQuery, membership_id: uuid.UUID, *, can_see_pii: bool) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Application.intake_id == query.intake_id, Application.status != "DRAFT"]
    if query.status:
        conditions.append(Application.status == query.status)
    if query.round_key:
        conditions.append(Application.current_round == query.round_key)
    if query.q:
        like = f"%{query.q.strip()}%"
        match = [Application.candidate_code.ilike(like)]
        if can_see_pii:  # chỉ tìm theo tên khi được phép thấy danh tính
            match.append(Application.profile["full_name"].astext.ilike(like))
        conditions.append(or_(*match))
    if query.needs_attention is not None:
        conditions.append(_latest_ai(AiAssessment.needs_attention).is_(query.needs_attention))
    if query.mine_pending:
        conditions.append(Application.status == "IN_ROUND")
        conditions.append(
            ~exists().where(
                Review.application_id == Application.id,
                Review.reviewer_membership_id == membership_id,
                Review.round == Application.current_round,
                Review.submitted_at.is_not(None),
            )
        )
    return conditions


async def list_queue(
    db: OrgDb, query: QueueQuery, *, membership_id: uuid.UUID, can_see_pii: bool, can_see_tier: bool, intake: Intake
) -> tuple[list[dict[str, Any]], str | None, int]:
    conditions = build_filters(query, membership_id, can_see_pii=can_see_pii)

    review_count = (
        select(func.count())
        .where(
            Review.application_id == Application.id,
            Review.round == Application.current_round,
            Review.submitted_at.is_not(None),
        )
        .scalar_subquery()
    )
    my_review = (
        select(case((Review.submitted_at.is_not(None), "submitted"), else_="draft"))
        .where(
            Review.application_id == Application.id,
            Review.reviewer_membership_id == membership_id,
            Review.round == Application.current_round,
        )
        .limit(1)
        .scalar_subquery()
    )

    stmt = (
        select(
            Application,
            review_count.label("review_count"),
            my_review.label("my_review"),
            _latest_ai(AiAssessment.needs_attention).label("ai_attention"),
            _latest_ai(AiAssessment.tier).label("ai_tier"),
            _latest_ai(AiAssessment.total_score).label("ai_score"),
        )
        .where(and_(*conditions))
        .order_by(Application.submitted_at.asc(), Application.id.asc())
        .limit(query.limit + 1)
    )
    if query.cursor:
        last_at, last_id = decode_cursor(query.cursor)
        stmt = stmt.where(tuple_(Application.submitted_at, Application.id) > tuple_(last_at, last_id))
    rows = (await db.session.execute(stmt)).all()
    total = (
        await db.session.execute(select(func.count()).select_from(Application).where(and_(*conditions)))
    ).scalar_one()

    show_identity = can_see_pii or not intake.blind_review
    items: list[dict[str, Any]] = []
    for app, count, mine, attention, tier, score in rows[: query.limit]:
        item: dict[str, Any] = {
            "id": app.id,
            "candidate_code": app.candidate_code,
            "name": app.profile.get("full_name") if show_identity else None,
            "status": app.status,
            "current_round": app.current_round,
            "submitted_at": app.submitted_at,
            "flag_count": len(app.flags or []),
            "review_count": count,
            "my_review": mine,
            # Hướng của AI (tier, điểm) chỉ cho người có quyền triage.read; reviewer chỉ thấy cờ trung tính.
            "ai_attention": attention,
        }
        if can_see_tier:
            item["ai_tier"] = tier
            item["ai_score"] = score
        items.append(item)

    next_cursor = None
    if len(rows) > query.limit:
        last = rows[query.limit - 1][0]
        assert last.submitted_at is not None
        next_cursor = encode_cursor(last.submitted_at, last.id)
    return items, next_cursor, total
