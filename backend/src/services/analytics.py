"""Phân tích cho ban điều hành: phễu tuyển sinh, giám sát công bằng, Rubric Lab trên dữ liệu thật."""

import copy
import json
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, func, select, text

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


@dataclass(frozen=True)
class _LabSetup:
    definitions: list[dict[str, Any]]  # tiêu chí chung, lấy định nghĩa của đợt đầu tiên
    first_rounds: dict[uuid.UUID, str]
    rubrics_json: str  # toàn bộ tiêu chí của các đợt, dùng làm một phần khoá bộ nhớ đệm

    @property
    def criteria(self) -> list[str]:
        return [c["id"] for c in self.definitions]


@dataclass
class _LabData:
    pool: list[lab.Applicant]
    analysis: dict[str, Any]
    probs: dict[str, float] | None = None  # xác suất đạt ước lượng, chỉ tính khi cần mô phỏng


# Bộ nhớ đệm trong tiến trình cho phần nặng của Rubric Lab (nạp dữ liệu + phân tích bootstrap). Màn Lab gọi lại mỗi lần
# người dùng chỉnh trọng số; các phần này không phụ thuộc trọng số và dữ liệu đợt cũ hiếm khi đổi. Khoá gồm tổ chức,
# danh sách đợt, rubric và dấu vân tay dữ liệu, nên dữ liệu đổi là tự tính lại.
_LAB_CACHE: OrderedDict[tuple[Any, ...], _LabData] = OrderedDict()
LAB_CACHE_SIZE = 8


async def _lab_setup(db: OrgDb, intake_ids: list[uuid.UUID]) -> _LabSetup:
    criteria_by_intake: list[list[dict[str, Any]]] = []
    first_rounds: dict[uuid.UUID, str] = {}
    for iid in intake_ids:
        intake = await _intake(db, iid)
        first_rounds[iid] = intake.rounds[0]["key"]
        rubric = await active_rubric(db, iid, first_rounds[iid])
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
    return _LabSetup(
        definitions=[c for c in criteria_by_intake[0] if c["id"] in common],
        first_rounds=first_rounds,
        rubrics_json=json.dumps(criteria_by_intake, sort_keys=True, default=str),
    )


async def _lab_fingerprint(db: OrgDb, intake_ids: list[uuid.UUID]) -> tuple[Any, ...]:
    """Dấu vân tay dữ liệu đầu vào của Lab: đổi khi thêm hay sửa hồ sơ, bài chấm hoặc ghi danh của các đợt.

    Dùng số dòng và *tổng* `updated_at` (numeric, chính xác tới micro giây) thay vì `max`: một giao dịch bắt đầu sớm
    nhưng commit muộn ghi `updated_at` nhỏ hơn max đã thấy, `max` sẽ bỏ sót còn tổng thì không. Ba bảng này không có
    thao tác xoá; mọi cập nhật đều đặt lại `updated_at` (ORM `onupdate` hoặc gán trực tiếp trong SQL).
    """
    in_intakes = Application.intake_id.in_(intake_ids)
    out: list[Any] = []
    for stmt in (
        select(func.count(), func.sum(func.extract("epoch", Application.updated_at))).where(in_intakes),
        select(func.count(), func.sum(func.extract("epoch", Review.updated_at)))
        .join(Application, Application.id == Review.application_id)
        .where(in_intakes),
        select(func.count(), func.sum(func.extract("epoch", Enrollment.updated_at)))
        .join(Application, Application.id == Enrollment.application_id)
        .where(in_intakes),
    ):
        out.extend((await db.session.execute(stmt)).one())
    return tuple(out)


