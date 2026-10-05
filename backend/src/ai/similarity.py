"""Phát hiện văn bản bị sao chép giữa các hồ sơ trong cùng đợt (gian lận, mẫu bài luận dùng chung).

Dùng shingle 5 từ và chỉ mục đảo: chỉ so các cặp thật sự có chung shingle nên chịu được hàng nghìn hồ sơ.
Chỉ tạo cờ cảnh báo để người xem xét; không kết luận và không tự loại.
"""

import uuid
from collections import defaultdict
from typing import Any

from src.ai.text import words

SHINGLE = 5
MIN_WORDS = 40
THRESHOLD = 0.6


def shingles(text: str) -> set[int]:
    tokens = words(text)
    if len(tokens) < MIN_WORDS:
        return set()
    return {hash(tuple(tokens[i : i + SHINGLE])) for i in range(len(tokens) - SHINGLE + 1)}


def essay_text(content: dict[str, Any]) -> str:
    essays = content.get("essays") or {}
    return f"{essays.get('motivation', '')}\n{essays.get('problem_solving', '')}"


def find_duplicates(
    contents: dict[uuid.UUID, dict[str, Any]], threshold: float = THRESHOLD
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Trả về {application_id: [cờ]} cho các hồ sơ có bài luận giống hồ sơ khác từ `threshold` (Jaccard) trở lên."""
    sets = {app_id: shingles(essay_text(c)) for app_id, c in contents.items()}
    index: dict[int, list[uuid.UUID]] = defaultdict(list)
    for app_id, s in sets.items():
        for sh in s:
            index[sh].append(app_id)

    shared: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for owners in index.values():
        if len(owners) < 2 or len(owners) > 50:  # cụm quá phổ biến (câu mẫu) bỏ qua để tránh nổ tổ hợp
            continue
        for i, a in enumerate(owners):
            for b in owners[i + 1 :]:
                shared[(a, b) if str(a) < str(b) else (b, a)] += 1

    flags: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for (a, b), count in shared.items():
        union = len(sets[a]) + len(sets[b]) - count
        similarity = count / union if union else 0.0
        if similarity >= threshold:
            for me, other in ((a, b), (b, a)):
                flags[me].append(
                    {
                        "source": "ai",
                        "rule": "duplicate_text",
                        "label": f"Bài luận giống {similarity:.0%} với một hồ sơ khác trong đợt này",
                        "severity": "warning",
                        "similarity": round(similarity, 3),
                        "other_application": str(other),
                    }
                )
    return flags
