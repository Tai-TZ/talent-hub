"""Tiện ích văn bản dùng chung cho các động cơ sàng lọc: dựng trường văn bản, tách câu, tìm trích dẫn."""

import bisect
import re
import unicodedata
from typing import Any

SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
WORD = re.compile(r"\w+", re.UNICODE)
NON_SPACE = re.compile(r"\S+")


def build_fields(content: dict[str, Any]) -> dict[str, str]:
    """Phẳng hoá `content` thành {khoá_trường: văn_bản}. Khoá dùng để trích dẫn bằng chứng.

    Chỉ nhận `content` (năng lực). `profile` (danh tính, giới tính, ngày sinh...) không bao giờ vào đây.
    """
    fields: dict[str, str] = {}
    essays = content.get("essays") or {}
    for key in ("motivation", "problem_solving"):
        if essays.get(key):
            fields[f"essays.{key}"] = str(essays[key])
    for i, edu in enumerate(content.get("education") or []):
        text = " ".join(str(edu.get(k, "")) for k in ("degree", "major", "school") if edu.get(k))
        status = edu.get("status")
        gpa = f", GPA {edu['gpa']}" if edu.get("gpa") is not None else ""
        fields[f"education.{i}"] = f"{text} ({status}{gpa})".strip()
    for i, exp in enumerate(content.get("experience") or []):
        fields[f"experience.{i}"] = " — ".join(
            str(exp.get(k, "")) for k in ("role", "org", "description") if exp.get(k)
        )
    for i, proj in enumerate(content.get("projects") or []):
        tech = f" Công nghệ: {', '.join(proj['tech'])}." if proj.get("tech") else ""
        fields[f"projects.{i}"] = f"{proj.get('title', '')}. {proj.get('description', '')}{tech}".strip()
    if content.get("skills"):
        fields["skills"] = ", ".join(str(s) for s in content["skills"])
    if content.get("cv_text"):
        fields["cv_text"] = str(content["cv_text"])
    return fields


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(norm(text)) if s.strip()]


def words(text: str) -> list[str]:
    return WORD.findall(norm(text).lower())


def _find_collapsed(text: str, pieces: list[str]) -> tuple[int, int] | None:
    """Đường nhanh của `find_span`: gộp mỗi cụm khoảng trắng thành một dấu cách, hạ chữ thường rồi tìm chuỗi con.

    Tương đương regex `p1\\s+p2...` với IGNORECASE (vị trí khớp đầu tiên) khi `lower()` giữ nguyên độ dài; nếu không
    thì trả None để dùng regex. Tránh biên dịch một regex mới cho mỗi trích dẫn (tốn kém khi chấm hàng chục nghìn hồ sơ).
    """
    lowered = text.lower()
    needle = " ".join(pieces)
    lowered_needle = needle.lower()
    if len(lowered) != len(text) or len(lowered_needle) != len(needle):
        return None
    collapsed = " ".join(lowered.split())
    at = collapsed.find(lowered_needle)
    if at < 0:
        return None
    if collapsed == lowered:  # văn bản vốn không có khoảng trắng thừa: vị trí giữ nguyên, khỏi dựng bảng ánh xạ
        return at, at + len(needle)
    # `collapsed` là các token (\S+, cùng định nghĩa khoảng trắng với str.split) nối bằng một dấu cách.
    tokens = [(m.start(), m.group()) for m in NON_SPACE.finditer(lowered)]
    starts: list[int] = []
    pos = 0
    for _, token in tokens:
        starts.append(pos)
        pos += len(token) + 1

    def original(i: int) -> int:
        k = bisect.bisect_right(starts, i) - 1
        return tokens[k][0] + i - starts[k]

    return original(at), original(at + len(needle) - 1) + 1


def find_span(text: str, quote: str) -> tuple[int, int] | None:
    """Tìm `quote` trong `text` bỏ qua khác biệt khoảng trắng và hoa/thường; trả (bắt đầu, kết thúc) hoặc None."""
    pieces = norm(quote).split()
    if not pieces:
        return None
    text = norm(text)
    fast = _find_collapsed(text, pieces)
    if fast is not None:
        return fast
    match = re.search(r"\s+".join(re.escape(p) for p in pieces), text, flags=re.IGNORECASE)
    return (match.start(), match.end()) if match else None
