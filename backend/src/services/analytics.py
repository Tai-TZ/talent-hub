"""Phân tích cho ban điều hành: phễu tuyển sinh, giám sát công bằng, Rubric Lab trên dữ liệu thật."""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select, text

from src.analytics import lab
from src.errors import NotFoundError, ValidationFailedError
from src.models import Application, Decision, Enrollment, Intake, Review
from src.services.intakes import active_rubric
from src.services.tenancy import OrgDb

HIGH_CITIES = {"Hà Nội": "Hà Nội", "TP. Hồ Chí Minh": "TP.HCM"}


async def _intake(db: OrgDb, intake_id: uuid.UUID) -> Intake:
    row = (await db.session.execute(select(Intake).where(Intake.id == intake_id))).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Không tìm thấy đợt tuyển")
    return row


async def funnel(db: OrgDb, intake_id: uuid.UUID) -> dict[str, Any]:
    intake = await _intake(db, intake_id)
    by_status = dict(
        (
            await db.session.execute(
                select(Application.status, func.count())
                .where(Application.intake_id == intake_id)
                .group_by(Application.status)
            )
        ).all()
    )
    submitted = sum(c for s, c in by_status.items() if s != "DRAFT")
    reached: dict[str, int] = {}
    for rnd in intake.rounds:
        reached[rnd["key"]] = (
            await db.session.execute(
                text(
                    "SELECT count(DISTINCT e.application_id) FROM application_events e JOIN applications a ON a.id = e.application_id "
                    "WHERE a.intake_id = :i AND e.type IN ('round.started','round.advanced') AND e.payload ->> 'round' = :r"
                ),
                {"i": intake_id, "r": rnd["key"]},
            )
        ).scalar_one()
    decisions = dict(
        (
            await db.session.execute(
                select(Decision.decided_outcome, func.count())
                .join(Application, Application.id == Decision.application_id)
                .where(Application.intake_id == intake_id, Decision.status == "approved")
                .group_by(Decision.decided_outcome)
            )
        ).all()
    )
    median_days = (
        await db.session.execute(
            text(
                "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (d.decided_at - a.submitted_at))/86400) "
                "FROM decisions d JOIN applications a ON a.id = d.application_id WHERE a.intake_id = :i AND d.status = 'approved' AND a.submitted_at IS NOT NULL"
            ),
            {"i": intake_id},
        )
    ).scalar_one()
    stages = [{"key": "submitted", "label": "Đã nộp", "count": submitted}]
    for rnd in intake.rounds:
        stages.append({"key": rnd["key"], "label": rnd["label"], "count": reached[rnd["key"]]})
    accepted = by_status.get("ACCEPTED", 0) + by_status.get("ENROLLED", 0)
    stages.append({"key": "accepted", "label": "Được nhận", "count": accepted})
    stages.append({"key": "enrolled", "label": "Nhập học", "count": by_status.get("ENROLLED", 0)})
    return {
        "intake": {"id": intake.id, "name": intake.name, "quota": intake.quota, "status": intake.status},
        "by_status": by_status,
        "stages": stages,
        "decisions": decisions,
        "median_days_to_decision": None if median_days is None else round(float(median_days), 1),
        "quota_fill": round(accepted / intake.quota, 3) if intake.quota else None,
    }


def _region(city: str | None) -> str:
    return HIGH_CITIES.get(city or "", "Tỉnh/thành khác" if city else "khong_khai")


async def fairness(db: OrgDb, intake_id: uuid.UUID) -> dict[str, Any]:
    """Tỉ lệ đi tiếp theo giới tính (tự khai) và khu vực. Chỉ thống kê gộp nhóm, không dùng vào chấm điểm."""
    intake = await _intake(db, intake_id)
    first, second = (intake.rounds[0]["key"], intake.rounds[1]["key"] if len(intake.rounds) > 1 else None)
    advanced_ids: set[uuid.UUID] = set()
    if second:
        advanced_ids = set(
            (
                await db.session.execute(
                    text(
                        "SELECT DISTINCT e.application_id FROM application_events e JOIN applications a ON a.id = e.application_id "
                        "WHERE a.intake_id = :i AND e.type IN ('round.started','round.advanced') AND e.payload ->> 'round' = :r"
                    ),
                    {"i": intake_id, "r": second},
                )
            )
            .scalars()
            .all()
        )
    rows = (
        await db.session.execute(
            select(Application.id, Application.profile, Application.status).where(
                Application.intake_id == intake_id, Application.status != "DRAFT"
            )
        )
    ).all()
    people = [
        (
            app_id,
            {"gender": (prof or {}).get("gender") or "khong_khai", "region": _region((prof or {}).get("city"))},
            status,
        )
        for app_id, prof, status in rows
    ]
    out: dict[str, Any] = {"intake": {"id": intake.id, "name": intake.name}, "stages": {}, "warnings": []}
    stage_defs: dict[str, Callable[[uuid.UUID, str], bool]] = {"accepted": lambda i, s: s in ("ACCEPTED", "ENROLLED")}
    if second:
        stage_defs[f"reached_{second}"] = lambda i, s: i in advanced_ids or s in ("ACCEPTED", "ENROLLED")
    for stage, test in stage_defs.items():
        selected = {str(i) for i, _, s in people if test(i, s)}
        pool = [lab.Applicant(id=str(i), scores={}, admitted=False, outcome=None, groups=g) for i, g, _ in people]
        rates = lab.selection_rates(pool, selected)
        out["stages"][stage] = rates
        for attr, data in rates.items():
            ratio = data["impact_ratio"]
            if ratio is not None and ratio < 0.8:
                out["warnings"].append(
                    f"Giai đoạn '{stage}': tỉ lệ tác động theo {attr} là {ratio:.2f} (< 0,8) cần xem lại tiêu chí và quy trình."
                )
    out["note"] = (
        "Quy tắc bốn phần năm: tỉ lệ thấp nhất chia tỉ lệ cao nhất. Dưới 0,8 là dấu hiệu cần rà soát, chưa phải kết luận phân biệt đối xử."
    )
    _ = first
    return out


