"""Đánh giá chất lượng trợ lý trên bộ câu hỏi chuẩn (eval/assistant_qa.jsonl).

Chỉ số chính:
- answer_accuracy: câu có đáp án — trả lời, trích đúng tài liệu và chứa đúng sự kiện chính.
- abstain_precision: câu KHÔNG có đáp án — tỉ lệ trợ lý biết từ chối (lỗi nặng nhất là trả lời bừa).
- citation_validity: mọi trích dẫn trỏ tới đoạn có thật trong các nguồn đã truy xuất.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ai.assistant import Answerer, fold
from src.services import assistant as svc
from src.services.tenancy import OrgDb

DATASET = Path(__file__).resolve().parents[3] / "eval" / "assistant_qa.jsonl"
PERMISSIONS = {
    "applicant": frozenset({"assistant.use", "application.read.own"}),
    "staff": frozenset({"assistant.use", "application.read", "kb.manage"}),
}


@dataclass
class Row:
    q: str
    persona: str
    kind: str
    ok: bool
    answered: bool
    detail: str
    answer: str
    ms: float


@dataclass
class Report:
    rows: list[Row] = field(default_factory=list)

    def _rate(self, kind: str) -> float | None:
        subset = [r for r in self.rows if r.kind == kind]
        return round(sum(r.ok for r in subset) / len(subset), 3) if subset else None

    @property
    def answer_accuracy(self) -> float | None:
        return self._rate("answerable")

    @property
    def abstain_precision(self) -> float | None:
        return self._rate("unanswerable")

    @property
    def answered_precision(self) -> float | None:
        """Trong các câu trợ lý ĐÃ trả lời, bao nhiêu câu đúng (câu từ chối không tính). Đo mức \"trả lời bừa\"."""
        answered = [r for r in self.rows if r.answered]
        return round(sum(r.ok for r in answered) / len(answered), 3) if answered else None

    @property
    def p50_ms(self) -> float:
        times = sorted(r.ms for r in self.rows)
        return round(times[len(times) // 2], 1) if times else 0.0

    def failures(self) -> list[Row]:
        return [r for r in self.rows if not r.ok]


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def run_eval(db: OrgDb, answerer: Answerer, dataset: list[dict[str, Any]] | None = None) -> Report:
    report = Report()
    for item in dataset or load_dataset():
        persona = item.get("as", "applicant")
        started = time.perf_counter()
        result = await svc.ask(
            db,
            question=item["q"],
            permissions=PERMISSIONS[persona],
            membership_id=None,
            answerer=answerer,
            persist=False,
        )
        ms = (time.perf_counter() - started) * 1000
        answered = result["answered"]
        if item["kind"] == "answerable":
            text = fold(result["answer"])
            cited_titles = " ".join(fold(c["title"] + " " + c["heading"]) for c in result["citations"])
            # "a|b" nghĩa là chấp nhận một trong các phương án (nhiều tài liệu cùng nói đúng một ý).
            has_doc = any(fold(d) in cited_titles for d in item["doc"].split("|"))
            has_facts = all(any(fold(alt) in text for alt in f.split("|")) for f in item["facts"])
            ok = answered and has_doc and has_facts
            detail = "" if ok else f"answered={answered} doc={has_doc} facts={has_facts}"
        else:
            ok = not answered
            detail = "" if ok else "trả lời bừa câu không có trong tài liệu"
        report.rows.append(Row(item["q"], persona, item["kind"], ok, answered, detail, result["answer"], ms))
    return report


def to_markdown(report: Report, engine: str) -> str:
    lines = [
        f"# Kết quả đánh giá trợ lý hỏi đáp ({engine})",
        "",
        f"- Câu có đáp án: **{report.answer_accuracy:.0%}** trả lời đúng tài liệu và đúng sự kiện chính"
        if report.answer_accuracy is not None
        else "- Không có câu có đáp án",
        f"- Câu không có đáp án: **{report.abstain_precision:.0%}** được từ chối đúng"
        if report.abstain_precision is not None
        else "- Không có câu không đáp án",
        f"- Trong các câu đã trả lời: **{report.answered_precision:.0%}** đúng (đo mức trả lời bừa)"
        if report.answered_precision is not None
        else "- Chưa trả lời câu nào",
        f"- Thời gian trả lời trung vị (gồm truy xuất): {report.p50_ms} ms",
        "",
        "| Loại | Người hỏi | Câu hỏi | Kết quả | Ghi chú |",
        "|---|---|---|---|---|",
    ]
    for r in report.rows:
        lines.append(
            f"| {'có đáp án' if r.kind == 'answerable' else 'không có'} | {r.persona} | {r.q} | {'đạt' if r.ok else 'trượt'} | {r.detail} |"
        )
    return "\n".join(lines) + "\n"
