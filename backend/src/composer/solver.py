"""Bộ giải xếp lớp, chia nhánh và ghép vị trí thực chiến. Hàm thuần: không đụng database, dễ kiểm thử.

Chia nhánh và ghép đối tác là bài toán gán có ràng buộc sức chứa, giải tối ưu bằng thuật toán Hungarian
(`scipy.optimize.linear_sum_assignment`) trên ma trận độ hài lòng. Xếp lớp có hai chế độ:
`levels` (lớp theo trình độ, đồng nhất) và `balanced` (lớp cân bằng, đa dạng).
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

PREF_SCORES = (1.0, 0.6, 0.3)  # nguyện vọng 1, 2, 3


class ComposerError(ValueError):
    """Tham số hoặc dữ liệu đầu vào không giải được (ví dụ sức chứa không đủ)."""


@dataclass(frozen=True)
class Learner:
    id: str
    score: float  # 0-100
    prefs: tuple[str, ...] = ()  # khoá nhánh theo thứ tự nguyện vọng
    fit: dict[str, float] = field(default_factory=dict)  # nhánh -> độ phù hợp 0..1
    skills: frozenset[str] = frozenset()
    background: str = "unknown"  # nhóm nền tảng (ví dụ tech/non_tech) để cân bằng, không phải thuộc tính được bảo vệ


@dataclass(frozen=True)
class PartnerSlot:
    partner_id: str
    track: str
    slots: int
    skills: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Params:
    track_capacity: dict[str, int]
    class_count: int = 3
    class_mode: str = "levels"  # levels | balanced
    pref_weight: float = 0.6
    fit_weight: float = 0.4
    placement_skill_weight: float = 0.7  # phần còn lại là điểm xét tuyển

    def validate(self, n_learners: int) -> None:
        if self.class_mode not in ("levels", "balanced"):
            raise ComposerError("Chế độ xếp lớp không hợp lệ")
        if not 1 <= self.class_count <= 30:
            raise ComposerError("Số lớp phải từ 1 đến 30")
        if not 0 <= self.pref_weight <= 1 or not 0 <= self.fit_weight <= 1 or self.pref_weight + self.fit_weight == 0:
            raise ComposerError("Trọng số nguyện vọng và độ phù hợp phải trong khoảng 0 đến 1 và không cùng bằng 0")
        if self.track_capacity and sum(self.track_capacity.values()) < n_learners:
            raise ComposerError(
                f"Tổng sức chứa các nhánh ({sum(self.track_capacity.values())}) nhỏ hơn số học viên ({n_learners})"
            )


def _pref_score(learner: Learner, track: str) -> float:
    try:
        return PREF_SCORES[learner.prefs.index(track)]
    except (ValueError, IndexError):
        return 0.0


def assign_tracks(learners: list[Learner], params: Params) -> dict[str, str]:
    """Chia nhánh tối đa hoá tổng độ hài lòng (nguyện vọng + độ phù hợp) trong giới hạn sức chứa."""
    if not params.track_capacity or not learners:
        return {}
    tracks = sorted(params.track_capacity)
    slot_track = [t for t in tracks for _ in range(params.track_capacity[t])]
    total_w = params.pref_weight + params.fit_weight
    utility = np.array(
        [
            [
                (params.pref_weight * _pref_score(lr, t) + params.fit_weight * lr.fit.get(t, 0.0)) / total_w
                for t in slot_track
            ]
            for lr in learners
        ]
    )
    rows, cols = linear_sum_assignment(-utility)
    return {learners[r].id: slot_track[c] for r, c in zip(rows, cols, strict=True)}


def assign_classes(learners: list[Learner], params: Params) -> dict[str, int]:
    """Trả về {learner_id: chỉ số lớp 0..K-1}. Với `levels`, lớp 0 là nhóm điểm cao nhất."""
    k = min(params.class_count, max(1, len(learners)))
    ordered = sorted(learners, key=lambda lr: (-lr.score, lr.id))
    if params.class_mode == "levels":
        size, extra = divmod(len(ordered), k)
        result: dict[str, int] = {}
        start = 0
        for idx in range(k):
            end = start + size + (1 if idx < extra else 0)
            for learner in ordered[start:end]:
                result[learner.id] = idx
            start = end
        return result

    # balanced: duyệt từ điểm cao xuống thấp, mỗi người vào lớp (còn chỗ) đang có ít người cùng nhóm nền tảng nhất,
    # hoà thì chọn lớp có tổng điểm thấp nhất, nên điểm trung bình và tỉ lệ nhóm đều giữa các lớp.
    capacity = -(-len(ordered) // k)
    sizes = [0] * k
    sums = [0.0] * k
    backgrounds: list[Counter[str]] = [Counter() for _ in range(k)]
    result = {}
    for learner in ordered:
        open_classes = [i for i in range(k) if sizes[i] < capacity]
        target = min(open_classes, key=lambda c: (backgrounds[c][learner.background], sums[c], c))
        result[learner.id] = target
        sizes[target] += 1
        sums[target] += learner.score
        backgrounds[target][learner.background] += 1
    return result


def assign_placements(
    learners: list[Learner], tracks: dict[str, str], slots: list[PartnerSlot], params: Params
) -> dict[str, str]:
    """Ghép học viên (đã có nhánh) với vị trí của đối tác cùng nhánh, ưu tiên khớp kỹ năng rồi đến điểm."""
    by_id = {lr.id: lr for lr in learners}
    result: dict[str, str] = {}
    for track in sorted({s.track for s in slots}):
        members = [by_id[i] for i, t in tracks.items() if t == track and i in by_id]
        expanded = [(s.partner_id, s.skills) for s in slots if s.track == track for _ in range(s.slots)]
        if not members or not expanded:
            continue
        w = params.placement_skill_weight
        utility = np.array(
            [
                [
                    w * (len(m.skills & skills) / max(1, len(m.skills | skills))) + (1 - w) * m.score / 100
                    for _, skills in expanded
                ]
                for m in members
            ]
        )
        rows, cols = linear_sum_assignment(-utility)
        for r, c in zip(rows, cols, strict=True):
            result[members[r].id] = expanded[c][0]
    return result


def explain(
    learner: Learner,
    track: str | None,
    class_idx: int | None,
    params: Params,
    class_ranges: dict[int, tuple[float, float]],
) -> str:
    parts: list[str] = []
    if track:
        try:
            parts.append(
                f"Nhánh {track}: nguyện vọng {learner.prefs.index(track) + 1}, độ phù hợp {learner.fit.get(track, 0):.0%}"
            )
        except ValueError:
            parts.append(
                f"Nhánh {track}: ngoài nguyện vọng đã chọn (độ phù hợp {learner.fit.get(track, 0):.0%}) do sức chứa các nhánh ưa thích đã đầy"
            )
    if class_idx is not None:
        low, high = class_ranges.get(class_idx, (0.0, 0.0))
        if params.class_mode == "levels":
            parts.append(f"Lớp mức {class_idx + 1}: điểm {learner.score:.0f} nằm trong khoảng {low:.0f}–{high:.0f}")
        else:
            parts.append(f"Lớp {class_idx + 1}: xếp cân bằng điểm và nhóm nền tảng ('{learner.background}')")
    return "; ".join(parts)


def compose(learners: list[Learner], params: Params, partner_slots: list[PartnerSlot] | None = None) -> dict[str, Any]:
    """Chạy toàn bộ bộ giải và trả về phương án kèm chỉ số chất lượng."""
    params.validate(len(learners))
    tracks = assign_tracks(learners, params)
    classes = assign_classes(learners, params)
    placements = assign_placements(learners, tracks, partner_slots or [], params) if partner_slots else {}

    class_scores: dict[int, list[float]] = defaultdict(list)
    class_bg: dict[int, Counter[str]] = defaultdict(Counter)
    for lr in learners:
        class_scores[classes[lr.id]].append(lr.score)
        class_bg[classes[lr.id]][lr.background] += 1
    ranges = {i: (min(v), max(v)) for i, v in class_scores.items()}

    assignments = [
        {
            "learner_id": lr.id,
            "class_index": classes[lr.id],
            "track": tracks.get(lr.id),
            "partner_id": placements.get(lr.id),
            "explanation": explain(lr, tracks.get(lr.id), classes[lr.id], params, ranges),
        }
        for lr in learners
    ]

    ranks = [lr.prefs.index(tracks[lr.id]) + 1 for lr in learners if lr.id in tracks and tracks[lr.id] in lr.prefs]
    with_prefs = [lr for lr in learners if lr.prefs and lr.id in tracks]
    fills = Counter(tracks.values())
    class_means = [mean(v) for v in class_scores.values()]
    placed = len(placements)
    in_tracks = len(tracks)
    metrics: dict[str, Any] = {
        "learners": len(learners),
        "classes": [
            {
                "index": i,
                "size": len(class_scores[i]),
                "mean_score": round(mean(class_scores[i]), 1),
                "std_score": round(pstdev(class_scores[i]), 1) if len(class_scores[i]) > 1 else 0.0,
                "min_score": round(ranges[i][0], 1),
                "max_score": round(ranges[i][1], 1),
                "background": dict(class_bg[i]),
            }
            for i in sorted(class_scores)
        ],
        "class_mean_spread": round(max(class_means) - min(class_means), 1) if class_means else 0.0,
        "pref_first_rate": round(sum(1 for r in ranks if r == 1) / len(with_prefs), 3) if with_prefs else None,
        "pref_top2_rate": round(sum(1 for r in ranks if r <= 2) / len(with_prefs), 3) if with_prefs else None,
        "avg_fit": round(mean(lr.fit.get(tracks[lr.id], 0.0) for lr in learners if lr.id in tracks), 3)
        if tracks
        else None,
        "track_fill": {
            t: {"assigned": fills.get(t, 0), "capacity": params.track_capacity[t]}
            for t in sorted(params.track_capacity)
        },
        "placed": placed,
        "placement_rate": round(placed / in_tracks, 3) if in_tracks and partner_slots else None,
    }
    return {"assignments": assignments, "metrics": metrics}
