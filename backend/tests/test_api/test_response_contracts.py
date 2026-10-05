"""Quét hợp đồng: mọi endpoint đọc phải trả đúng cấu trúc đã khai báo (response_model) trên dữ liệu thật.

httpx ASGITransport ném lại ngoại lệ của ứng dụng, nên sai lệch giữa dữ liệu và mô hình sẽ làm test đỏ ngay
(ResponseValidationError) thay vì lặng lẽ trả 500 cho giao diện.
"""

import pytest

GAMMA = "gamma"


async def _ok(client, url: str):  # type: ignore[no-untyped-def]
    res = await client.get(url)
    assert res.status_code == 200, f"{url}: {res.status_code} {res.text[:300]}"
    return res.json()


async def test_admin_and_catalog_endpoints_match_their_models(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", GAMMA)
    for url in (
        "/api/v1/org",
        "/api/v1/me",
        "/api/v1/programs",
        "/api/v1/tracks",
        "/api/v1/partners",
        "/api/v1/notifications",
        "/api/v1/audit-logs",
        "/api/v1/admin/overview",
        "/api/v1/admin/settings",
        "/api/v1/admin/users",
        "/api/v1/admin/users?status=active&role=admin",
        "/api/v1/admin/documents",
        "/api/v1/admin/costs/summary",
        "/api/v1/admin/costs/entries",
        "/api/v1/admin/costs/ai?group=feature",
        "/api/v1/admin/costs/ai?group=day",
        "/api/v1/admin/costs/ai?group=model",
    ):
        await _ok(admin, url)
    trainer = await login_as("training_manager", GAMMA)
    await _ok(trainer, "/api/v1/mentor/learners")
    summary = await _ok(admin, "/api/v1/admin/costs/summary")
    assert {"month", "total", "by_category"} <= set(summary["timeline"][0]) if summary["timeline"] else True


async def test_admissions_and_cohort_endpoints_match_their_models(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", GAMMA)
    programs = await _ok(admin, "/api/v1/programs")
    program = next(p for p in programs if p["code"] == "ai-talent")
    cohorts = {c["code"]: c["id"] for c in program["cohorts"]}
    intakes = {i["name"]: i for i in await _ok(admin, "/api/v1/intakes")}
    done = intakes["[Minh hoạ] Đợt tuyển khoá 1"]
    current = intakes[next(n for n in intakes if intakes[n]["id"] == demo_env["current_intake"])]
    assert current["status"] == "open"

    for intake in (done, current):
        iid = intake["id"]
        await _ok(admin, f"/api/v1/intakes/{iid}")
        await _ok(admin, f"/api/v1/intakes/{iid}/rubrics")
        await _ok(admin, f"/api/v1/analytics/funnel?intake_id={iid}")
        await _ok(admin, f"/api/v1/analytics/fairness?intake_id={iid}")
        queue = await _ok(admin, f"/api/v1/staff/applications?intake_id={iid}&limit=5")
        if queue["items"]:
            first = queue["items"][0]["id"]
            await _ok(admin, f"/api/v1/staff/applications/{first}")
            await _ok(admin, f"/api/v1/applications/{first}/timeline")

    reviewer = await login_as("reviewer", GAMMA)
    await _ok(reviewer, f"/api/v1/staff/applications?intake_id={current['id']}&limit=5")
    approver = await login_as("approver", GAMMA)
    await _ok(approver, "/api/v1/staff/approvals")
    await _ok(approver, f"/api/v1/staff/approvals?intake_id={done['id']}")

    for cohort_id in cohorts.values():
        await _ok(admin, f"/api/v1/cohorts/{cohort_id}/overview")
        await _ok(admin, f"/api/v1/cohorts/{cohort_id}/enrollments?limit=5")
        await _ok(admin, f"/api/v1/cohorts/{cohort_id}/qualification")
        await _ok(admin, f"/api/v1/cohorts/{cohort_id}/stipends")
        await _ok(admin, f"/api/v1/cohorts/{cohort_id}/composer/runs")

    # học viên đã có nhánh: ma trận năng lực khớp mô hình
    page = await _ok(admin, f"/api/v1/cohorts/{cohorts['K1']}/enrollments?limit=50")
    learner = next((e for e in page["items"] if e["track_id"]), None)
    assert learner is not None
    trainer = await login_as("training_manager", GAMMA)
    comp = await _ok(trainer, f"/api/v1/enrollments/{learner['id']}/competencies")
    assert comp["matrix"], "nhánh phải có năng lực mục tiêu"


async def test_applicant_endpoints_match_their_models(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    applicant = await login_as("applicant", GAMMA)
    intakes = await _ok(applicant, "/api/v1/intakes")
    assert all(i["status"] == "open" for i in intakes)  # ứng viên chỉ thấy đợt đang mở
    mine = await _ok(applicant, "/api/v1/applications/mine")
    assert isinstance(mine, list)


@pytest.mark.parametrize("group", ["feature", "model", "day"])
async def test_ai_usage_groups_return_string_keys(login_as, demo_env, group: str) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", GAMMA)
    rows = await _ok(admin, f"/api/v1/admin/costs/ai?group={group}")
    assert all(isinstance(r["key"], str) for r in rows)
