"""Trường hợp biên và đầu vào xấu: không được 500, không được lộ dữ liệu, trạng thái luôn nhất quán."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from tests.helpers import (
    CRITERIA,
    FULL_SCORES,
    create_open_intake,
    good_content,
    good_profile,
    submit_application,
)

pytestmark = pytest.mark.asyncio


async def _new_draft(login_as: Any, who: str = "applicant") -> tuple[Any, Any, dict[str, Any]]:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    applicant = await login_as(who)
    created = await applicant.post("/api/v1/applications", json={"intake_id": intake["id"]})
    assert created.status_code == 201, created.text
    return admin, applicant, {"intake": intake, "app": created.json()}


async def test_one_application_per_person_per_intake_and_creation_is_idempotent(login_as: Any) -> None:
    _, applicant, ctx = await _new_draft(login_as)
    again = await applicant.post("/api/v1/applications", json={"intake_id": ctx["intake"]["id"]})
    assert again.status_code == 201 and again.json()["id"] == ctx["app"]["id"]  # không tạo bản ghi thứ hai


async def test_cannot_apply_to_unpublished_or_closed_intake_and_unknown_ids_are_clean_errors(login_as: Any) -> None:
    admin = await login_as("admin")
    applicant = await login_as("applicant2")
    intake = await create_open_intake(admin)
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/close")).status_code == 200
    closed = await applicant.post("/api/v1/applications", json={"intake_id": intake["id"]})
    assert closed.status_code == 422 and "đóng" in closed.json()["detail"]
    ghost = await applicant.post("/api/v1/applications", json={"intake_id": "01a10a21-0000-7000-8000-000000000000"})
    assert ghost.status_code == 404
    assert (await applicant.post("/api/v1/applications", json={"intake_id": "khong-phai-uuid"})).status_code == 422
    assert (await applicant.get("/api/v1/applications/khong-phai-uuid")).status_code == 422


async def test_submit_and_edit_after_deadline_are_rejected_not_silently_accepted(login_as: Any) -> None:
    admin, applicant, ctx = await _new_draft(login_as, "applicant3")
    app_id = ctx["app"]["id"]
    saved = await applicant.patch(
        f"/api/v1/applications/{app_id}", json={"profile": good_profile(), "content": good_content()}
    )
    assert saved.status_code == 200
    assert (await admin.post(f"/api/v1/intakes/{ctx['intake']['id']}/close")).status_code == 200
    late = await applicant.post(f"/api/v1/applications/{app_id}/submit", json={"consent": True})
    assert late.status_code == 409 and "đóng" in late.json()["detail"]
    edit = await applicant.patch(f"/api/v1/applications/{app_id}", json={"content": good_content()})
    assert edit.status_code == 409


async def test_double_submit_and_double_withdraw_leave_one_consistent_outcome(login_as: Any) -> None:
    admin, applicant, ctx = await _new_draft(login_as, "applicant2")
    app_id = ctx["app"]["id"]
    await applicant.patch(f"/api/v1/applications/{app_id}", json={"profile": good_profile(), "content": good_content()})
    results = await asyncio.gather(
        *[applicant.post(f"/api/v1/applications/{app_id}/submit", json={"consent": True}) for _ in range(5)]
    )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1 and all(c in (200, 409, 422) for c in codes), codes  # đúng một lần nộp thành công
    timeline = (await applicant.get(f"/api/v1/applications/{app_id}/timeline")).json()
    assert [e["type"] for e in timeline].count("application.submitted") == 1

    first = await applicant.post(f"/api/v1/applications/{app_id}/withdraw", json={"reason": "đổi ý"})
    second = await applicant.post(f"/api/v1/applications/{app_id}/withdraw", json={})
    assert first.status_code == 200 and second.status_code in (409, 422)
    # hồ sơ đã rút không còn xuất hiện để xét nhưng vẫn truy xuất được ở phía chủ hồ sơ
    assert (await applicant.get(f"/api/v1/applications/{app_id}")).json()["status"] == "WITHDRAWN"


async def test_other_applicants_cannot_read_or_change_my_application(login_as: Any) -> None:
    admin, owner, ctx = await _new_draft(login_as, "applicant")
    app_id = ctx["app"]["id"]
    stranger = await login_as("applicant2")
    for method, url, body in [
        ("get", f"/api/v1/applications/{app_id}", None),
        ("patch", f"/api/v1/applications/{app_id}", {"content": {}}),
        ("post", f"/api/v1/applications/{app_id}/submit", {"consent": True}),
        ("post", f"/api/v1/applications/{app_id}/withdraw", {}),
    ]:
        res = await getattr(stranger, method)(url, **({"json": body} if body is not None else {}))
        assert res.status_code == 404, (method, url, res.status_code)  # 404 chứ không phải 403: không lộ sự tồn tại
    assert (await stranger.get(f"/api/v1/applications/{app_id}/timeline")).status_code == 404
    assert (await stranger.get(f"/api/v1/staff/applications/{app_id}")).status_code == 403


async def test_mass_assignment_cannot_set_status_or_owner(login_as: Any) -> None:
    _, applicant, ctx = await _new_draft(login_as)
    app_id = ctx["app"]["id"]
    res = await applicant.patch(
        f"/api/v1/applications/{app_id}",
        json={
            "profile": good_profile(),
            "status": "ACCEPTED",
            "applicant_membership_id": "x",
            "current_round": "aptitude",
        },
    )
    assert res.status_code == 200
    view = (await applicant.get(f"/api/v1/applications/{app_id}")).json()
    assert view["status"] == "DRAFT" and view["current_round"] is None
    # nội dung có trường lạ bị từ chối chứ không lưu vào JSON
    bad = await applicant.patch(
        f"/api/v1/applications/{app_id}", json={"content": {**good_content(), "is_admin": True}}
    )
    assert bad.status_code == 422


async def test_oversized_and_hostile_content_is_rejected_or_neutralised(login_as: Any) -> None:
    _, applicant, ctx = await _new_draft(login_as)
    app_id = ctx["app"]["id"]
    url = f"/api/v1/applications/{app_id}"
    too_many = {**good_content(), "skills": [f"kỹ năng {i}" for i in range(41)]}
    assert (await applicant.patch(url, json={"content": too_many})).status_code == 422
    long_essay = {**good_content(), "essays": {"motivation": "a" * 4001, "problem_solving": ""}}
    assert (await applicant.patch(url, json={"content": long_essay})).status_code == 422
    for link in ("javascript:alert(1)", "data:text/html,<script>1</script>", "ftp://x.example/file", "//evil.example"):
        res = await applicant.patch(url, json={"content": {**good_content(), "links": {"github": link}}})
        assert res.status_code == 422, link
    # ký tự điều khiển bị loại; HTML được lưu như văn bản thuần (giao diện luôn escape)
    xss = {
        **good_content(),
        "essays": {"motivation": "<img src=x onerror=alert(1)>\x00\x07 xin chào", "problem_solving": ""},
    }
    saved = await applicant.patch(url, json={"content": xss})
    assert saved.status_code == 200
    stored = saved.json()["content"]["essays"]["motivation"]
    assert "\x00" not in stored and "\x07" not in stored and stored.startswith("<img")


async def test_invalid_cursors_and_filters_are_client_errors_never_500(login_as: Any) -> None:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    reviewer = await login_as("reviewer")
    for cursor in ("@@@", "abc", "MTIz", "!!!!====", "x" * 500):
        res = await reviewer.get(f"/api/v1/staff/applications?intake_id={intake['id']}&cursor={cursor}")
        assert res.status_code in (400, 422), (cursor, res.status_code)
    assert (await reviewer.get(f"/api/v1/staff/applications?intake_id={intake['id']}&status=KHONG_CO")).status_code in (
        200,
        422,
    )
    assert (await reviewer.get(f"/api/v1/staff/applications?intake_id={intake['id']}&q=%25_%25")).status_code == 200
    assert (await admin.get("/api/v1/audit-logs?cursor=@@@")).status_code in (400, 422)


async def test_search_wildcards_are_treated_as_literal_text(login_as: Any) -> None:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    applicant = await login_as("applicant")
    await submit_application(applicant, intake["id"])
    reviewer = await login_as("reviewer")
    # "%" không được hiểu là ký tự đại diện: tìm "%" không khớp mọi hồ sơ
    res = (await reviewer.get(f"/api/v1/staff/applications?intake_id={intake['id']}&q=%25")).json()
    assert res["total"] == 0


async def test_intake_dates_without_timezone_are_client_errors_not_500(login_as: Any) -> None:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    naive = await admin.patch(f"/api/v1/intakes/{intake['id']}", json={"closes_at": "2030-12-01T00:00:00"})
    assert naive.status_code == 422, naive.text
    aware = await admin.patch(f"/api/v1/intakes/{intake['id']}", json={"closes_at": "2030-12-01T00:00:00+07:00"})
    assert aware.status_code == 200, aware.text
    program = (await admin.post("/api/v1/programs", json={"code": "tz1", "name_vi": "P"})).json()
    mixed = await admin.post(
        "/api/v1/intakes",
        json={
            "program_id": program["id"],
            "name": "Múi giờ lẫn lộn",
            "opens_at": "2030-01-01T00:00:00",
            "closes_at": "2030-02-01T00:00:00Z",
            "quota": 3,
            "rounds": [{"key": "r1", "label": "Vòng 1", "type": "review"}],
        },
    )
    assert mixed.status_code == 422, mixed.text


@pytest.mark.parametrize(
    "config",
    [
        {"thresholds": {"invite": "high"}},
        {"thresholds": [1]},
        {"thresholds": {"invite": 150}},
        {"thresholds": {"min_confidence": 2}},
        {"thresholds": {"invite": 40, "decline": 60}},
        {"thresholds": {"unknown": 1}},
        {"other": True},
    ],
)
async def test_bad_triage_config_is_rejected_before_it_can_break_triage(login_as: Any, config: dict[str, Any]) -> None:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    res = await admin.patch(f"/api/v1/intakes/{intake['id']}", json={"triage_config": config})
    assert res.status_code == 422, res.text
    assert (await admin.get(f"/api/v1/intakes/{intake['id']}/triage")).status_code == 200


async def test_partial_triage_thresholds_keep_engine_defaults(login_as: Any) -> None:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    res = await admin.patch(f"/api/v1/intakes/{intake['id']}", json={"triage_config": {"thresholds": {"invite": 75}}})
    assert res.status_code == 200, res.text
    triage = (await admin.get(f"/api/v1/intakes/{intake['id']}/triage")).json()
    assert triage["thresholds"]["invite"] == 75 and triage["thresholds"]["decline"] == 42


async def test_costs_and_settings_reject_non_finite_and_absurd_numbers(login_as: Any) -> None:
    admin = await login_as("admin")
    today = datetime.now(UTC).date().isoformat()
    for amount in ("NaN", "Infinity", "-5", "0", "1e30", "99999999999999999999"):
        res = await admin.post(
            "/api/v1/admin/costs/entries", json={"category": "operations", "amount_vnd": amount, "occurred_on": today}
        )
        assert res.status_code in (422, 400), (amount, res.status_code, res.text[:120])
    for payload in (
        {"usd_vnd_rate": float("nan")},
        {"usd_vnd_rate": -1},
        {"ai_monthly_budget_usd": 10**12},
        {"ai_engine": "gpt"},
    ):
        res = await admin.put(
            "/api/v1/admin/settings",
            content=json.dumps({"values": payload}),
            headers={"content-type": "application/json"},
        )
        assert res.status_code == 422, payload


async def test_decision_edge_cases_conflicts_and_wrong_states(login_as: Any) -> None:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    applicant = await login_as("applicant")
    app = await submit_application(applicant, intake["id"])
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/close")).status_code == 200
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/start")).status_code == 200
    reviewer = await login_as("reviewer")
    base = f"/api/v1/staff/applications/{app['id']}"
    rubric = (await reviewer.get(base)).json()["rubric"]
    assert rubric and len(rubric["criteria"]) == len(CRITERIA)

    # không đề xuất khi chưa đủ người chấm; không chuyển vòng khi chưa chốt điểm
    version = app["version"] + 1
    early = await reviewer.post(
        f"{base}/proposals", json={"version": version, "outcome": "accepted", "reason": "x" * 30}
    )
    assert early.status_code == 409
    assert (await reviewer.post(f"{base}/advance", json={"version": version})).status_code == 409
    assert (
        await reviewer.post(f"{base}/proposals", json={"version": version, "outcome": "khac", "reason": "x" * 30})
    ).status_code in (409, 422)

    scored = await reviewer.put(
        f"{base}/review",
        json={
            "scores": FULL_SCORES,
            "comment": "Hồ sơ tốt, đủ dự án thực tế.",
            "recommendation": "advance",
            "submit": True,
        },
    )
    assert scored.status_code == 200
    # chốt rồi thì không sửa; điểm ngoài thang bị chặn trước khi chốt
    assert (await reviewer.put(f"{base}/review", json={"scores": FULL_SCORES, "submit": False})).status_code == 409
    again = await reviewer.put(f"{base}/review", json={"scores": {"projects": 99}, "submit": False})
    assert again.status_code in (409, 422)

    # rút giữa chừng khi đang chờ duyệt không được (phải chờ quyết định)
    proposed = await reviewer.post(
        f"{base}/proposals",
        json={"version": version, "outcome": "accepted", "reason": "Dự án tốt, đạt các tiêu chí chính của đợt."},
    )
    assert proposed.status_code == 201, proposed.text
    dup = await reviewer.post(
        f"{base}/proposals", json={"version": version + 1, "outcome": "rejected", "reason": "x" * 30}
    )
    assert dup.status_code in (409, 422)  # đã có đề xuất đang chờ
    assert (await applicant.post(f"/api/v1/applications/{app['id']}/withdraw", json={})).status_code in (409, 422)


async def test_responses_never_include_secrets_or_internal_fields(login_as: Any) -> None:
    """Quét các phản hồi chính để chắc không rò rỉ băm mật khẩu, token, khoá nội bộ."""
    admin = await login_as("admin")
    texts = []
    for url in (
        "/api/v1/me",
        "/api/v1/admin/users?limit=100",
        "/api/v1/admin/settings",
        "/api/v1/audit-logs?limit=50",
        "/api/v1/org",
    ):
        texts.append((await admin.get(url)).text)
    blob = " ".join(texts).lower()
    for needle in (
        "password_hash",
        "$argon2",
        "refresh_token",
        "jwt_secret",
        "token_hash",
        "anthropic_api_key",
        "llm_api_key",
        "client_secret",
    ):
        assert needle not in blob, needle
