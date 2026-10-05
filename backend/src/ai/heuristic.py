"""Động cơ sàng lọc chạy offline bằng luật và từ vựng (song ngữ Việt-Anh).

Có hai vai trò: (1) chạy được không cần khoá API, nên demo và test ổn định; (2) phương án dự phòng khi dịch vụ LLM
lỗi. Cho kết quả có bằng chứng trích nguyên văn nên người xét duyệt kiểm chứng được. Không dùng bất kỳ thông tin nhận
dạng nào (chỉ nhận `content`).
"""

import functools
import json
import re
from collections.abc import Callable
from typing import Any

from src.ai.screening import (
    PROMPT_VERSION,
    CriterionResult,
    ScreeningResult,
    decide_tier,
    injection_flags,
    verify_evidence,
    weighted_confidence,
    weighted_total,
)
from src.ai.text import build_fields, sentences, words

LANGUAGES = (
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c#",
    "golang",
    "rust",
    "kotlin",
    "swift",
    "php",
    "ruby",
    "sql",
    "bash",
)
TOOLS = (
    "git",
    "docker",
    "linux",
    "kubernetes",
    "fastapi",
    "django",
    "flask",
    "react",
    "node",
    "spring",
    "aws",
    "gcp",
    "azure",
    "ci/cd",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "api",
    "backend",
    "frontend",
)
AI_TERMS = (
    "machine learning",
    "deep learning",
    "pytorch",
    "tensorflow",
    "nlp",
    "llm",
    "rag",
    "transformer",
    "hugging face",
    "huggingface",
    "scikit-learn",
    "sklearn",
    "computer vision",
    "neural",
    "học máy",
    "học sâu",
    "xử lý ngôn ngữ",
    "thị giác máy tính",
    "mô hình ngôn ngữ",
    "fine-tune",
    "embedding",
)
DATA_TERMS = (
    "sql",
    "pandas",
    "numpy",
    "spark",
    "data analysis",
    "phân tích dữ liệu",
    "power bi",
    "tableau",
    "etl",
    "data pipeline",
    "dashboard",
    "thống kê",
    "statistics",
    "visualization",
    "trực quan hoá",
)
RELEVANT_MAJORS = (
    "khoa học máy tính",
    "công nghệ thông tin",
    "kỹ thuật phần mềm",
    "computer science",
    "information technology",
    "software engineering",
    "data science",
    "khoa học dữ liệu",
    "trí tuệ nhân tạo",
    "artificial intelligence",
    "an toàn thông tin",
    "cybersecurity",
    "toán",
    "mathematics",
    "điện tử",
    "viễn thông",
)
CONCRETE = re.compile(
    r"\d+|dự án|project|xây dựng|built|triển khai|deploy|mô hình|model|ứng dụng|hệ thống|system|mục tiêu|goal|kế hoạch"
)
METHOD = (
    "bước",
    "đo lường",
    "kiểm thử",
    "giả thuyết",
    "đánh đổi",
    "trade-off",
    "first",
    "then",
    "sau đó",
    "trước hết",
    "phân tích",
    "thử nghiệm",
    "so sánh",
    "test",
    "measure",
    "iterate",
    "lặp",
    "cải tiến",
)
GENERIC = ("đam mê", "passionate", "nhiệt huyết", "cầu tiến", "hardworking", "chăm chỉ")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@functools.lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")


PLAIN_TERMS = frozenset(("c++", "c#", "ci/cd"))  # có ký tự không phải chữ ở cuối nên chỉ so chuỗi con


def _hits(text: str, terms: tuple[str, ...]) -> set[str]:
    """Các từ khoá xuất hiện trọn từ trong `text` (không phân biệt hoa/thường).

    Lọc bằng phép tìm chuỗi con trước: là điều kiện cần, rẻ hơn regex nhiều và loại được phần lớn từ khoá.
    Hàm nóng nhất khi chấm hàng loạt nên viết gọn trong một biểu thức.
    """
    lowered = text.lower()
    return {t for t in terms if t in lowered and (t in PLAIN_TERMS or _term_pattern(t).search(lowered) is not None)}


