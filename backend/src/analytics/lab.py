"""Rubric Lab: tiêu chí tuyển chọn nào dự đoán được kết quả đào tạo, và đổi trọng số thì ai sẽ được chọn khác đi.

Lưu ý trung thực về dữ liệu: chỉ biết kết quả của người đã được nhận (thiên lệch chọn lọc, hẹp dải điểm).
Vì vậy mọi kết luận gắn cờ độ tin cậy; phần mô phỏng tách rõ phần "quan sát được" và phần "ước lượng bằng mô hình".
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

MIN_N = 60
MIN_EVENTS = 15


@dataclass(frozen=True)
class Applicant:
    id: str
    scores: dict[str, float]  # tiêu chí -> điểm chuẩn hoá 0..1
    admitted: bool
    outcome: int | None  # 1 đạt, 0 chưa đạt, None chưa biết/không được nhận
    groups: dict[str, str]  # thuộc tính tự khai dùng để kiểm tra công bằng (giới tính, khu vực)


def _matrix(rows: list[Applicant], criteria: list[str]) -> np.ndarray:
    return np.array([[r.scores.get(c, 0.0) for c in criteria] for r in rows], dtype=float)


def auc(y: np.ndarray, score: np.ndarray) -> float | None:
    """AUC theo công thức hạng Mann-Whitney; None nếu thiếu một trong hai lớp."""
    pos, neg = score[y == 1], score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    values = np.concatenate([pos, neg])[order]
    i = 0
    rank_values = np.empty(len(values))
    while i < len(values):  # xử lý đồng hạng bằng hạng trung bình
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        rank_values[i : j + 1] = (i + j) / 2 + 1
        i = j + 1
    ranks[order] = rank_values
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 60) -> tuple[np.ndarray, float]:
    """Hồi quy logistic có chuẩn hoá L2 (IRLS). X nên được chuẩn hoá trước. Trả (hệ số, hằng số)."""
    n, d = x.shape
    xb = np.hstack([x, np.ones((n, 1))])
    beta = np.zeros(d + 1)
    reg = np.diag([l2] * d + [0.0])
    for _ in range(iters):
        z = np.clip(xb @ beta, -30, 30)
        p = 1 / (1 + np.exp(-z))
        w = np.clip(p * (1 - p), 1e-6, None)
        grad = xb.T @ (y - p) - reg @ beta
        hess = (xb * w[:, None]).T @ xb + reg
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-7:
            break
    return beta[:d], float(beta[d])


def bootstrap_coefs(
    x: np.ndarray,
    y: np.ndarray,
    counts: np.ndarray,
    start: np.ndarray | None = None,
    l2: float = 1.0,
    iters: int = 60,
    chunk: int = 50,
) -> np.ndarray:
    """Hệ số (thang chuẩn hoá) của `fit_logistic` trên từng mẫu bootstrap, giải đồng thời cả loạt.

    Mẫu bootstrap thứ b là số lần mỗi dòng được rút (`counts[b]`, tổng = n); bỏ mẫu chỉ có một lớp. Tương đương với
    chuẩn hoá `x[mẫu]` rồi gọi `fit_logistic` cho từng mẫu (cùng nghiệm tối ưu duy nhất), nhưng làm trên dữ liệu gốc
    có trọng số: chuẩn hoá theo trọng số, đổi phạt L2 sang thang gốc (l2·sd²) rồi quy đổi hệ số về thang chuẩn hoá.
    Nhanh hơn nhiều so với vòng lặp vì mỗi bước IRLS là vài phép nhân ma trận cho cả loạt. `start` (hệ số thang gốc,
    kèm hằng số ở cuối) là điểm xuất phát, thường lấy từ mô hình trên toàn bộ dữ liệu để hội tụ sau ít vòng hơn.
    """
    n, d = x.shape
    total = counts.sum(axis=1)
    positives = counts @ y
    counts = counts[(positives > 0) & (positives < total)]
    if len(counts) == 0:
        return np.zeros((0, d))
    xb = np.hstack([x, np.ones((n, 1))])
    outer = (xb[:, :, None] * xb[:, None, :]).reshape(n, (d + 1) ** 2)  # x_i x_iᵀ của từng dòng, trải phẳng
    out = []
    for first in range(0, len(counts), chunk):
        c = counts[first : first + chunk]  # (B, n)
        size = c.sum(axis=1, keepdims=True)
        mu = c @ x / size
        sd = np.sqrt(np.maximum(c @ (x * x) / size - mu * mu, 0.0))
        sd[sd < 1e-9] = 1.0
        reg = np.zeros((len(c), d + 1, d + 1))
        reg[:, np.arange(d), np.arange(d)] = l2 * sd * sd
        beta = np.tile(start, (len(c), 1)) if start is not None else np.zeros((len(c), d + 1))
        for _ in range(iters):
            z = np.clip(beta @ xb.T, -30, 30)  # (B, n)
            p = 1 / (1 + np.exp(-z))
            w = np.clip(p * (1 - p), 1e-6, None) * c
            grad = ((y - p) * c) @ xb - np.einsum("bij,bj->bi", reg, beta)
            hess = (w @ outer).reshape(len(c), d + 1, d + 1) + reg
            step = np.linalg.solve(hess, grad[:, :, None])[:, :, 0]
            beta += step
            if np.max(np.abs(step * np.hstack([sd, np.ones((len(c), 1))]))) < 1e-7:
                break
        out.append(beta[:, :d] * sd)
    return np.vstack(out)


def _standardise(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = x.mean(axis=0)
    sd = x.std(axis=0)
    sd[sd < 1e-9] = 1.0
    return (x - mu) / sd, mu, sd


def cross_val_auc(x: np.ndarray, y: np.ndarray, folds: int = 5, seed: int = 0) -> float | None:
    """AUC kiểm chứng chéo: tránh ảo tưởng do khớp quá trên chính dữ liệu huấn luyện."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(y))
    preds = np.zeros(len(y))
    for f in range(folds):
        test = idx[f::folds]
        train = np.setdiff1d(idx, test)
        if len(np.unique(y[train])) < 2:
            return None
        xs, mu, sd = _standardise(x[train])
        coef, b = fit_logistic(xs, y[train])
        preds[test] = ((x[test] - mu) / sd) @ coef + b
    return auc(y, preds)


