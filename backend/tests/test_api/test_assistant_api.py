"""API trợ lý hỏi đáp: phân quyền tài liệu, nhật ký câu hỏi, phản hồi, thống kê khoảng trống, giới hạn tốc độ, chi phí LLM."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from src.ai import assistant as ai
from src.ai.providers import FakeProvider

GAMMA = "gamma"
ASK = "/api/v1/assistant/ask"


async def _ask(client: AsyncClient, question: str) -> dict[str, Any]:
    res = await client.post(ASK, json={"question": question})
    assert res.status_code == 200, res.text
    data: dict[str, Any] = res.json()
    return data


async def test_applicant_gets_cited_answer_and_unanswerable_question_is_declined(
    login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    applicant = await login_as("applicant", GAMMA)
    ok = await _ask(applicant, "Phụ cấp hàng tháng là bao nhiêu?")
    assert ok["answered"] and "tám triệu" in ok["answer"] and ok["engine"] == "extractive"
    assert ok["citations"] and ok["citations"][0]["title"].startswith("[Minh hoạ]")
    assert all(f"[{c['n']}]" in ok["answer"] for c in ok["citations"])

    declined = await _ask(applicant, "Thời tiết Hà Nội hôm nay thế nào?")
    assert not declined["answered"] and declined["citations"] == []


async def test_internal_documents_are_visible_to_staff_only(
    login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    question = "Quyết định ngoại lệ khi khác gợi ý được ghi nhận thế nào?"
    staff = await _ask(await login_as("reviewer", GAMMA), question)
    assert staff["answered"] and "ngoại lệ" in staff["answer"]
    applicant = await _ask(await login_as("applicant", GAMMA), question)
    assert not applicant["answered"]  # không lộ tài liệu nội bộ cho ứng viên


async def test_requires_login_and_validates_input(
    client: AsyncClient, login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    assert (await client.post(ASK, json={"question": "xin chào"}, headers={"X-Organization": GAMMA})).status_code == 401
    applicant = await login_as("applicant", GAMMA)
    assert (await applicant.post(ASK, json={"question": "  a "})).status_code == 422
    assert (await applicant.post(ASK, json={"question": "x" * 501})).status_code == 422
    assert (await applicant.post(ASK, json={})).status_code == 422


async def test_questions_are_logged_and_owner_can_rate_the_answer(
    login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    applicant = await login_as("applicant", GAMMA)
    result = await _ask(applicant, "Phụ cấp hàng tháng là bao nhiêu?")
    rated = await applicant.post(f"/api/v1/assistant/queries/{result['id']}/feedback", json={"helpful": True})
    assert rated.status_code == 204
    # người khác không đánh giá được câu hỏi của bạn
    other = await login_as("reviewer", GAMMA)
    assert (
        await other.post(f"/api/v1/assistant/queries/{result['id']}/feedback", json={"helpful": False})
    ).status_code == 404


async def test_admin_sees_documentation_gaps_from_unanswered_questions(
    login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    applicant = await login_as("applicant", GAMMA)
    gap = "Chương trình có hỗ trợ ký túc xá cho học viên ở xa không?"
    for _ in range(2):
        await _ask(applicant, gap)
    admin = await login_as("admin", GAMMA)
    res = await admin.get("/api/v1/admin/assistant/insights")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] >= 3 and 0 <= data["answer_rate"] <= 1
    top = {row["question"]: row["count"] for row in data["unanswered"]}
    assert top.get(gap, 0) >= 2  # câu lặp lại được gộp và xếp lên đầu để biết cần bổ sung tài liệu nào
    assert (await (await login_as("reviewer", GAMMA)).get("/api/v1/admin/assistant/insights")).status_code == 403


async def test_rate_limit_protects_against_scraping_and_cost_abuse(
    login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    mentor = await login_as("mentor", GAMMA)
    codes = [(await mentor.post(ASK, json={"question": f"Phụ cấp bao nhiêu {i}?"})).status_code for i in range(22)]
    assert (
        codes[:20] == [200] * 20
        and codes[20] == 429
        and "retry-after" in (await mentor.post(ASK, json={"question": "lại"})).headers
    )


async def test_llm_usage_is_recorded_with_cost_and_declined_answers_are_still_safe(
    app_instance: FastAPI, login_as: Callable[..., Any], demo_env: dict[str, str]
) -> None:
    provider = FakeProvider(
        lambda system, user: {
            "answerable": True,
            "answer": "Học viên nhận tám triệu đồng mỗi tháng.",
            "citations": [1],
        },
        model="claude-haiku-4-5-20251001",
    )
    app_instance.state.assistant_answerer = ai.LLMAnswerer(provider)
    try:
        applicant = await login_as("applicant", GAMMA)
        res = await _ask(applicant, "Phụ cấp hàng tháng là bao nhiêu?")
        assert res["answered"] and res["engine"].startswith("llm") and res["citations"]
        admin = await login_as("admin", GAMMA)
        usage = (await admin.get("/api/v1/admin/costs/ai?group=feature")).json()
        assistant_rows = [r for r in usage if r["key"] == "assistant"]
        assert assistant_rows and assistant_rows[0]["calls"] >= 1 and assistant_rows[0]["cost_usd"] > 0
        # mô hình bịa số: bị từ chối thay vì trả lời sai
        provider2 = FakeProvider(
            lambda system, user: {"answerable": True, "answer": "Phụ cấp là 20.000.000 đồng.", "citations": [1]}
        )
        app_instance.state.assistant_answerer = ai.LLMAnswerer(provider2)
        bad = await _ask(applicant, "Phụ cấp hàng tháng là bao nhiêu?")
        assert not bad["answered"]
    finally:
        app_instance.state.assistant_answerer = None