def _sentence_evidence(
    fields: dict[str, str], terms: tuple[str, ...], keys: tuple[str, ...] | None, limit: int = 3
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, text in fields.items():
        if keys is not None and not any(key == k or key.startswith(k + ".") for k in keys):
            continue
        for sentence in sentences(text):
            if _hits(sentence, terms):
                out.append((key, sentence[:240]))
                break
        if len(out) >= limit:
            break
    return out


Scorer = Callable[[dict[str, Any], dict[str, str], dict[str, Any]], tuple[float, list[tuple[str, str]], str, float]]


def _programming(
    content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
) -> tuple[float, list[tuple[str, str]], str, float]:
    text = " ".join(fields.values())
    langs = _hits(text, LANGUAGES)
    tools = _hits(text, TOOLS)
    applied_fields = [
        k for k, v in fields.items() if k.startswith(("projects.", "experience.")) and _hits(v, LANGUAGES + TOOLS)
    ]
    breadth = _clamp(len(langs) / 4)
    applied = _clamp(len(applied_fields) / 2)
    tooling = _clamp(len(tools) / 4)
    frac = 0.35 * breadth + 0.45 * applied + 0.20 * tooling
    evidence = _sentence_evidence(fields, LANGUAGES + TOOLS, ("projects", "experience"))
    conf = _clamp(0.3 + 0.2 * min(len(evidence), 3) + (0.1 if content.get("skills") else 0))
    why = f"{len(langs)} ngôn ngữ, {len(tools)} công cụ; dùng thực tế trong {len(applied_fields)} dự án/kinh nghiệm."
    return frac, evidence, why, conf


def _projects(
    content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
) -> tuple[float, list[tuple[str, str]], str, float]:
    projects = content.get("projects") or []
    qualities: list[float] = []
    evidence: list[tuple[str, str]] = []
    for i, proj in enumerate(projects):
        desc = proj.get("description") or ""
        q = (
            0.3 * (len(desc) >= 120)
            + 0.15 * (len(desc) >= 300)
            + 0.25 * bool(proj.get("link"))
            + 0.2 * (len(proj.get("tech") or []) >= 2)
            + 0.1 * bool(CONCRETE.search(desc.lower()))
        )
        qualities.append(q)
        key = f"projects.{i}"
        if key in fields and q >= 0.3 and len(evidence) < 3:
            first = sentences(fields[key])
            evidence.append((key, (first[1] if len(first) > 1 else first[0])[:240]))
    top = sorted(qualities, reverse=True)[:3]
    frac = _clamp(sum(top) / 1.6)
    conf = _clamp(0.35 + 0.2 * min(len(evidence), 3))
    return (
        frac,
        evidence,
        f"{len(projects)} dự án; điểm chất lượng trung bình {sum(qualities) / len(qualities):.2f}."
        if qualities
        else "Chưa có dự án nào.",
        conf,
    )


def _keyword_scorer(terms: tuple[str, ...], applied_prefixes: tuple[str, ...]) -> Scorer:
    def score(
        content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
    ) -> tuple[float, list[tuple[str, str]], str, float]:
        text = " ".join(fields.values())
        found = _hits(text, terms)
        applied = [k for k, v in fields.items() if k.startswith(applied_prefixes) and _hits(v, terms)]
        frac = _clamp(0.6 * _clamp(len(found) / 4) + 0.4 * _clamp(len(applied) / 2))
        evidence = _sentence_evidence(fields, terms, applied_prefixes or None)
        conf = _clamp(0.3 + 0.2 * min(len(evidence), 3))
        return (
            frac,
            evidence,
            f"Nhắc tới {len(found)} khái niệm liên quan; áp dụng trong {len(applied)} dự án/kinh nghiệm.",
            conf,
        )

    return score


def _education(
    content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
) -> tuple[float, list[tuple[str, str]], str, float]:
    edus = content.get("education") or []
    if not edus:
        return 0.0, [], "Chưa có thông tin học vấn.", 0.2
    best = 0.0
    best_key = "education.0"
    for i, edu in enumerate(edus):
        base = {"graduated": 0.65, "final_year": 0.6, "student": 0.4}.get(edu.get("status", ""), 0.3)
        major = (edu.get("major") or "").lower() + " " + (edu.get("degree") or "").lower()
        relevance = 0.2 if any(m in major for m in RELEVANT_MAJORS) else 0.0
        gpa = edu.get("gpa")
        gpa_bonus = 0.0
        if gpa is not None:
            scaled = gpa * 2.5 if gpa <= 4.0 else gpa  # nhận cả thang 4 và thang 10
            gpa_bonus = 0.15 if scaled >= 8 else 0.08 if scaled >= 7 else 0.0
        value = base + relevance + gpa_bonus
        if value > best:
            best, best_key = value, f"education.{i}"
    evidence = [(best_key, fields.get(best_key, "")[:240])] if fields.get(best_key) else []
    return _clamp(best), evidence, "Dựa trên trạng thái học tập, mức liên quan của ngành và điểm (nếu có).", 0.7


def _experience(
    content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
) -> tuple[float, list[tuple[str, str]], str, float]:
    exps = content.get("experience") or []
    years = sum(float(e.get("years") or 0) for e in exps)
    relevant = [
        f"experience.{i}"
        for i, e in enumerate(exps)
        if _hits(fields.get(f"experience.{i}", ""), LANGUAGES + TOOLS + AI_TERMS + DATA_TERMS)
    ]
    frac = _clamp(0.6 * _clamp(years / 2) + 0.4 * _clamp(len(relevant) / 2))
    evidence = [(k, fields[k][:240]) for k in relevant[:3]]
    conf = _clamp(0.35 + 0.2 * min(len(evidence), 2) + (0.1 if exps else 0))
    return frac, evidence, f"Tổng {years:g} năm kinh nghiệm, {len(relevant)} vị trí có nội dung kỹ thuật.", conf


def _essay_scorer(key: str, markers: Callable[[str], int]) -> Scorer:
    def score(
        content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
    ) -> tuple[float, list[tuple[str, str]], str, float]:
        field_key = f"essays.{key}"
        text = fields.get(field_key, "")
        n = len(words(text))
        if n == 0:
            return 0.0, [], "Chưa có nội dung.", 0.3
        specific = markers(text)
        generic = sum(1 for g in GENERIC if g in text.lower())
        frac = _clamp(0.45 * _clamp(n / 120) + 0.55 * _clamp(specific / 4) - 0.08 * generic)
        best = max(sentences(text), key=lambda s: markers(s) * 1000 + len(s)) if sentences(text) else text
        evidence = [(field_key, best[:240])]
        conf = _clamp(0.45 + 0.25 * _clamp(n / 150))
        return (
            frac,
            evidence,
            f"{n} từ; {specific} dấu hiệu cụ thể" + (f"; {generic} cụm chung chung." if generic else "."),
            conf,
        )

    return score


def _motivation_markers(text: str) -> int:
    return len(CONCRETE.findall(text.lower())) + len(_hits(text, LANGUAGES + AI_TERMS + DATA_TERMS))


def _method_markers(text: str) -> int:
    lowered = text.lower()
    return sum(1 for m in METHOD if m in lowered)


def _communication(
    content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
) -> tuple[float, list[tuple[str, str]], str, float]:
    text = fields.get("essays.motivation", "") + "\n" + fields.get("essays.problem_solving", "")
    sents = sentences(text)
    if len(sents) < 2:
        return 0.15, [], "Văn bản quá ngắn để đánh giá cách trình bày.", 0.3
    lengths = [len(words(s)) for s in sents]
    avg = sum(lengths) / len(lengths)
    clarity = 1.0 if 8 <= avg <= 28 else 0.6 if 5 <= avg <= 40 else 0.3
    volume = _clamp(len(sents) / 6)
    frac = 0.6 * clarity + 0.4 * volume
    key = "essays.motivation" if fields.get("essays.motivation") else "essays.problem_solving"
    return frac, [(key, sents[0][:240])], f"{len(sents)} câu, trung bình {avg:.0f} từ mỗi câu.", 0.55


def _custom(
    content: dict[str, Any], fields: dict[str, str], crit: dict[str, Any]
) -> tuple[float, list[tuple[str, str]], str, float]:
    tokens = tuple({w for w in words(f"{crit.get('name', '')} {crit.get('description', '')}") if len(w) >= 4})
    if not tokens:
        return 0.0, [], "Tiêu chí tuỳ chỉnh chưa có từ khoá mô tả để đối chiếu.", 0.2
    text = " ".join(fields.values())
    found = _hits(text, tokens)
    frac = _clamp(len(found) / 3)
    evidence = _sentence_evidence(fields, tokens, None, limit=2)
    return frac, evidence, f"Khớp {len(found)}/{len(tokens)} từ khoá của tiêu chí.", _clamp(0.25 + 0.2 * len(evidence))


SCORERS: dict[str, Scorer] = {
    "programming": _programming,
    "projects": _projects,
    "ai_ml": _keyword_scorer(AI_TERMS, ("projects", "experience")),
    "data": _keyword_scorer(DATA_TERMS, ("projects", "experience")),
    "education": _education,
    "experience": _experience,
    "motivation": _essay_scorer("motivation", _motivation_markers),
    "problem_solving": _essay_scorer("problem_solving", _method_markers),
    "communication": _communication,
    "custom": _custom,
}


def screen_batch(
    contents: list[str], criteria: list[dict[str, Any]], thresholds: dict[str, float]
) -> list[ScreeningResult]:
    """Chấm một lô hồ sơ (nội dung dạng chuỗi JSON); hàm cấp module để chạy trong tiến trình con (ProcessPoolExecutor).

    Nhận JSON thay vì dict để việc giải mã cũng diễn ra ở tiến trình con, không dồn lên tiến trình API.
    """
    engine = HeuristicEngine()
    return [engine.screen_sync(json.loads(c), criteria, thresholds) for c in contents]


class HeuristicEngine:
    name = "heuristic"

    async def screen(
        self, content: dict[str, Any], criteria: list[dict[str, Any]], thresholds: dict[str, float]
    ) -> ScreeningResult:
        return self.screen_sync(content, criteria, thresholds)

    def screen_sync(
        self, content: dict[str, Any], criteria: list[dict[str, Any]], thresholds: dict[str, float]
    ) -> ScreeningResult:
        fields = build_fields(content)
        total_chars = sum(len(v) for v in fields.values())
        results: list[CriterionResult] = []
        dropped_total = 0
        for crit in criteria:
            scorer = SCORERS.get(crit.get("kind", "custom"), _custom)
            frac, raw_evidence, why, conf = scorer(content, fields, crit)
            evidence, dropped = verify_evidence(fields, raw_evidence)
            dropped_total += dropped
            if frac < 0.12 and total_chars >= 150:
                # Đã đọc đủ nội dung mà không thấy tín hiệu: khá chắc là tiêu chí này thực sự yếu.
                conf = max(conf, 0.55)
            if dropped and not evidence:
                conf = min(conf, 0.3)
            score = round(_clamp(frac) * crit["max"] * 2) / 2  # làm tròn theo nấc 0,5 như người chấm
            results.append(
                CriterionResult(
                    id=crit["id"],
                    score=min(score, crit["max"]),
                    max=crit["max"],
                    evidence=evidence,
                    rationale=why,
                    confidence=round(conf, 3),
                )
            )

        flags = injection_flags(fields)
        if total_chars < 400:
            flags.append(
                {
                    "source": "ai",
                    "rule": "sparse_content",
                    "label": "Hồ sơ rất ngắn, thiếu dữ liệu để đánh giá chắc chắn",
                    "severity": "warning",
                }
            )
        skills = content.get("skills") or []
        if len(skills) >= 5 and not (content.get("projects") or content.get("experience")):
            flags.append(
                {
                    "source": "ai",
                    "rule": "claim_without_evidence",
                    "label": "Liệt kê nhiều kỹ năng nhưng chưa có dự án hay kinh nghiệm minh chứng",
                    "severity": "warning",
                }
            )

        total = weighted_total(criteria, results)
        confidence = weighted_confidence(criteria, results)
        if any(f["rule"] == "injection_suspected" for f in flags):
            confidence = min(confidence, 0.4)  # đẩy sang nhóm "cần xem" thay vì tin điểm
        tier, attention = decide_tier(total, confidence, flags, thresholds)
        best = max(results, key=lambda r: r.score / r.max if r.max else 0, default=None)
        names = {c["id"]: c.get("name", c["id"]) for c in criteria}
        summary = (
            f"Tiêu chí mạnh nhất: {names.get(best.id, best.id)} ({best.score:g}/{best.max:g})."
            if best and best.score
            else "Chưa thấy điểm mạnh rõ rệt từ nội dung hồ sơ."
        )
        return ScreeningResult(
            engine=self.name,
            model=None,
            prompt_version=PROMPT_VERSION,
            criteria=results,
            total_score=total,
            confidence=confidence,
            tier=tier,
            needs_attention=attention,
            flags=flags,
            summary=summary,
            input_fields=sorted(fields),
            dropped_quotes=dropped_total,
        )
