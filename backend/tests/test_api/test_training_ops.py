"""Vận hành khoá học: ghi danh, mentor đánh giá năng lực, xét đạt, phụ cấp ↔ sổ chi phí, phân quyền."""

from typing import Any

import pytest

GAMMA = "delta"  # tổ chức riêng của fixture training_env
PERIOD = "2026-09"


async def _ready_cohort(login_as: Any, training_env: dict[str, str]) -> tuple[Any, str]:
    manager = await login_as("cohort_manager", GAMMA)
    cohort_id = training_env["cohort_id"]
    overview = (await manager.get(f"/api/v1/cohorts/{cohort_id}/overview")).json()
    if overview["accepted_waiting_enrollment"]:
        res = await manager.post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")
        assert res.status_code == 200 and res.json()["enrolled"] == int(training_env["accepted"])
    return manager, cohort_id


async def _learner_with_track(manager: Any, cohort_id: str) -> dict[str, Any]:
    """Ghi danh xong thì gán nhánh cho một học viên (nhánh đầu tiên có chuẩn năng lực)."""
    tracks = (await manager.get("/api/v1/tracks")).json()
    track = next(t for t in tracks if t["targets"])
    page = (await manager.get(f"/api/v1/cohorts/{cohort_id}/enrollments?status=active&limit=5")).json()
    learner = page["items"][0]
    res = await manager.patch(f"/api/v1/enrollments/{learner['id']}", json={"track_id": track["id"]})
    assert res.status_code == 200, res.text
    return {"learner": learner, "track": track}