def analyse(rows: list[Applicant], criteria: list[str], *, bootstrap: int = 200, seed: int = 11) -> dict[str, Any]:
    """Phân tích giá trị dự báo của từng tiêu chí trên nhóm đã được nhận và đã có kết quả."""
    labelled = [r for r in rows if r.outcome is not None]
    warnings: list[str] = []
    n = len(labelled)
    y = np.array([r.outcome for r in labelled], dtype=float)
    events = int(y.sum()) if n else 0
    if n < MIN_N:
        warnings.append(f"Mới có {n} học viên có kết quả (cần tối thiểu {MIN_N}): kết luận chưa đủ tin cậy.")
    if n and (events < MIN_EVENTS or n - events < MIN_EVENTS):
        warnings.append("Số học viên đạt hoặc chưa đạt quá ít để ước lượng ổn định.")
    warnings.append(
        "Chỉ có kết quả của người đã được nhận nên dải điểm bị thu hẹp; tác động thật của tiêu chí có thể lớn hơn số đo."
    )
    if n < 10 or len(np.unique(y)) < 2:
        return {"n": n, "events": events, "criteria": [], "model_auc": None, "warnings": warnings, "reliable": False}

    x = _matrix(labelled, criteria)
    xs, mu, sd = _standardise(x)
    coef, intercept = fit_logistic(xs, y)

    rng = np.random.default_rng(seed)
    counts = np.array([np.bincount(rng.integers(0, n, n), minlength=n) for _ in range(bootstrap)], dtype=float)
    # Mẫu bootstrap xuất phát từ mô hình trên toàn bộ dữ liệu (quy về thang gốc): gần nghiệm nên hội tụ nhanh.
    start = np.append(coef / sd, intercept - float(np.sum(coef * mu / sd)))
    boot_arr = bootstrap_coefs(x, y, counts, start)
    if len(boot_arr) == 0:
        boot_arr = np.zeros((1, len(criteria)))
    lo, hi = np.percentile(boot_arr, [5, 95], axis=0)

    per = []
    for j, name in enumerate(criteria):
        per.append(
            {
                "criterion": name,
                "coef": round(float(coef[j]), 4),
                "ci90": [round(float(lo[j]), 4), round(float(hi[j]), 4)],
                "significant": bool(lo[j] > 0 or hi[j] < 0),
                "auc": None if (a := auc(y, x[:, j])) is None else round(a, 4),
                "mean_if_qualified": round(float(x[y == 1, j].mean()), 4),
                "mean_if_not": round(float(x[y == 0, j].mean()), 4),
            }
        )
    cv = cross_val_auc(x, y)
    return {
        "n": n,
        "events": events,
        "qualified_rate": round(events / n, 4),
        "criteria": per,
        "model_auc": None if cv is None else round(cv, 4),
        "warnings": warnings,
        "reliable": n >= MIN_N and events >= MIN_EVENTS and n - events >= MIN_EVENTS,
    }


