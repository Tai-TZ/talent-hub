import numpy as np
import pytest

from src.analytics.lab import Applicant, analyse, auc, predict_probabilities, selection_rates, simulate

CRITERIA = ["projects", "programming", "motivation", "noise"]
TRUE = {"projects": 1.6, "programming": 0.9, "motivation": 0.0, "noise": 0.0}


def synthetic(n: int = 600, seed: int = 3, admit_rate: float = 0.5) -> list[Applicant]:
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 1, size=(n, len(CRITERIA)))
    logit = sum(TRUE[c] * (x[:, j] - 0.5) * 4 for j, c in enumerate(CRITERIA)) + rng.normal(0, 0.8, n)
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(int)
    composite = x[:, 0] * 3 + x[:, 1] * 2 + x[:, 2]  # rubric thật sự được dùng khi tuyển
    admitted_idx = set(np.argsort(-composite)[: int(n * admit_rate)])
    genders = rng.choice(["female", "male"], n)
    return [
        Applicant(
            id=f"A{i:04d}",
            scores={c: float(x[i, j]) for j, c in enumerate(CRITERIA)},
            admitted=i in admitted_idx,
            outcome=int(y[i]) if i in admitted_idx else None,
            groups={"gender": str(genders[i])},
        )
        for i in range(n)
    ]


def test_auc_matches_known_values() -> None:
    y = np.array([0, 0, 1, 1])
    assert auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    assert auc(np.array([1, 1]), np.array([0.1, 0.2])) is None


def test_lab_recovers_which_criteria_matter() -> None:
    rows = synthetic()
    report = analyse(rows, CRITERIA)
    by = {c["criterion"]: c for c in report["criteria"]}
    assert report["reliable"] and report["model_auc"] > 0.65
    # tiêu chí thật sự có ảnh hưởng thì có ý nghĩa và đúng thứ tự; tiêu chí nhiễu thì khoảng tin cậy chứa 0
    assert by["projects"]["significant"] and by["projects"]["coef"] > by["programming"]["coef"] > 0
    assert not by["noise"]["significant"] and by["noise"]["ci90"][0] < 0 < by["noise"]["ci90"][1]
    assert by["projects"]["mean_if_qualified"] > by["projects"]["mean_if_not"]
    assert any("thu hẹp" in w for w in report["warnings"])  # luôn nói rõ giới hạn dữ liệu


def test_small_samples_are_flagged_unreliable() -> None:
    report = analyse(synthetic(n=40, admit_rate=1.0), CRITERIA)
    assert report["reliable"] is False and any("tối thiểu" in w for w in report["warnings"])
    empty = analyse([], CRITERIA)
    assert empty["criteria"] == [] and empty["reliable"] is False


def test_simulation_with_same_weights_changes_nobody() -> None:
    pool = synthetic()
    weights = {"projects": 3, "programming": 2, "motivation": 1, "noise": 0}
    out = simulate(pool, weights, weights, admitted_count=sum(1 for r in pool if r.admitted))
    assert out["overlap_old_new"] == 1.0 and out["changed_in"] == 0
    assert out["overlap_actual_old"] == 1.0  # rubric cũ tái tạo đúng danh sách đã nhận


def test_shifting_weight_to_predictive_criteria_improves_model_expected_rate() -> None:
    pool = synthetic()
    probs = predict_probabilities(pool, pool, CRITERIA)
    old = {"projects": 3, "programming": 2, "motivation": 1, "noise": 0}
    better = {"projects": 6, "programming": 3, "motivation": 0, "noise": 0}
    worse = {"projects": 0, "programming": 0, "motivation": 3, "noise": 3}
    k = sum(1 for r in pool if r.admitted)
    up = simulate(pool, old, better, k, probs)
    down = simulate(pool, old, worse, k, probs)
    assert up["model_expected_new"] >= up["model_expected_old"] - 1e-9
    assert down["model_expected_new"] < down["model_expected_old"]
    assert "ngoại suy" in up["model_note"]
    assert down["changed_in"] > up["changed_in"]


def test_fairness_impact_ratio_flags_disparity() -> None:
    rows = [
        Applicant(
            id=f"m{i}", scores={"x": 1.0 if i < 40 else 0.0}, admitted=False, outcome=None, groups={"gender": "male"}
        )
        for i in range(50)
    ] + [
        Applicant(
            id=f"f{i}", scores={"x": 1.0 if i < 10 else 0.0}, admitted=False, outcome=None, groups={"gender": "female"}
        )
        for i in range(50)
    ]
    selected = {r.id for r in rows if r.scores["x"] == 1.0}
    gender = selection_rates(rows, selected)["gender"]
    assert gender["rates"] == {"female": 0.2, "male": 0.8}
    assert gender["impact_ratio"] == 0.25  # dưới 0,8: cần xem lại
    small = selection_rates(rows[:10], selected)["gender"]
    assert small["impact_ratio"] is None  # nhóm quá nhỏ thì không kết luận


def test_zero_weights_are_rejected() -> None:
    pool = synthetic(n=50)
    with pytest.raises(ValueError):
        simulate(pool, {"projects": 1}, {"projects": 0}, 10)
