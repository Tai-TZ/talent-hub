import random
import time
from collections import Counter

import pytest

from src.composer.solver import ComposerError, Learner, Params, PartnerSlot, assign_classes, assign_tracks, compose

TRACKS = ("ai_products", "ai_infrastructure", "ai_applications")


def make_learners(n: int, seed: int = 7) -> list[Learner]:
    rng = random.Random(seed)
    learners = []
    for i in range(n):
        prefs = tuple(rng.sample(TRACKS, k=rng.choice((1, 2, 3))))
        fit = {t: round(rng.random(), 3) for t in TRACKS}
        skills = frozenset(
            rng.sample(["python", "docker", "sql", "llm", "figma", "kubernetes", "react", "pytorch"], k=3)
        )
        learners.append(
            Learner(
                id=f"L{i:04d}",
                score=round(rng.gauss(60, 15), 1),
                prefs=prefs,
                fit=fit,
                skills=skills,
                background=rng.choice(("tech", "non_tech")),
            )
        )
    return learners


def test_track_assignment_respects_capacity_and_beats_greedy() -> None:
    learners = make_learners(90)
    params = Params(track_capacity={"ai_products": 20, "ai_infrastructure": 30, "ai_applications": 40})
    tracks = assign_tracks(learners, params)
    counts = Counter(tracks.values())
    assert len(tracks) == 90 and all(counts[t] <= c for t, c in params.track_capacity.items())

    def utility(assign: dict[str, str]) -> float:
        total = 0.0
        for lr in learners:
            pref = (1.0, 0.6, 0.3)[lr.prefs.index(assign[lr.id])] if assign[lr.id] in lr.prefs else 0.0
            total += 0.6 * pref + 0.4 * lr.fit[assign[lr.id]]
        return total

    # tham lam: lần lượt cho mỗi người nhánh tốt nhất còn chỗ
    remaining = dict(params.track_capacity)
    greedy: dict[str, str] = {}
    for lr in learners:
        best = max(
            (t for t in TRACKS if remaining[t] > 0),
            key=lambda t: 0.6 * ((1.0, 0.6, 0.3)[lr.prefs.index(t)] if t in lr.prefs else 0) + 0.4 * lr.fit[t],
        )
        greedy[lr.id] = best
        remaining[best] -= 1
    assert utility(tracks) >= utility(greedy) - 1e-9


def test_insufficient_capacity_and_bad_params_are_rejected() -> None:
    learners = make_learners(10)
    with pytest.raises(ComposerError, match="sức chứa"):
        compose(learners, Params(track_capacity={"ai_products": 3, "ai_infrastructure": 3}))
    with pytest.raises(ComposerError):
        compose(learners, Params(track_capacity={"ai_products": 10}, class_mode="chaos"))
    with pytest.raises(ComposerError):
        compose(learners, Params(track_capacity={"ai_products": 10}, pref_weight=0, fit_weight=0))
    with pytest.raises(ComposerError):
        compose(learners, Params(track_capacity={"ai_products": 10}, class_count=0))


def test_level_classes_are_homogeneous_and_balanced_in_size() -> None:
    learners = make_learners(100)
    classes = assign_classes(learners, Params(track_capacity={}, class_count=3, class_mode="levels"))
    sizes = Counter(classes.values())
    assert max(sizes.values()) - min(sizes.values()) <= 1
    ranges = {}
    for lr in learners:
        low, high = ranges.get(classes[lr.id], (999.0, -999.0))
        ranges[classes[lr.id]] = (min(low, lr.score), max(high, lr.score))
    # lớp 0 là nhóm điểm cao nhất; khoảng điểm các lớp không chồng lấn
    assert ranges[0][0] >= ranges[1][1] and ranges[1][0] >= ranges[2][1]


def test_balanced_classes_equalise_scores_and_background_mix() -> None:
    learners = make_learners(120)
    balanced = compose(learners, Params(track_capacity={"ai_products": 120}, class_count=4, class_mode="balanced"))
    levels = compose(learners, Params(track_capacity={"ai_products": 120}, class_count=4, class_mode="levels"))
    assert balanced["metrics"]["class_mean_spread"] < 2.0 < levels["metrics"]["class_mean_spread"]
    sizes = [c["size"] for c in balanced["metrics"]["classes"]]
    assert max(sizes) - min(sizes) <= 1
    tech_shares = [c["background"].get("tech", 0) / c["size"] for c in balanced["metrics"]["classes"]]
    assert max(tech_shares) - min(tech_shares) < 0.15


def test_compose_reports_preference_satisfaction_and_explanations() -> None:
    learners = make_learners(60)
    out = compose(learners, Params(track_capacity={"ai_products": 20, "ai_infrastructure": 20, "ai_applications": 20}))
    m = out["metrics"]
    assert 0.5 <= m["pref_top2_rate"] <= 1.0 and m["pref_first_rate"] <= m["pref_top2_rate"]
    assert all(a["explanation"] for a in out["assignments"])
    assert sum(t["assigned"] for t in m["track_fill"].values()) == 60


def test_placements_respect_slots_and_prefer_skill_match() -> None:
    learners = [
        Learner(id="a", score=70, skills=frozenset({"docker", "kubernetes"})),
        Learner(id="b", score=70, skills=frozenset({"figma"})),
    ]
    slots = [
        PartnerSlot(
            partner_id="infra-co", track="ai_infrastructure", slots=1, skills=frozenset({"docker", "kubernetes"})
        ),
        PartnerSlot(partner_id="design-co", track="ai_infrastructure", slots=1, skills=frozenset({"figma"})),
    ]
    out = compose(
        learners,
        Params(track_capacity={"ai_infrastructure": 2}, class_count=1),
        slots,
    )
    placed = {a["learner_id"]: a["partner_id"] for a in out["assignments"]}
    assert placed == {"a": "infra-co", "b": "design-co"}
    assert out["metrics"]["placement_rate"] == 1.0


def test_solver_is_deterministic_and_fast_for_a_full_cohort() -> None:
    learners = make_learners(500)
    params = Params(
        track_capacity={"ai_products": 150, "ai_infrastructure": 150, "ai_applications": 200}, class_count=10
    )
    started = time.perf_counter()
    first = compose(learners, params)
    elapsed = time.perf_counter() - started
    assert first == compose(learners, params)
    assert elapsed < 3.0, f"500 học viên mất {elapsed:.2f}s"