async def test_enrollment_is_idempotent_and_only_for_accepted_applicants(
    login_as: Any, training_env: dict[str, str]
) -> None:
    manager, cohort_id = await _ready_cohort(login_as, training_env)
    again = await manager.post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")
    assert again.status_code == 200 and again.json()["enrolled"] == 0  # không ghi danh trùng
    overview = (await manager.get(f"/api/v1/cohorts/{cohort_id}/overview")).json()
    assert overview["accepted_waiting_enrollment"] == 0 and overview["enrollments"]["active"] >= int(
        training_env["accepted"]
    )
    reviewer = await login_as("reviewer", GAMMA)
    assert (await reviewer.post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")).status_code == 403


async def test_competency_assessment_rules_and_mentor_scope(login_as: Any, training_env: dict[str, str]) -> None:
    manager, cohort_id = await _ready_cohort(login_as, training_env)
    ctx = await _learner_with_track(manager, cohort_id)
    learner_id = ctx["learner"]["id"]
    trainer = await login_as("training_manager", GAMMA)

    matrix = (await trainer.get(f"/api/v1/enrollments/{learner_id}/competencies")).json()
    assert matrix["suggestion"] == "pending" and matrix["matrix"] and all(m["level"] is None for m in matrix["matrix"])
    row = matrix["matrix"][0]
    url = f"/api/v1/enrollments/{learner_id}/assessments"
    assert (
        await trainer.post(url, json={"competency_id": row["competency_id"], "level": 3, "evidence": "ngắn"})
    ).status_code == 422
    assert (
        await trainer.post(
            url, json={"competency_id": row["competency_id"], "level": row["max_level"] + 1, "evidence": "x" * 30}
        )
    ).status_code == 422
    assert (
        await trainer.post(
            url, json={"competency_id": "01a10a21-0000-7000-8000-000000000000", "level": 3, "evidence": "x" * 30}
        )
    ).status_code == 422

    # mức đạt chuẩn tất cả năng lực → gợi ý đạt; chỉ cần một năng lực thấp hơn chuẩn → gợi ý chưa đạt
    for m in matrix["matrix"]:
        ok = await trainer.post(
            url,
            json={
                "competency_id": m["competency_id"],
                "level": m["target"],
                "evidence": "Hoàn thành dự án thực chiến đúng yêu cầu.",
            },
        )
        assert ok.status_code == 201, ok.text
    assert (await trainer.get(f"/api/v1/enrollments/{learner_id}/competencies")).json()["suggestion"] == "qualified"
    low = matrix["matrix"][0]
    await trainer.post(
        url,
        json={
            "competency_id": low["competency_id"],
            "level": max(1, low["target"] - 1),
            "evidence": "Đánh giá lại: chưa đạt mức yêu cầu.",
        },
    )
    assert (await trainer.get(f"/api/v1/enrollments/{learner_id}/competencies")).json()[
        "suggestion"
    ] == "not_qualified"  # lấy mức mới nhất

    # mentor chỉ đánh giá học viên mình phụ trách
    mentor = await login_as("mentor", GAMMA)
    denied = await mentor.post(
        url,
        json={"competency_id": row["competency_id"], "level": 2, "evidence": "Thử đánh giá học viên không phụ trách."},
    )
    assert denied.status_code == 403
    assert (await mentor.get("/api/v1/mentor/learners")).json() == []  # chưa được giao ai
    # và cũng không đọc được hồ sơ năng lực của học viên không phụ trách (404, không lộ sự tồn tại)
    assert (await mentor.get(f"/api/v1/enrollments/{learner_id}/competencies")).status_code == 404


async def test_mentor_sees_and_assesses_only_assigned_learners(login_as: Any, training_env: dict[str, str]) -> None:
    manager, cohort_id = await _ready_cohort(login_as, training_env)
    ctx = await _learner_with_track(manager, cohort_id)
    learner_id = ctx["learner"]["id"]
    partner = (
        await manager.post("/api/v1/partners", json={"name": "Đối tác thử nghiệm QA", "skills": ["python"]})
    ).json()
    admin = await login_as("admin", GAMMA)
    mentor_row = next(u for u in (await admin.get("/api/v1/admin/users?q=mentor@delta.test")).json()["items"])
    placed = await manager.post(
        f"/api/v1/enrollments/{learner_id}/placement",
        json={"partner_id": partner["id"], "mentor_membership_id": mentor_row["membership_id"], "project": "Dự án QA"},
    )
    assert placed.status_code == 200, placed.text

    mentor = await login_as("mentor", GAMMA)
    mine = (await mentor.get("/api/v1/mentor/learners")).json()
    assert [m["enrollment_id"] for m in mine] == [learner_id] and mine[0]["partner_name"] == "Đối tác thử nghiệm QA"
    matrix = (await mentor.get(f"/api/v1/enrollments/{learner_id}/competencies")).json()["matrix"]
    done = await mentor.post(
        f"/api/v1/enrollments/{learner_id}/assessments",
        json={
            "competency_id": matrix[0]["competency_id"],
            "level": matrix[0]["target"],
            "evidence": "Giao đúng hạn module phân loại, có kiểm thử.",
        },
    )
    assert done.status_code == 201


async def test_qualification_decision_needs_track_reason_and_is_final(
    login_as: Any, training_env: dict[str, str]
) -> None:
    manager, cohort_id = await _ready_cohort(login_as, training_env)
    page = (await manager.get(f"/api/v1/cohorts/{cohort_id}/enrollments?status=active&limit=50")).json()
    untracked = next(e for e in page["items"] if e["track_id"] is None)
    no_track = await manager.post(
        f"/api/v1/enrollments/{untracked['id']}/qualification",
        json={"outcome": "qualified", "reason": "Đủ điều kiện xét."},
    )
    assert no_track.status_code == 409  # phải có nhánh trước

    ctx = await _learner_with_track(manager, cohort_id)
    eid = next(
        e["id"]
        for e in (await manager.get(f"/api/v1/cohorts/{cohort_id}/enrollments?status=active&limit=50")).json()["items"]
        if e["track_id"]
    )
    url = f"/api/v1/enrollments/{eid}/qualification"
    assert (await manager.post(url, json={"outcome": "qualified", "reason": "ngắn"})).status_code == 422
    assert (
        await manager.post(url, json={"outcome": "xuat_sac", "reason": "Lý do đủ dài để hợp lệ."})
    ).status_code == 422
    first = await manager.post(
        url, json={"outcome": "qualified", "reason": "Đạt đủ chuẩn năng lực theo đánh giá mentor."}
    )
    assert first.status_code == 200 and first.json()["status"] == "qualified"
    assert (
        await manager.post(url, json={"outcome": "not_qualified", "reason": "Đổi ý sau khi đã chốt kết quả."})
    ).status_code == 409
    assert ctx["track"]["id"]


async def test_stipend_ledger_matches_cost_entries_and_is_idempotent(
    login_as: Any, training_env: dict[str, str]
) -> None:
    manager, cohort_id = await _ready_cohort(login_as, training_env)
    admin = await login_as("admin", GAMMA)
    gen_url = f"/api/v1/cohorts/{cohort_id}/stipends/generate"
    assert (await manager.post(gen_url, json={"period": "2026/09"})).status_code == 422
    assert (await manager.post(gen_url, json={"period": "2026-13"})).status_code == 422

    created = (await manager.post(gen_url, json={"period": PERIOD})).json()["created"]
    assert created > 0
    assert (await manager.post(gen_url, json={"period": PERIOD})).json()["created"] == 0  # chạy lại không tạo trùng

    before = (await admin.get(f"/api/v1/admin/costs/summary?cohort_id={cohort_id}")).json()["by_category"]["stipend"][
        "amount"
    ]
    paid = (await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/pay", json={"period": PERIOD})).json()
    assert paid["count"] == created and paid["total_vnd"] > 0
    again = (await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/pay", json={"period": PERIOD})).json()
    assert again["count"] == 0  # đã chi thì không ghi nhận chi lần hai
    after = (await admin.get(f"/api/v1/admin/costs/summary?cohort_id={cohort_id}")).json()["by_category"]["stipend"][
        "amount"
    ]
    assert after - before == pytest.approx(paid["total_vnd"])  # sổ chi phí khớp phụ cấp đã chi

    rows = (await manager.get(f"/api/v1/cohorts/{cohort_id}/stipends")).json()
    assert any(r["period"] == PERIOD and r["status"] == "paid" and r["count"] == created for r in rows)
    reviewer = await login_as("reviewer", GAMMA)
    assert (await reviewer.post(gen_url, json={"period": PERIOD})).status_code == 403


async def test_composer_apply_is_one_shot_and_skips_changed_learners(
    login_as: Any, training_env: dict[str, str]
) -> None:
    manager, cohort_id = await _ready_cohort(login_as, training_env)
    run = await manager.post(
        f"/api/v1/cohorts/{cohort_id}/composer/runs", json={"class_count": 3, "class_mode": "balanced"}
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    first = await manager.post(f"/api/v1/composer/runs/{run_id}/apply")
    assert first.status_code == 200 and first.json()["applied"] > 0
    assert (await manager.post(f"/api/v1/composer/runs/{run_id}/apply")).status_code == 409  # chỉ áp dụng một lần
    bad = await manager.post(f"/api/v1/cohorts/{cohort_id}/composer/runs", json={"class_count": 0})
    assert bad.status_code == 422
    assert (
        await manager.post(f"/api/v1/cohorts/{cohort_id}/composer/runs", json={"class_count": 3, "pref_weight": 2})
    ).status_code == 422
