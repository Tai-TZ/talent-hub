"""Chất lượng chương trình theo chuẩn đầu ra: mức đạt từng năng lực, cảnh báo dữ liệu thiếu/bất thường, đề xuất cải tiến.

Tách hai lớp: `load_cohort` đọc DB, `analyse` là hàm thuần (dễ kiểm thử). Mọi cảnh báo và đề xuất là gợi ý cho người phụ
trách; hệ thống không tự đổi dữ liệu hay quyết định của ai.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select

from src.errors import NotFoundError
from src.i18n import Locale
from src.models import (
    Application,
    Cohort,
    CohortClass,
    Competency,
    CompetencyAssessment,
    Enrollment,
    OrgMembership,
    Track,
    TrackTarget,
    User,
)
from src.services.tenancy import OrgDb

# Ngưỡng (đặt ở đây để dễ chỉnh và để giải thích trong giao diện).
LOW_ATTAINMENT = 0.6  # năng lực có dưới 60% học viên đạt mức mục tiêu
MIN_SAMPLE = 20  # cỡ mẫu tối thiểu để kết luận về một năng lực / một mentor
DROP_POINTS = 0.15  # tụt từ 15 điểm % so với khoá trước
ASSESSOR_BIAS = 0.75  # mentor chấm lệch từ 0,75 mức so với mặt bằng (trên cùng năng lực)
LEVEL_JUMP = 3  # hai lần đánh giá liên tiếp chênh từ 3 mức
STALE_DAYS = 60  # học viên đang học mà 60 ngày chưa có đánh giá mới
MAX_ITEMS = 20  # số mục ví dụ kèm mỗi cảnh báo


@dataclass
class Assessment:
    competency_id: uuid.UUID
    level: int
    assessor_id: uuid.UUID
    assessed_at: datetime


@dataclass
class Learner:
    id: uuid.UUID
    name: str
    code: str
    status: str
    track_id: uuid.UUID | None
    class_id: uuid.UUID | None
    assessments: list[Assessment] = field(default_factory=list)  # theo thời gian tăng dần


@dataclass
class CohortData:
    cohort: dict[str, Any]
    learners: list[Learner]
    competencies: dict[uuid.UUID, dict[str, Any]]  # id -> {code, name, max_level}
    targets: dict[uuid.UUID, dict[uuid.UUID, int]]  # track_id -> {competency_id: mức mục tiêu}
    tracks: dict[uuid.UUID, str]
    assessors: dict[uuid.UUID, str]
    previous: dict[str, Any] | None = None  # {"code": "K2", "attainment": {mã năng lực: tỉ lệ}}


# ---------------------------------------------------------------------------------------------------------------------
# Văn bản hai thứ tiếng
# ---------------------------------------------------------------------------------------------------------------------

T: dict[Locale, dict[str, Any]] = {
    "vi": {
        "no_track": ("Học viên chưa được xếp nhánh", "Chưa có nhánh nên không có chuẩn đầu ra để đối chiếu."),
        "missing_assessment": (
            "Thiếu đánh giá năng lực",
            "Học viên còn năng lực mục tiêu chưa được đánh giá lần nào; không đủ căn cứ xét đạt.",
        ),
        "stale_assessment": (
            "Đánh giá đã cũ",
            f"Học viên đang học nhưng {STALE_DAYS} ngày chưa có đánh giá mới.",
        ),
        "no_class": ("Học viên chưa được xếp lớp", "Ảnh hưởng tới phân bổ mentor và theo dõi tiến độ."),
        "assessor_bias": (
            "Mentor chấm lệch mặt bằng",
            "Trên cùng năng lực, mức trung bình mentor này cho lệch rõ so với các mentor khác. Nên hiệu chuẩn.",
        ),
        "level_jump": (
            "Mức năng lực thay đổi bất thường",
            f"Hai lần đánh giá liên tiếp chênh từ {LEVEL_JUMP} mức trở lên; có thể là nhập nhầm.",
        ),
        "decision_mismatch": (
            "Quyết định xét đạt không khớp ma trận năng lực",
            "Kết luận đạt/chưa đạt ngược với mức đánh giá mới nhất; cần ghi rõ lý do hoặc rà soát.",
        ),
        "low_attainment": (
            "Năng lực có tỉ lệ đạt thấp",
            f"Dưới {LOW_ATTAINMENT:.0%} học viên đạt mức mục tiêu.",
        ),
        "attainment_drop": (
            "Tỉ lệ đạt giảm so với khoá trước",
            f"Giảm từ {DROP_POINTS:.0%} trở lên so với khoá liền trước.",
        ),
        "bias_item": lambda name, comp, diff: f"{name} · {comp}: {'+' if diff > 0 else ''}{diff:.1f} mức",
        "jump_item": lambda name, comp, a, b: f"{name} · {comp}: {a} → {b}",
        "mismatch_item": lambda name, status: (
            f"{name}: kết luận “{status}” nhưng ma trận năng lực cho kết quả ngược lại"
        ),
        "status": {"qualified": "đạt", "not_qualified": "chưa đạt"},
        "attain_item": lambda comp, rate, n: f"{comp}: {rate:.0%} đạt (n={n})",
        "drop_item": lambda comp, prev, now, code: f"{comp}: {prev:.0%} ({code}) → {now:.0%}",
        "rec": {
            "low": lambda comp, rate, gap, worst: {
                "title": f"Tăng cường năng lực “{comp}”",
                "rationale": f"Chỉ {rate:.0%} học viên đạt mức mục tiêu; người chưa đạt thiếu trung bình {gap:.1f} mức"
                + (f"; yếu nhất ở nhánh {worst}." if worst else "."),
                "actions": [
                    "Rà soát nội dung và thời lượng các học phần gắn với năng lực này.",
                    "Bổ sung bài thực hành/dự án có chấm theo đúng mức mục tiêu.",
                    "Kèm cặp thêm cho học viên đang thiếu từ 2 mức trở lên trước kỳ xét đạt.",
                    "Xem Rubric Lab: cân nhắc tăng trọng số tiêu chí tuyển sinh liên quan.",
                ],
            },
            "drop": lambda comp, prev, now, code: {
                "title": f"Tìm nguyên nhân tụt giảm ở “{comp}”",
                "rationale": f"Tỉ lệ đạt giảm từ {prev:.0%} ({code}) xuống {now:.0%}.",
                "actions": [
                    "So sánh thay đổi về giảng viên, giáo trình, lịch học giữa hai khoá.",
                    "Kiểm tra đầu vào: mức năng lực ban đầu của học viên khoá này có thấp hơn không.",
                ],
            },
            "bias": lambda n: {
                "title": "Hiệu chuẩn cách chấm giữa các mentor",
                "rationale": f"{n} mentor chấm lệch rõ so với mặt bằng trên cùng năng lực.",
                "actions": [
                    "Tổ chức buổi chấm chéo trên cùng bộ minh chứng mẫu.",
                    "Bổ sung mô tả hành vi cho từng mức trong khung năng lực.",
                ],
            },
            "gaps": lambda n: {
                "title": "Hoàn thiện dữ liệu trước khi xét đạt",
                "rationale": f"{n} học viên còn thiếu đánh giá hoặc chưa xếp nhánh; kết luận dựa trên dữ liệu thiếu sẽ không công bằng.",
                "actions": [
                    "Giao mentor hoàn tất đánh giá còn thiếu (danh sách trong phần cảnh báo).",
                    "Xếp nhánh cho học viên chưa có nhánh để có chuẩn đầu ra đối chiếu.",
                ],
            },
            "track": lambda track, rate, overall: {
                "title": f"Xem lại nhánh “{track}”",
                "rationale": f"Tỉ lệ đạt chuẩn {rate:.0%}, thấp hơn mức chung {overall:.0%}.",
                "actions": [
                    "Đối chiếu mức mục tiêu của nhánh với thời lượng đào tạo thực tế.",
                    "Kiểm tra nhu cầu đối tác và dự án thực chiến của nhánh.",
                ],
            },
            "mismatch": lambda n: {
                "title": "Rà soát các quyết định xét đạt không khớp dữ liệu",
                "rationale": f"{n} quyết định ngược với ma trận năng lực mới nhất.",
                "actions": ["Bổ sung lý do hoặc đánh giá lại; ghi nhận trong nhật ký hoạt động."],
            },
            "none": {
                "title": "Chưa thấy vấn đề nổi bật",
                "rationale": "Các năng lực đều đạt ngưỡng và dữ liệu đầy đủ.",
                "actions": ["Tiếp tục theo dõi ở khoá sau; cân nhắc nâng mức mục tiêu nếu tỉ lệ đạt rất cao."],
            },
        },
        "report": {
            "title": lambda code, name: f"Báo cáo chất lượng chương trình — {code} {name}",
            "generated": lambda when: (
                f"Tạo lúc {when} (UTC). Số liệu tự động; người phụ trách xem xét trước khi áp dụng."
            ),
            "summary": "Tóm tắt",
            "learners": "Học viên",
            "qualified": "Đạt",
            "not_qualified": "Chưa đạt",
            "active": "Đang học",
            "coverage": "Độ phủ đánh giá",
            "attainment": "Tỉ lệ đạt mức mục tiêu",
            "outcomes": "Chuẩn đầu ra theo năng lực",
            "competency": "Năng lực",
            "assessed": "Đã đánh giá",
            "met": "Đạt",
            "rate": "Tỉ lệ",
            "gap": "Thiếu TB (mức)",
            "alerts": "Cảnh báo dữ liệu",
            "no_alerts": "Không có cảnh báo.",
            "recommendations": "Đề xuất cải tiến",
            "actions": "Việc nên làm",
        },
    },
    "en": {
        "no_track": ("Learners without a track", "No track means no learning outcomes to check against."),
        "missing_assessment": (
            "Missing competency assessments",
            "Learners still have target competencies that were never assessed; not enough evidence to qualify.",
        ),
        "stale_assessment": ("Stale assessments", f"Active learners with no new assessment for {STALE_DAYS} days."),
        "no_class": ("Learners without a class", "Affects mentor allocation and progress tracking."),
        "assessor_bias": (
            "Mentor grading out of line",
            "On the same competency, this mentor's average level differs clearly from other mentors. Calibrate.",
        ),
        "level_jump": (
            "Unusual level change",
            f"Two consecutive assessments differ by {LEVEL_JUMP} or more levels; possibly a data-entry error.",
        ),
        "decision_mismatch": (
            "Qualification decision contradicts the competency matrix",
            "The qualified/not-qualified decision is the opposite of the latest assessed levels; document or review.",
        ),
        "low_attainment": (
            "Competencies with low attainment",
            f"Fewer than {LOW_ATTAINMENT:.0%} of learners reach the target level.",
        ),
        "attainment_drop": (
            "Attainment down from the previous cohort",
            f"Down {DROP_POINTS:.0%} or more from the previous cohort.",
        ),
        "bias_item": lambda name, comp, diff: f"{name} · {comp}: {'+' if diff > 0 else ''}{diff:.1f} levels",
        "jump_item": lambda name, comp, a, b: f"{name} · {comp}: {a} → {b}",
        "mismatch_item": lambda name, status: f"{name}: decided “{status}” but the competency matrix says otherwise",
        "status": {"qualified": "qualified", "not_qualified": "not qualified"},
        "attain_item": lambda comp, rate, n: f"{comp}: {rate:.0%} reached (n={n})",
        "drop_item": lambda comp, prev, now, code: f"{comp}: {prev:.0%} ({code}) → {now:.0%}",
        "rec": {
            "low": lambda comp, rate, gap, worst: {
                "title": f"Strengthen “{comp}”",
                "rationale": f"Only {rate:.0%} of learners reach the target level; those below are short by {gap:.1f} levels on average"
                + (f"; weakest in the {worst} track." if worst else "."),
                "actions": [
                    "Review content and hours of the modules tied to this competency.",
                    "Add hands-on assignments/projects graded against the target level.",
                    "Give extra coaching to learners 2+ levels short before the qualification review.",
                    "Check Rubric Lab: consider raising the weight of related admission criteria.",
                ],
            },
            "drop": lambda comp, prev, now, code: {
                "title": f"Investigate the drop in “{comp}”",
                "rationale": f"Attainment fell from {prev:.0%} ({code}) to {now:.0%}.",
                "actions": [
                    "Compare changes in instructors, materials and schedule between the two cohorts.",
                    "Check intake: did this cohort start at a lower level?",
                ],
            },
            "bias": lambda n: {
                "title": "Calibrate grading across mentors",
                "rationale": f"{n} mentor(s) grade clearly out of line with peers on the same competency.",
                "actions": [
                    "Run a cross-grading session on the same sample evidence.",
                    "Add behavioural descriptors for each level of the competency framework.",
                ],
            },
            "gaps": lambda n: {
                "title": "Complete the data before qualification",
                "rationale": f"{n} learner(s) lack assessments or a track; decisions on incomplete data are unfair.",
                "actions": [
                    "Ask mentors to complete the missing assessments (listed under alerts).",
                    "Assign a track to learners without one so outcomes can be checked.",
                ],
            },
            "track": lambda track, rate, overall: {
                "title": f"Review the “{track}” track",
                "rationale": f"Qualification rate {rate:.0%}, below the overall {overall:.0%}.",
                "actions": [
                    "Check the track's target levels against the actual training time.",
                    "Review partner demand and real-world projects for the track.",
                ],
            },
            "mismatch": lambda n: {
                "title": "Review qualification decisions that contradict the data",
                "rationale": f"{n} decision(s) contradict the latest competency matrix.",
                "actions": ["Add the reasoning or reassess; it is recorded in the activity log."],
            },
            "none": {
                "title": "No notable issues",
                "rationale": "All competencies meet the threshold and the data is complete.",
                "actions": ["Keep monitoring next cohort; consider raising targets if attainment is very high."],
            },
        },
        "report": {
            "title": lambda code, name: f"Programme quality report — {code} {name}",
            "generated": lambda when: (
                f"Generated {when} (UTC). Automatic figures; the owner should review before acting."
            ),
            "summary": "Summary",
            "learners": "Learners",
            "qualified": "Qualified",
            "not_qualified": "Not qualified",
            "active": "Studying",
            "coverage": "Assessment coverage",
            "attainment": "Target-level attainment",
            "outcomes": "Learning outcomes by competency",
            "competency": "Competency",
            "assessed": "Assessed",
            "met": "Met",
            "rate": "Rate",
            "gap": "Avg. gap (levels)",
            "alerts": "Data alerts",
            "no_alerts": "No alerts.",
            "recommendations": "Improvement recommendations",
            "actions": "Actions",
        },
    },
}

SEVERITY_ORDER = {"danger": 0, "warning": 1, "info": 2}


# ---------------------------------------------------------------------------------------------------------------------
# Phân tích (hàm thuần)
# ---------------------------------------------------------------------------------------------------------------------


def _latest(learner: Learner) -> dict[uuid.UUID, int]:
    out: dict[uuid.UUID, int] = {}
    for a in learner.assessments:
        out[a.competency_id] = a.level
    return out


def analyse(data: CohortData, locale: Locale, *, now: datetime | None = None) -> dict[str, Any]:
    t = T[locale]
    now = now or datetime.now(UTC)
    comps = data.competencies
    learners = [lr for lr in data.learners if lr.status != "withdrawn"]

    # ---- Chuẩn đầu ra theo năng lực ----
    stats: dict[uuid.UUID, dict[str, Any]] = {}
    by_track: dict[tuple[uuid.UUID, uuid.UUID], dict[str, int]] = defaultdict(
        lambda: {"targeted": 0, "assessed": 0, "met": 0}
    )
    pairs_required = pairs_assessed = pairs_met = 0
    matrix_ok: dict[uuid.UUID, bool | None] = {}  # None = chưa đủ dữ liệu
    for lr in learners:
        targets = data.targets.get(lr.track_id, {}) if lr.track_id else {}
        latest = _latest(lr)
        verdict: bool | None = True if targets else None
        for cid, target in targets.items():
            s = stats.setdefault(cid, {"targeted": 0, "assessed": 0, "met": 0, "gaps": []})
            s["targeted"] += 1
            bt = by_track[(cid, lr.track_id)]  # type: ignore[index]
            bt["targeted"] += 1
            pairs_required += 1
            level = latest.get(cid)
            if level is None:
                verdict = None
                continue
            s["assessed"] += 1
            bt["assessed"] += 1
            pairs_assessed += 1
            if level >= target:
                s["met"] += 1
                bt["met"] += 1
                pairs_met += 1
            else:
                s["gaps"].append(target - level)
                if verdict is not None:
                    verdict = False
        matrix_ok[lr.id] = verdict

    competencies_out = []
    for cid, s in sorted(stats.items(), key=lambda kv: comps[kv[0]]["code"]):
        rate = s["met"] / s["assessed"] if s["assessed"] else None
        competencies_out.append(
            {
                "id": cid,
                "code": comps[cid]["code"],
                "name": comps[cid]["name"],
                "targeted": s["targeted"],
                "assessed": s["assessed"],
                "met": s["met"],
                "attainment": None if rate is None else round(rate, 4),
                "coverage": round(s["assessed"] / s["targeted"], 4) if s["targeted"] else None,
                "avg_gap": round(mean(s["gaps"]), 2) if s["gaps"] else None,
                "previous": (data.previous or {}).get("attainment", {}).get(comps[cid]["code"]),
                "by_track": [
                    {
                        "track_id": tid,
                        "track": data.tracks.get(tid, "—"),
                        "targeted": v["targeted"],
                        "assessed": v["assessed"],
                        "met": v["met"],
                        "attainment": round(v["met"] / v["assessed"], 4) if v["assessed"] else None,
                    }
                    for (c, tid), v in sorted(by_track.items(), key=lambda kv: data.tracks.get(kv[0][1], ""))
                    if c == cid
                ],
            }
        )

    # ---- Theo nhánh ----
    tracks_out: list[dict[str, Any]] = []
    for tid, name in sorted(data.tracks.items(), key=lambda kv: kv[1]):
        members = [lr for lr in learners if lr.track_id == tid]
        if not members:
            continue
        decided = [lr for lr in members if lr.status in ("qualified", "not_qualified")]
        q = sum(1 for lr in decided if lr.status == "qualified")
        tracks_out.append(
            {
                "track_id": tid,
                "track": name,
                "learners": len(members),
                "qualified": q,
                "not_qualified": len(decided) - q,
                "active": sum(1 for lr in members if lr.status == "active"),
                "qualified_rate": round(q / len(decided), 4) if decided else None,
            }
        )

    counts = {
        s: sum(1 for lr in data.learners if lr.status == s)
        for s in ("active", "qualified", "not_qualified", "withdrawn")
    }
    decided_n = counts["qualified"] + counts["not_qualified"]
    summary: dict[str, Any] = {
        "learners": len(data.learners),
        **counts,
        "qualified_rate": round(counts["qualified"] / decided_n, 4) if decided_n else None,
        "coverage": round(pairs_assessed / pairs_required, 4) if pairs_required else None,
        "attainment": round(pairs_met / pairs_assessed, 4) if pairs_assessed else None,
    }

    # ---- Cảnh báo ----
    alerts: list[dict[str, Any]] = []

    def alert(code: str, severity: str, items: list[dict[str, Any]], count: int | None = None) -> None:
        if not items:
            return
        title, detail = t[code]
        alerts.append(
            {
                "code": code,
                "severity": severity,
                "title": title,
                "detail": detail,
                "count": count or len(items),
                "items": items[:MAX_ITEMS],
            }
        )

    def learner_item(lr: Learner, label: str | None = None) -> dict[str, Any]:
        return {"label": label or f"{lr.name} ({lr.code})", "ref_type": "enrollment", "ref_id": str(lr.id)}

    no_track = [lr for lr in learners if lr.track_id is None]
    alert("no_track", "warning", [learner_item(lr) for lr in no_track])

    missing = [
        lr
        for lr in learners
        if lr.track_id is not None and matrix_ok.get(lr.id) is None and data.targets.get(lr.track_id)
    ]
    alert("missing_assessment", "warning", [learner_item(lr) for lr in missing])

    stale = [
        lr
        for lr in learners
        if lr.status == "active"
        and lr.assessments
        and now - lr.assessments[-1].assessed_at > timedelta(days=STALE_DAYS)
    ]
    alert("stale_assessment", "info", [learner_item(lr) for lr in stale])

    no_class = [lr for lr in learners if lr.status == "active" and lr.class_id is None]
    alert("no_class", "info", [learner_item(lr) for lr in no_class])

    # Mentor chấm lệch: so (mức − mục tiêu) trung bình của mentor với các mentor khác trên cùng năng lực.
    deltas: dict[tuple[uuid.UUID, uuid.UUID], list[int]] = defaultdict(list)
    for lr in learners:
        targets = data.targets.get(lr.track_id, {}) if lr.track_id else {}
        for a in lr.assessments:
            if a.competency_id in targets:
                deltas[(a.assessor_id, a.competency_id)].append(a.level - targets[a.competency_id])
    bias_items: list[dict[str, Any]] = []
    biased: set[uuid.UUID] = set()
    for (assessor, cid), values in deltas.items():
        others = [v for (other, c), vs in deltas.items() if c == cid and other != assessor for v in vs]
        if len(values) < MIN_SAMPLE or len(others) < MIN_SAMPLE:
            continue
        diff = mean(values) - mean(others)
        if abs(diff) >= ASSESSOR_BIAS:
            biased.add(assessor)
            bias_items.append(
                {
                    "label": t["bias_item"](data.assessors.get(assessor, "—"), comps[cid]["name"], diff),
                    "ref_type": "membership",
                    "ref_id": str(assessor),
                }
            )
    alert("assessor_bias", "warning", bias_items)

    jumps = []
    for lr in learners:
        last: dict[uuid.UUID, int] = {}
        for a in lr.assessments:
            prev = last.get(a.competency_id)
            if prev is not None and abs(a.level - prev) >= LEVEL_JUMP:
                jumps.append(learner_item(lr, t["jump_item"](lr.name, comps[a.competency_id]["name"], prev, a.level)))
            last[a.competency_id] = a.level
    alert("level_jump", "info", jumps)

    mismatch = [
        learner_item(lr, t["mismatch_item"](lr.name, t["status"][lr.status]))
        for lr in learners
        if lr.status in ("qualified", "not_qualified")
        and matrix_ok.get(lr.id) is not None
        and matrix_ok[lr.id] != (lr.status == "qualified")
    ]
    alert("decision_mismatch", "warning", mismatch)

    low = [
        c
        for c in competencies_out
        if c["attainment"] is not None and c["assessed"] >= MIN_SAMPLE and c["attainment"] < LOW_ATTAINMENT
    ]
    alert(
        "low_attainment",
        "danger",
        [
            {
                "label": t["attain_item"](c["name"], c["attainment"], c["assessed"]),
                "ref_type": "competency",
                "ref_id": str(c["id"]),
            }
            for c in low
        ],
    )

    dropped = [
        c
        for c in competencies_out
        if c["attainment"] is not None
        and c["previous"] is not None
        and c["assessed"] >= MIN_SAMPLE
        and c["previous"] - c["attainment"] >= DROP_POINTS
    ]
    prev_code = (data.previous or {}).get("code", "")
    alert(
        "attainment_drop",
        "warning",
        [
            {
                "label": t["drop_item"](c["name"], c["previous"], c["attainment"], prev_code),
                "ref_type": "competency",
                "ref_id": str(c["id"]),
            }
            for c in dropped
        ],
    )
    alerts.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], -a["count"]))

    # ---- Đề xuất cải tiến ----
    rec = t["rec"]
    recommendations: list[dict[str, Any]] = []
    for c in sorted(low, key=lambda c: c["attainment"]):
        worst = min(
            (b for b in c["by_track"] if b["attainment"] is not None), key=lambda b: b["attainment"], default=None
        )
        recommendations.append(
            {
                "priority": "high",
                "area": "outcomes",
                **rec["low"](c["name"], c["attainment"], c["avg_gap"] or 0, worst["track"] if worst else None),
            }
        )
    for c in dropped:
        if c not in low:
            recommendations.append(
                {
                    "priority": "medium",
                    "area": "outcomes",
                    **rec["drop"](c["name"], c["previous"], c["attainment"], prev_code),
                }
            )
    overall = summary["qualified_rate"]
    if overall is not None:
        for tr in tracks_out:
            decided = tr["qualified"] + tr["not_qualified"]
            if (
                tr["qualified_rate"] is not None
                and decided >= MIN_SAMPLE
                and tr["qualified_rate"] <= overall - DROP_POINTS
            ):
                recommendations.append(
                    {"priority": "medium", "area": "tracks", **rec["track"](tr["track"], tr["qualified_rate"], overall)}
                )
    if biased:
        recommendations.append({"priority": "medium", "area": "assessment", **rec["bias"](len(biased))})
    gaps = len({lr.id for lr in no_track} | {lr.id for lr in missing})
    if gaps:
        recommendations.append(
            {"priority": "high" if gaps >= MIN_SAMPLE else "medium", "area": "data", **rec["gaps"](gaps)}
        )
    if mismatch:
        recommendations.append({"priority": "medium", "area": "decisions", **rec["mismatch"](len(mismatch))})
    if not recommendations:
        recommendations.append({"priority": "low", "area": "general", **rec["none"]})

    return {
        "cohort": data.cohort,
        "previous_cohort": prev_code or None,
        "summary": summary,
        "competencies": competencies_out,
        "tracks": tracks_out,
        "alerts": alerts,
        "recommendations": recommendations,
        "thresholds": {
            "low_attainment": LOW_ATTAINMENT,
            "min_sample": MIN_SAMPLE,
            "drop_points": DROP_POINTS,
            "assessor_bias": ASSESSOR_BIAS,
            "level_jump": LEVEL_JUMP,
            "stale_days": STALE_DAYS,
        },
    }


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


def to_markdown(result: dict[str, Any], locale: Locale, *, now: datetime | None = None) -> str:
    """Báo cáo cải tiến dạng Markdown để tải về / gửi cho hội đồng chương trình."""
    r = T[locale]["report"]
    s, c = result["summary"], result["cohort"]
    lines = [
        f"# {r['title'](c['code'], c['name'])}",
        "",
        r["generated"]((now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M")),
        "",
        f"## {r['summary']}",
        "",
        f"- {r['learners']}: {s['learners']} · {r['qualified']}: {s['qualified']} · {r['not_qualified']}: {s['not_qualified']} · {r['active']}: {s['active']}",
        f"- {r['coverage']}: {_pct(s['coverage'])}",
        f"- {r['attainment']}: {_pct(s['attainment'])}",
        "",
        f"## {r['outcomes']}",
        "",
        f"| {r['competency']} | {r['assessed']} | {r['met']} | {r['rate']} | {r['gap']} |",
        "|---|---:|---:|---:|---:|",
    ]
    for comp in result["competencies"]:
        gap = "—" if comp["avg_gap"] is None else f"{comp['avg_gap']:.1f}"
        lines.append(
            f"| {comp['name']} | {comp['assessed']}/{comp['targeted']} | {comp['met']} | {_pct(comp['attainment'])} | {gap} |"
        )
    lines += ["", f"## {r['alerts']}", ""]
    if not result["alerts"]:
        lines.append(r["no_alerts"])
    for a in result["alerts"]:
        lines.append(f"- **{a['title']}** ({a['count']}): {a['detail']}")
        lines += [f"  - {item['label']}" for item in a["items"][:5]]
    lines += ["", f"## {r['recommendations']}", ""]
    for i, rec in enumerate(result["recommendations"], start=1):
        lines += [f"### {i}. {rec['title']} ({rec['priority']})", "", rec["rationale"], "", f"{r['actions']}:"]
        lines += [f"- {action}" for action in rec["actions"]]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------------------------------------------------
# Đọc dữ liệu
# ---------------------------------------------------------------------------------------------------------------------


async def load_cohort(db: OrgDb, cohort_id: uuid.UUID, locale: Locale) -> CohortData:
    cohort = (await db.session.execute(select(Cohort).where(Cohort.id == cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise NotFoundError("Không tìm thấy khoá học")

    rows = (
        await db.session.execute(
            select(Enrollment, User.full_name, Application.candidate_code)
            .join(OrgMembership, OrgMembership.id == Enrollment.membership_id)
            .join(User, User.id == OrgMembership.user_id)
            .join(Application, Application.id == Enrollment.application_id)
            .where(Enrollment.cohort_id == cohort_id)
            .order_by(User.full_name, Enrollment.id)
        )
    ).all()
    learners = {
        e.id: Learner(id=e.id, name=name, code=code, status=e.status, track_id=e.track_id, class_id=e.class_id)
        for e, name, code in rows
    }
    assessor_ids: set[uuid.UUID] = set()
    if learners:
        for a in (
            await db.session.execute(
                select(CompetencyAssessment)
                .where(CompetencyAssessment.enrollment_id.in_(list(learners)))
                .order_by(CompetencyAssessment.assessed_at, CompetencyAssessment.id)
            )
        ).scalars():
            learners[a.enrollment_id].assessments.append(
                Assessment(
                    competency_id=a.competency_id,
                    level=a.level,
                    assessor_id=a.assessor_membership_id,
                    assessed_at=a.assessed_at,
                )
            )
            assessor_ids.add(a.assessor_membership_id)

    competencies = {
        c.id: {"code": c.code, "name": c.name, "max_level": c.max_level}
        for c in (
            await db.session.execute(select(Competency).where(Competency.program_id == cohort.program_id))
        ).scalars()
    }
    tracks = {
        tr.id: (tr.name or {}).get(locale) or (tr.name or {}).get("vi") or tr.key
        for tr in (await db.session.execute(select(Track).where(Track.program_id == cohort.program_id))).scalars()
    }
    targets: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(dict)
    if tracks:
        for track_id, competency_id, level in (
            await db.session.execute(
                select(TrackTarget.track_id, TrackTarget.competency_id, TrackTarget.target_level).where(
                    TrackTarget.track_id.in_(list(tracks))
                )
            )
        ).all():
            targets[track_id][competency_id] = level
    assessors = (
        dict(
            (
                await db.session.execute(
                    select(OrgMembership.id, User.full_name)
                    .join(User, User.id == OrgMembership.user_id)
                    .where(OrgMembership.id.in_(list(assessor_ids)))
                )
            ).all()
        )
        if assessor_ids
        else {}
    )
    class_names = dict(
        (
            await db.session.execute(select(CohortClass.id, CohortClass.name).where(CohortClass.cohort_id == cohort_id))
        ).all()
    )
    data = CohortData(
        cohort={
            "id": cohort.id,
            "code": cohort.code,
            "name": cohort.name,
            "status": cohort.status,
            "classes": len(class_names),
        },
        learners=list(learners.values()),
        competencies=competencies,
        targets=dict(targets),
        tracks=tracks,
        assessors=assessors,
    )
    data.previous = await _previous_attainment(db, cohort, data)
    return data


async def _previous_attainment(db: OrgDb, cohort: Cohort, data: CohortData) -> dict[str, Any] | None:
    """Tỉ lệ đạt từng năng lực của khoá liền trước (cùng chương trình, bắt đầu sớm hơn) để so xu hướng."""
    if cohort.starts_on is None:
        return None
    prev = (
        await db.session.execute(
            select(Cohort)
            .where(Cohort.program_id == cohort.program_id, Cohort.starts_on < cohort.starts_on)
            .order_by(Cohort.starts_on.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prev is None:
        return None
    rows = (
        await db.session.execute(
            select(Enrollment.id, Enrollment.track_id).where(
                Enrollment.cohort_id == prev.id, Enrollment.status != "withdrawn"
            )
        )
    ).all()
    if not rows:
        return None
    latest: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(dict)
    for enrollment_id, competency_id, level in (
        await db.session.execute(
            select(CompetencyAssessment.enrollment_id, CompetencyAssessment.competency_id, CompetencyAssessment.level)
            .where(CompetencyAssessment.enrollment_id.in_([r[0] for r in rows]))
            .order_by(CompetencyAssessment.assessed_at, CompetencyAssessment.id)
        )
    ).all():
        latest[enrollment_id][competency_id] = level
    met: dict[str, list[bool]] = defaultdict(list)
    for enrollment_id, track_id in rows:
        for cid, target in data.targets.get(track_id, {}).items() if track_id else []:
            lvl = latest[enrollment_id].get(cid)
            if lvl is not None:
                met[data.competencies[cid]["code"]].append(lvl >= target)
    return {
        "code": prev.code,
        "attainment": {code: round(sum(v) / len(v), 4) for code, v in met.items() if len(v) >= MIN_SAMPLE},
    }


async def cohort_quality(db: OrgDb, cohort_id: uuid.UUID, locale: Locale) -> dict[str, Any]:
    return analyse(await load_cohort(db, cohort_id, locale), locale)