def _composite(rows: list[Applicant], weights: dict[str, float]) -> np.ndarray:
    total = sum(w for w in weights.values() if w > 0)
    if total <= 0:
        raise ValueError("Tổng trọng số phải lớn hơn 0")
    return np.array([sum(weights.get(c, 0.0) * r.scores.get(c, 0.0) for c in weights) / total for r in rows])


def _top_k(scores: np.ndarray, ids: list[str], k: int) -> set[str]:
    order = sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))
    return {ids[i] for i in order[:k]}


def selection_rates(rows: list[Applicant], selected: set[str], min_group: int = 20) -> dict[str, Any]:
    """Tỉ lệ được chọn theo nhóm và tỉ lệ tác động (quy tắc bốn phần năm: min/max, dưới 0,8 là cần xem lại)."""
    out: dict[str, Any] = {}
    attributes = sorted({k for r in rows for k in r.groups})
    for attr in attributes:
        groups: dict[str, list[Applicant]] = {}
        for r in rows:
            groups.setdefault(r.groups.get(attr, "khong_khai"), []).append(r)
        rates = {
            g: sum(1 for m in members if m.id in selected) / len(members)
            for g, members in groups.items()
            if len(members) >= min_group and g != "khong_khai"
        }
        sizes = {g: len(m) for g, m in groups.items()}
        ratio = (min(rates.values()) / max(rates.values())) if len(rates) >= 2 and max(rates.values()) > 0 else None
        out[attr] = {
            "rates": {g: round(r, 4) for g, r in rates.items()},
            "sizes": sizes,
            "impact_ratio": None if ratio is None else round(ratio, 4),
        }
    return out


def simulate(
    pool: list[Applicant],
    old_weights: dict[str, float],
    new_weights: dict[str, float],
    admitted_count: int,
    model_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Chạy lại xếp hạng của một đợt đã qua với trọng số mới."""
    ids = [r.id for r in pool]
    k = max(1, min(admitted_count, len(pool)))
    old_sel = _top_k(_composite(pool, old_weights), ids, k)
    new_sel = _top_k(_composite(pool, new_weights), ids, k)
    actual = {r.id for r in pool if r.admitted}
    by_id = {r.id: r for r in pool}

    def observed_rate(selected: set[str]) -> dict[str, Any]:
        known = [by_id[i] for i in selected if by_id[i].outcome is not None]
        rate = sum(r.outcome for r in known if r.outcome is not None) / len(known) if known else None
        return {"known": len(known), "of": len(selected), "qualified_rate": None if rate is None else round(rate, 4)}

    out: dict[str, Any] = {
        "pool": len(pool),
        "selected": k,
        "overlap_old_new": round(len(old_sel & new_sel) / k, 4),
        "changed_in": len(new_sel - old_sel),
        "overlap_actual_old": round(len(actual & old_sel) / max(1, len(actual)), 4),
        "observed_old": observed_rate(old_sel),
        "observed_new": observed_rate(new_sel),
        "fairness_old": selection_rates(pool, old_sel),
        "fairness_new": selection_rates(pool, new_sel),
        "newly_selected_ids": sorted(new_sel - old_sel)[:50],
        "dropped_ids": sorted(old_sel - new_sel)[:50],
    }
    if model_scores:

        def expected(selected: set[str]) -> float:
            return round(float(np.mean([model_scores[i] for i in selected if i in model_scores])), 4)

        out["model_expected_old"] = expected(old_sel)
        out["model_expected_new"] = expected(new_sel)
        out["model_note"] = "Ước lượng bằng mô hình, ngoại suy cho cả người chưa được nhận; chỉ mang tính tham khảo."
    return out


def predict_probabilities(rows: list[Applicant], pool: list[Applicant], criteria: list[str]) -> dict[str, float]:
    """Huấn luyện trên nhóm có kết quả rồi dự đoán xác suất đạt cho toàn bộ pool."""
    labelled = [r for r in rows if r.outcome is not None]
    y = np.array([r.outcome for r in labelled], dtype=float)
    if len(labelled) < 10 or len(np.unique(y)) < 2:
        return {}
    x = _matrix(labelled, criteria)
    xs, mu, sd = _standardise(x)
    coef, b = fit_logistic(xs, y)
    probs = 1 / (1 + np.exp(-np.clip(((_matrix(pool, criteria) - mu) / sd) @ coef + b, -30, 30)))
    return {r.id: float(p) for r, p in zip(pool, probs, strict=True)}
