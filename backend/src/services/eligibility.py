"""Luật đủ điều kiện do từng đợt tuyển cấu hình. Chỉ tạo cờ cảnh báo; không bao giờ tự loại hồ sơ."""

from typing import Any

from src.schemas.application import Content


def evaluate(rules: list[dict[str, Any]], content: Content) -> list[dict[str, Any]]:
    """Trả về danh sách cờ cho các luật KHÔNG đạt (để người xét duyệt thấy và quyết định)."""
    flags: list[dict[str, Any]] = []
    for rule in rules:
        passed = _check(rule, content)
        if not passed:
            flags.append({"source": "eligibility", "rule": rule["id"], "label": rule["label"], "severity": "warning"})
    return flags


def _check(rule: dict[str, Any], content: Content) -> bool:
    kind = rule["type"]
    if kind == "education_status_in":
        allowed = set(rule.get("values", []))
        return any(e.status in allowed for e in content.education)
    if kind == "min_skills":
        return len(content.skills) >= int(rule.get("value") or 0)
    if kind == "min_projects":
        return len(content.projects) >= int(rule.get("value") or 0)
    if kind == "min_essay_chars":
        needed = int(rule.get("value") or 0)
        return len(content.essays.motivation) + len(content.essays.problem_solving) >= needed
    return True  # luật lạ: không chặn
