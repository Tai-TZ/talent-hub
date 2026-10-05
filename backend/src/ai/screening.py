"""Kiểu dữ liệu và quy tắc chung cho sàng lọc hồ sơ bằng AI.

Nguyên tắc: AI chỉ **gợi ý**. Mọi trích dẫn bằng chứng phải xuất hiện nguyên văn trong hồ sơ
(được kiểm chứng ở đây, không tin lời mô hình); trích dẫn không kiểm chứng được sẽ bị loại và làm giảm độ tin cậy.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.ai.text import find_span, norm

PROMPT_VERSION = "screen-v1"

DEFAULT_THRESHOLDS = {"invite": 68.0, "decline": 42.0, "min_confidence": 0.5, "margin": 6.0}

TIER_INVITE = "invite"
TIER_REVIEW = "review"
TIER_DECLINE = "decline_likely"

# Dấu hiệu nhúng chỉ dẫn vào hồ sơ để thao túng AI chấm (prompt injection).
INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
        r"disregard (all |any )?(the )?(previous|prior|above)",
        r"(give|assign|award) (me|this (candidate|applicant)) (a )?(full|perfect|maximum|top) (score|marks|rating)",
        r"bỏ qua (tất cả |mọi )?(các )?(hướng dẫn|chỉ dẫn|yêu cầu) (trước|ở trên)",
        r"(hãy )?(cho|chấm) (tôi|ứng viên này) (điểm )?(tối đa|tuyệt đối|cao nhất)",
        r"you are now|system prompt|<\s*/?\s*(system|assistant)\s*>",
    )
]


@dataclass(frozen=True)
class Evidence:
    field: str
    quote: str
    start: int
    end: int


@dataclass
class CriterionResult:
    id: str
    score: float
    max: float
    evidence: list[Evidence] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0


@dataclass
class ScreeningResult:
    engine: str
    model: str | None
    prompt_version: str
    criteria: list[CriterionResult]
    total_score: float
    confidence: float
    tier: str
    needs_attention: bool
    flags: list[dict[str, Any]]
    summary: str
    input_fields: list[str]
    dropped_quotes: int = 0
    usage: dict[str, int] | None = None


class ScreeningError(Exception):
    """Động cơ không trả được kết quả dùng được (lỗi dịch vụ, từ chối, đầu ra sai cấu trúc)."""


class ScreeningEngine(Protocol):
    name: str

    async def screen(
        self, content: dict[str, Any], criteria: list[dict[str, Any]], thresholds: dict[str, float]
    ) -> ScreeningResult: ...


def verify_evidence(fields: dict[str, str], raw: list[tuple[str, str]]) -> tuple[list[Evidence], int]:
    """Giữ lại các trích dẫn thật sự có trong trường được nêu; trả (đã kiểm chứng, số bị loại)."""
    verified: list[Evidence] = []
    dropped = 0
    seen: set[tuple[str, str]] = set()
    for field_key, quote in raw:
        quote = norm(quote).strip()
        text = fields.get(field_key)
        span = find_span(text, quote) if text is not None and len(quote) >= 8 else None
        if span is None:
            dropped += 1
            continue
        exact = norm(text)[span[0] : span[1]]  # type: ignore[arg-type]
        key = (field_key, exact)
        if key in seen:
            continue
        seen.add(key)
        verified.append(Evidence(field=field_key, quote=exact, start=span[0], end=span[1]))
    return verified, dropped


def weighted_total(criteria_defs: list[dict[str, Any]], results: list[CriterionResult]) -> float:
    by_id = {r.id: r for r in results}
    weight_sum = sum(c["weight"] for c in criteria_defs)
    if weight_sum <= 0:
        return 0.0
    achieved = sum(
        (min(max(by_id[c["id"]].score, 0.0), c["max"]) / c["max"]) * c["weight"]
        for c in criteria_defs
        if c["id"] in by_id
    )
    return float(round(achieved / weight_sum * 100, 2))


def weighted_confidence(criteria_defs: list[dict[str, Any]], results: list[CriterionResult]) -> float:
    by_id = {r.id: r for r in results}
    weight_sum = sum(c["weight"] for c in criteria_defs)
    if weight_sum <= 0:
        return 0.0
    value = sum(by_id[c["id"]].confidence * c["weight"] for c in criteria_defs if c["id"] in by_id)
    return float(round(value / weight_sum, 3))


def injection_flags(fields: dict[str, str]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for key, text in fields.items():
        for pattern in INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                flags.append(
                    {
                        "source": "ai",
                        "rule": "injection_suspected",
                        "label": "Hồ sơ chứa câu giống chỉ dẫn gửi cho AI; đã bỏ qua và cần người xem kỹ",
                        "severity": "warning",
                        "field": key,
                        "quote": norm(match.group(0)),
                    }
                )
                break
    return flags


def decide_tier(
    total: float, confidence: float, flags: list[dict[str, Any]], thresholds: dict[str, float]
) -> tuple[str, bool]:
    """Tier là gợi ý. `needs_attention` trung tính về hướng: AI không chắc hoặc có cờ cần người xem kỹ."""
    t = {**DEFAULT_THRESHOLDS, **thresholds}
    confident = confidence >= t["min_confidence"]
    if confident and total >= t["invite"]:
        tier = TIER_INVITE
    elif confident and total < t["decline"]:
        tier = TIER_DECLINE
    else:
        tier = TIER_REVIEW
    near_boundary = abs(total - t["invite"]) <= t["margin"] or abs(total - t["decline"]) <= t["margin"]
    has_warning = any(f.get("severity") == "warning" for f in flags)
    return tier, (not confident) or near_boundary or has_warning