async def _lab_pool(
    db: OrgDb, intake_ids: list[uuid.UUID]
) -> tuple[list[lab.Applicant], list[dict[str, Any]], dict[str, float]]:
    criteria_by_intake: list[list[dict[str, Any]]] = []
    for iid in intake_ids:
        intake = await _intake(db, iid)
        rubric = await active_rubric(db, iid, intake.rounds[0]["key"])
        if rubric is None:
            raise ValidationFailedError("Một đợt tuyển chưa có rubric", {"intake_ids": str(iid)})
        criteria_by_intake.append(rubric.criteria)
    common = [
        c["id"]
        for c in criteria_by_intake[0]
        if all(any(x["id"] == c["id"] for x in cs) for cs in criteria_by_intake[1:])
    ]
    if not common:
        raise ValidationFailedError(
            "Các đợt tuyển không có tiêu chí chung để so sánh", {"intake_ids": "Không có tiêu chí chung"}
        )
    definitions = [c for c in criteria_by_intake[0] if c["id"] in common]
    old_weights = {c["id"]: float(c["weight"]) for c in definitions}
    max_by = {c["id"]: float(c["max"]) for c in definitions}

    pool: list[lab.Applicant] = []
    for iid in intake_ids:
        intake = await _intake(db, iid)
        first_round = intake.rounds[0]["key"]
        rows = (
            await db.session.execute(
                select(Application.id, Application.profile, Application.status, Enrollment.status)
                .outerjoin(Enrollment, Enrollment.application_id == Application.id)
                .where(Application.intake_id == iid, Application.status != "DRAFT")
            )
        ).all()
        scores: dict[uuid.UUID, dict[str, list[float]]] = {}
        for app_id, raw in (
            await db.session.execute(
                select(Review.application_id, Review.scores)
                .join(Application, Application.id == Review.application_id)
                .where(Application.intake_id == iid, Review.round == first_round, Review.submitted_at.is_not(None))
            )
        ).all():
            bucket = scores.setdefault(app_id, {})
            for cid in common:
                if cid in raw:
                    bucket.setdefault(cid, []).append(float(raw[cid]) / max_by[cid])
        for app_id, profile, status, enrollment_status in rows:
            if app_id not in scores:
                continue  # chưa có điểm vòng đầu thì không đưa vào phân tích
            admitted = status in ("ACCEPTED", "ENROLLED")
            outcome = 1 if enrollment_status == "qualified" else 0 if enrollment_status == "not_qualified" else None
            pool.append(
                lab.Applicant(
                    id=str(app_id),
                    scores={cid: sum(v) / len(v) for cid, v in scores[app_id].items()},
                    admitted=admitted,
                    outcome=outcome,
                    groups={
                        "gender": (profile or {}).get("gender") or "khong_khai",
                        "region": _region((profile or {}).get("city")),
                    },
                )
            )
    return pool, definitions, old_weights


async def lab_report(db: OrgDb, intake_ids: list[uuid.UUID], new_weights: dict[str, float] | None) -> dict[str, Any]:
    pool, definitions, old_weights = await _lab_pool(db, intake_ids)
    criteria = [c["id"] for c in definitions]
    analysis = lab.analyse(pool, criteria)
    admitted = sum(1 for p in pool if p.admitted)
    result: dict[str, Any] = {
        "criteria": [{"id": c["id"], "name": c["name"], "weight": float(c["weight"])} for c in definitions],
        "analysis": analysis,
        "pool": len(pool),
        "admitted": admitted,
        "old_weights": old_weights,
    }
    if new_weights is not None:
        cleaned = {k: float(v) for k, v in new_weights.items() if k in criteria}
        if not cleaned or sum(max(w, 0) for w in cleaned.values()) <= 0:
            raise ValidationFailedError("Trọng số mới phải có ít nhất một giá trị dương", {"weights": "Không hợp lệ"})
        probs = (
            lab.predict_probabilities(pool, pool, criteria)
            if analysis.get("reliable") or analysis.get("n", 0) >= 10
            else {}
        )
        result["simulation"] = lab.simulate(
            pool, old_weights, {c: max(cleaned.get(c, 0.0), 0.0) for c in criteria}, admitted, probs
        )
        result["new_weights"] = cleaned
    return result