async def _lab_pool(db: OrgDb, intake_ids: list[uuid.UUID], setup: _LabSetup) -> list[lab.Applicant]:
    common = setup.criteria
    max_by = {c["id"]: float(c["max"]) for c in setup.definitions}
    pool: list[lab.Applicant] = []
    for iid in intake_ids:
        # Chỉ lấy đúng các trường cần (giới tính, tỉnh/thành, điểm các tiêu chí chung) thay vì giải mã cả JSONB
        # hồ sơ và bảng điểm: với hàng chục nghìn hồ sơ, phần giải mã chiếm phần lớn thời gian.
        rows = (
            await db.session.execute(
                select(
                    Application.id,
                    Application.profile["gender"].astext,
                    Application.profile["city"].astext,
                    Application.status,
                    Enrollment.status,
                )
                .outerjoin(Enrollment, Enrollment.application_id == Application.id)
                .where(Application.intake_id == iid, Application.status != "DRAFT")
                # Thứ tự cố định: mẫu bootstrap phụ thuộc thứ tự dòng, thiếu ORDER BY thì khoảng tin cậy đổi giữa các lần xem.
                .order_by(Application.id)
            )
        ).all()
        # Điểm trung bình (chuẩn hoá 0..1) của các bài chấm vòng đầu theo từng tiêu chí, tính ngay trong DB.
        scores: dict[uuid.UUID, dict[str, float]] = {
            app_id: {cid: value for cid, value in zip(common, averages, strict=True) if value is not None}
            for app_id, *averages in (
                await db.session.execute(
                    select(
                        Review.application_id,
                        *(func.avg(Review.scores[cid].astext.cast(Float) / max_by[cid]) for cid in common),
                    )
                    .join(Application, Application.id == Review.application_id)
                    .where(
                        Application.intake_id == iid,
                        Review.round == setup.first_rounds[iid],
                        Review.submitted_at.is_not(None),
                    )
                    .group_by(Review.application_id)
                )
            ).all()
        }
        for app_id, gender, city, status, enrollment_status in rows:
            if app_id not in scores:
                continue  # chưa có điểm vòng đầu thì không đưa vào phân tích
            admitted = status in ("ACCEPTED", "ENROLLED")
            outcome = 1 if enrollment_status == "qualified" else 0 if enrollment_status == "not_qualified" else None
            pool.append(
                lab.Applicant(
                    id=str(app_id),
                    scores=scores[app_id],
                    admitted=admitted,
                    outcome=outcome,
                    groups={"gender": gender or "khong_khai", "region": _region(city)},
                )
            )
    return pool


async def _lab_data(db: OrgDb, intake_ids: list[uuid.UUID], setup: _LabSetup) -> _LabData:
    key = (db.org.id, tuple(intake_ids), setup.rubrics_json, await _lab_fingerprint(db, intake_ids))
    data = _LAB_CACHE.get(key)
    if data is not None:
        _LAB_CACHE.move_to_end(key)
        return data
    pool = await _lab_pool(db, intake_ids, setup)
    data = _LabData(pool=pool, analysis=lab.analyse(pool, setup.criteria))
    _LAB_CACHE[key] = data
    while len(_LAB_CACHE) > LAB_CACHE_SIZE:
        _LAB_CACHE.popitem(last=False)
    return data


async def lab_intakes(db: OrgDb) -> list[dict[str, Any]]:
    """Các đợt dùng được cho Rubric Lab (đã đóng, có người được nhận), kèm bộ tiêu chí vòng đầu và số học viên có kết
    quả, để giao diện gom các đợt cùng bộ tiêu chí và không chọn mặc định những đợt không so sánh được với nhau."""
    intakes = (
        (
            await db.session.execute(
                select(Intake).where(Intake.status.in_(("closed", "archived"))).order_by(Intake.opens_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if not intakes:
        return []
    ids = [i.id for i in intakes]
    admitted = dict(
        (
            await db.session.execute(
                select(Application.intake_id, func.count())
                .where(Application.intake_id.in_(ids), Application.status.in_(("ACCEPTED", "ENROLLED")))
                .group_by(Application.intake_id)
            )
        ).all()
    )
    outcomes = dict(
        (
            await db.session.execute(
                select(Application.intake_id, func.count())
                .join(Enrollment, Enrollment.application_id == Application.id)
                .where(Application.intake_id.in_(ids), Enrollment.status.in_(("qualified", "not_qualified")))
                .group_by(Application.intake_id)
            )
        ).all()
    )
    out: list[dict[str, Any]] = []
    for intake in intakes:
        if not admitted.get(intake.id):
            continue
        rubric = await active_rubric(db, intake.id, intake.rounds[0]["key"]) if intake.rounds else None
        out.append(
            {
                "id": intake.id,
                "name": intake.name,
                "status": intake.status,
                "admitted": admitted.get(intake.id, 0),
                "with_outcome": outcomes.get(intake.id, 0),
                "criteria": [
                    {"id": c["id"], "name": c.get("name", c["id"])} for c in (rubric.criteria if rubric else [])
                ],
            }
        )
    return out


async def lab_report(db: OrgDb, intake_ids: list[uuid.UUID], new_weights: dict[str, float] | None) -> dict[str, Any]:
    setup = await _lab_setup(db, intake_ids)
    data = await _lab_data(db, intake_ids, setup)
    pool, criteria, definitions = data.pool, setup.criteria, setup.definitions
    old_weights = {c["id"]: float(c["weight"]) for c in definitions}
    analysis = copy.deepcopy(data.analysis)  # bản riêng cho mỗi phản hồi, không để lộ đối tượng trong bộ nhớ đệm
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
        if data.probs is None:
            data.probs = (
                lab.predict_probabilities(pool, pool, criteria)
                if analysis.get("reliable") or analysis.get("n", 0) >= 10
                else {}
            )
        result["simulation"] = lab.simulate(
            pool, old_weights, {c: max(cleaned.get(c, 0.0), 0.0) for c in criteria}, admitted, data.probs
        )
        result["new_weights"] = cleaned
    return result
