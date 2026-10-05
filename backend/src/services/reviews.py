"""Chấm điểm theo rubric, chuyển vòng và yêu cầu bổ sung. Người chấm là con người; AI chỉ gợi ý."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from src.errors import ConflictError, InvalidTransitionError, PermissionDeniedError, ValidationFailedError
from src.models import AiAssessment, Application, Review
from src.services.audit import RequestMeta, write_audit
from src.services.intakes import active_rubric, get_intake
from src.services.notifications import notify
from src.services.tenancy import OrgDb
from src.services.workflow import Actor, apply_transition

RECOMMENDATIONS = ("advance", "reject", "waitlist")


def compute_total(criteria: list[dict[str, Any]], scores: dict[str, float]) -> float:
    """Điểm tổng 0–100 theo trọng số; tiêu chí chưa chấm tính 0."""
    weight_sum = sum(c["weight"] for c in criteria)
    if weight_sum <= 0:
        return 0.0
    achieved = sum((min(max(scores.get(c["id"], 0.0), 0.0), c["max"]) / c["max"]) * c["weight"] for c in criteria)
    return float(round(achieved / weight_sum * 100, 2))


async def get_review(
    db: OrgDb, application_id: uuid.UUID, reviewer_membership_id: uuid.UUID, round_key: str
) -> Review | None:
    return (
        await db.session.execute(
            select(Review).where(
                Review.application_id == application_id,
                Review.reviewer_membership_id == reviewer_membership_id,
                Review.round == round_key,
            )
        )
    ).scalar_one_or_none()


async def save_review(
    db: OrgDb,
    app: Application,
    *,
    actor: Actor,
    round_key: str,
    scores: dict[str, float],
    comment: str,
    recommendation: str | None,
    submit: bool,
    meta: RequestMeta,
) -> Review:
    assert actor.membership_id is not None
    if app.status != "IN_ROUND" or app.current_round != round_key:
        raise ConflictError("Hồ sơ không ở vòng này để chấm")
    if app.applicant_membership_id == actor.membership_id:
        raise PermissionDeniedError("Không được chấm hồ sơ của chính mình (xung đột lợi ích)")

    rubric = await active_rubric(db, app.intake_id, round_key)
    if rubric is None:
        raise ValidationFailedError("Vòng này chưa có rubric")
    by_id = {c["id"]: c for c in rubric.criteria}

    errors: dict[str, str] = {}
    for cid, value in scores.items():
        crit = by_id.get(cid)
        if crit is None:
            errors[f"scores.{cid}"] = "Tiêu chí không tồn tại"
        elif not 0 <= value <= crit["max"]:
            errors[f"scores.{cid}"] = f"Điểm phải từ 0 đến {crit['max']:g}"
    if errors:
        raise ValidationFailedError("Điểm không hợp lệ", errors)

    if submit:
        missing = [c["name"] for c in rubric.criteria if c["id"] not in scores]
        if missing:
            raise ValidationFailedError("Cần chấm đủ mọi tiêu chí", {"scores": ", ".join(missing)})
        if recommendation not in RECOMMENDATIONS:
            raise ValidationFailedError("Chọn khuyến nghị của bạn", {"recommendation": "Bắt buộc"})
        extremes = [c["name"] for c in rubric.criteria if scores[c["id"]] in (0, c["max"])]
        if extremes and len(comment.strip()) < 20:
            raise ValidationFailedError(
                "Điểm tuyệt đối (0 hoặc tối đa) cần nhận xét giải thích",
                {"comment": "Cần ít nhất 20 ký tự: " + ", ".join(extremes)},
            )

    review = await get_review(db, app.id, actor.membership_id, round_key)
    if review is not None and review.submitted_at is not None:
        raise ConflictError("Bạn đã chốt điểm hồ sơ này, không thể sửa")
    if review is None:
        review = Review(
            organization_id=db.org.id,
            application_id=app.id,
            reviewer_membership_id=actor.membership_id,
            round=round_key,
            rubric_id=rubric.id,
        )
        db.session.add(review)
    review.scores = scores
    review.comment = comment.strip()
    review.recommendation = recommendation
    review.total_score = compute_total(rubric.criteria, scores)
    if submit:
        review.submitted_at = datetime.now(UTC)
    await db.session.flush()
    if submit:
        write_audit(
            db,
            action="review.submitted",
            entity_type="application",
            entity_id=app.id,
            actor_user_id=actor.user_id,
            after={"round": round_key, "total": review.total_score, "recommendation": recommendation},
            meta=meta,
        )
    return review


async def submitted_reviews(db: OrgDb, app: Application, round_key: str | None = None) -> list[Review]:
    return list(
        (
            await db.session.execute(
                select(Review)
                .where(
                    Review.application_id == app.id,
                    Review.round == (round_key or app.current_round),
                    Review.submitted_at.is_not(None),
                )
                .order_by(Review.submitted_at)
            )
        )
        .scalars()
        .all()
    )


def disagreement(reviews: list[Review]) -> bool:
    """Reviewer bất đồng: có người khuyến nghị advance và có người khuyến nghị reject."""
    recs = {r.recommendation for r in reviews}
    return "advance" in recs and "reject" in recs


async def my_review_submitted(db: OrgDb, app: Application, membership_id: uuid.UUID) -> bool:
    if app.current_round is None:
        return False
    review = await get_review(db, app.id, membership_id, app.current_round)
    return review is not None and review.submitted_at is not None


async def latest_ai(db: OrgDb, app: Application, round_key: str | None = None) -> AiAssessment | None:
    return (
        await db.session.execute(
            select(AiAssessment)
            .where(AiAssessment.application_id == app.id, AiAssessment.round == (round_key or app.current_round))
            .order_by(AiAssessment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def advance_round(
    db: OrgDb, app: Application, *, actor: Actor, expected_version: int | None, meta: RequestMeta
) -> Application:
    intake = await get_intake(db, app.intake_id)
    keys = [r["key"] for r in intake.rounds]
    if app.status != "IN_ROUND" or app.current_round not in keys:
        raise ConflictError("Hồ sơ không ở trong vòng xét")
    index = keys.index(app.current_round)
    if index + 1 >= len(keys):
        raise InvalidTransitionError("Đây là vòng cuối: hãy đề xuất quyết định thay vì chuyển vòng")

    reviews = await submitted_reviews(db, app)
    if len(reviews) < intake.min_reviews:
        raise ConflictError(f"Cần tối thiểu {intake.min_reviews} reviewer chốt điểm trước khi chuyển vòng")
    if disagreement(reviews):
        raise ConflictError("Các reviewer đang bất đồng: cần thêm một reviewer chấm hoặc đề xuất quyết định")
    if any(r.recommendation != "advance" for r in reviews):
        raise ConflictError("Chưa đủ khuyến nghị 'advance' từ reviewer")

    target = keys[index + 1]
    await apply_transition(
        db,
        app,
        "IN_ROUND",
        actor=actor,
        expected_version=expected_version,
        next_round=target,
        event_type="round.advanced",
        payload={"from_round": app.current_round},
    )
    notify(
        db,
        app.applicant_membership_id,
        type="round.advanced",
        title="Hồ sơ của bạn sang vòng tiếp theo",
        body=f"Bạn đã vào vòng: {next(r['label'] for r in intake.rounds if r['key'] == target)}.",
        link=f"/apply/{app.id}",
    )
    write_audit(
        db,
        action="round.advanced",
        entity_type="application",
        entity_id=app.id,
        actor_user_id=actor.user_id,
        after={"to": target},
        meta=meta,
    )
    return app


async def request_info(
    db: OrgDb, app: Application, *, actor: Actor, message: str, expected_version: int | None, meta: RequestMeta
) -> Application:
    if len(message.strip()) < 10:
        raise ValidationFailedError("Hãy mô tả rõ thông tin cần bổ sung", {"message": "Tối thiểu 10 ký tự"})
    await apply_transition(
        db,
        app,
        "NEEDS_INFO",
        actor=actor,
        expected_version=expected_version,
        event_type="info.requested",
        payload={"message": message.strip(), "from_round": app.current_round},
    )
    notify(
        db,
        app.applicant_membership_id,
        type="info.requested",
        title="Cần bổ sung thông tin cho hồ sơ",
        body=message.strip(),
        link=f"/apply/{app.id}",
    )
    write_audit(
        db, action="info.requested", entity_type="application", entity_id=app.id, actor_user_id=actor.user_id, meta=meta
    )
    return app


async def review_stats(db: OrgDb, app: Application) -> dict[str, Any]:
    row = (
        await db.session.execute(
            select(func.count(), func.avg(Review.total_score))
            .select_from(Review)
            .where(Review.application_id == app.id, Review.round == app.current_round, Review.submitted_at.is_not(None))
        )
    ).one()
    return {"count": row[0], "avg": float(row[1]) if row[1] is not None else None}
