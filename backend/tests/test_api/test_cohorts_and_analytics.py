import uuid

import pytest
from sqlalchemy import select

from src.db import set_org_context
from src.models import Application, Enrollment
from src.services import analytics

GAMMA = "gamma"


async def _programs(client) -> dict:  # type: ignore[no-untyped-def]
    programs = (await client.get("/api/v1/programs")).json()
    program = next(p for p in programs if p["code"] == "ai-talent")
    return {"program": program, "cohorts": {c["code"]: c for c in program["cohorts"]}}


async def _intakes(client) -> dict:  # type: ignore[no-untyped-def]
    return {i["name"]: i for i in (await client.get("/api/v1/intakes")).json()}


async def test_funnel_and_stages_for_a_finished_intake(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", GAMMA)
    intakes = await _intakes(admin)
    k1 = intakes["[Minh hoạ] Đợt tuyển khoá 1"]
    res = await admin.get(f"/api/v1/analytics/funnel?intake_id={k1['id']}")
    assert res.status_code == 200, res.text
    data = res.json()
    counts = [s["count"] for s in data["stages"]]
    assert data["stages"][0]["key"] == "submitted" and counts[0] == 160
    assert counts[0] >= counts[-2] >= counts[-1] > 0  # phễu không tăng dần
    assert data["quota_fill"] == pytest.approx(1.0, abs=0.01)


async def test_rubric_lab_finds_predictive_criteria_and_simulates_new_weights(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    reviewer = await login_as("reviewer", GAMMA)
    intakes = await _intakes(reviewer)
    ids = [intakes[f"[Minh hoạ] Đợt tuyển khoá {k}"]["id"] for k in (1, 2, 3)]

    report = (await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids})).json()
    assert report["pool"] > 200 and report["admitted"] > 100
    analysis = report["analysis"]
    by = {c["criterion"]: c for c in analysis["criteria"]}
    assert analysis["reliable"] and analysis["model_auc"] > 0.6
    # dữ liệu sinh có chủ đích: dự án/lập trình dự báo kết quả, động lực thì không
    assert by["projects"]["coef"] > by["motivation"]["coef"] and by["programming"]["coef"] > by["motivation"]["coef"]
    assert not by["motivation"]["significant"]
    assert any("thu hẹp" in w for w in analysis["warnings"])

    # kéo trọng số về tiêu chí có giá trị dự báo: ước lượng tỉ lệ đạt không giảm; kèm kiểm tra công bằng
    new = {
        "projects": 5,
        "programming": 5,
        "ai_ml": 2,
        "education": 1,
        "experience": 1,
        "motivation": 0,
        "communication": 0,
    }
    sim = (await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids, "weights": new})).json()["simulation"]
    assert sim["selected"] == report["admitted"] and sim["changed_in"] > 0
    assert sim["model_expected_new"] >= sim["model_expected_old"] - 0.005
    assert "gender" in sim["fairness_new"] and "region" in sim["fairness_new"]
    assert sim["overlap_actual_old"] > 0.75  # rubric cũ gần như tái tạo được danh sách đã nhận

    bad = await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids, "weights": {"projects": 0}})
    assert bad.status_code == 422
    applicant = await login_as("applicant", GAMMA)
    assert (await applicant.post("/api/v1/analytics/lab", json={"intake_ids": ids})).status_code == 403


async def test_rubric_lab_lists_comparable_intakes_with_their_criteria(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    reviewer = await login_as("reviewer", GAMMA)
    res = await reviewer.get("/api/v1/analytics/lab/intakes")
    assert res.status_code == 200, res.text
    by_name = {i["name"]: i for i in res.json()}
    history = [by_name[f"[Minh hoạ] Đợt tuyển khoá {k}"] for k in (1, 2, 3)]
    assert all(i["admitted"] > 0 and i["with_outcome"] > 0 for i in history)
    assert len({tuple(c["id"] for c in i["criteria"]) for i in history}) == 1  # cùng bộ tiêu chí: so sánh được
    assert "projects" in {c["id"] for c in history[0]["criteria"]}
    assert all(i["status"] in ("closed", "archived") for i in res.json())  # đợt đang mở không vào Lab
    applicant = await login_as("applicant", GAMMA)
    assert (await applicant.get("/api/v1/analytics/lab/intakes")).status_code == 403


async def test_rubric_lab_reuses_analysis_until_data_changes(login_as, demo_env, owner_maker, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Chỉnh trọng số không phân tích lại; dữ liệu đổi (kết quả của một học viên) thì tính lại. Kết quả ổn định."""
    reviewer = await login_as("reviewer", GAMMA)
    intakes = await _intakes(reviewer)
    ids = [intakes[f"[Minh hoạ] Đợt tuyển khoá {k}"]["id"] for k in (1, 2, 3)]
    analytics._LAB_CACHE.clear()
    calls: list[int] = []
    real_analyse = analytics.lab.analyse
    monkeypatch.setattr(analytics.lab, "analyse", lambda *a, **k: calls.append(1) or real_analyse(*a, **k))

    first = (await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids})).json()
    weights = {c["id"]: 1 for c in first["criteria"]}
    sim = await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids, "weights": weights})
    again = (await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids})).json()
    assert sim.status_code == 200 and again == first and len(calls) == 1
    analytics._LAB_CACHE.clear()
    assert (
        await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids})
    ).json() == first  # tính lại vẫn y hệt

    async with owner_maker() as session, session.begin():
        await set_org_context(session, uuid.UUID(demo_env["org_id"]))
        enrollment = (
            await session.execute(
                select(Enrollment)
                .join(Application, Application.id == Enrollment.application_id)
                .where(Application.intake_id == uuid.UUID(ids[0]), Enrollment.status == "qualified")
                .limit(1)
            )
        ).scalar_one()
        enrollment.status = "not_qualified"
    try:
        changed = (await reviewer.post("/api/v1/analytics/lab", json={"intake_ids": ids})).json()
        assert len(calls) == 3
        assert changed["analysis"]["events"] == first["analysis"]["events"] - 1
    finally:  # trả lại dữ liệu minh hoạ dùng chung cho các test phân tích khác
        async with owner_maker() as session, session.begin():
            await set_org_context(session, uuid.UUID(demo_env["org_id"]))
            (await session.get(Enrollment, enrollment.id)).status = "qualified"  # type: ignore[union-attr]


async def test_fairness_monitor_reports_group_rates(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    reviewer = await login_as("reviewer", GAMMA)
    intakes = await _intakes(reviewer)
    data = (
        await reviewer.get(f"/api/v1/analytics/fairness?intake_id={intakes['[Minh hoạ] Đợt tuyển khoá 2']['id']}")
    ).json()
    accepted = data["stages"]["accepted"]
    assert set(accepted["gender"]["rates"]) == {"female", "male"}
    assert 0 < accepted["gender"]["impact_ratio"] <= 1
    assert "bốn phần năm" in data["note"]


async def test_cohort_enrollment_composer_and_apply(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    manager = await login_as("cohort_manager", GAMMA)
    cohort_id = demo_env["cohort_id"]

    overview = (await manager.get(f"/api/v1/cohorts/{cohort_id}/overview")).json()
    assert overview["accepted_waiting_enrollment"] == 60 and overview["enrollments"] == {}

    # chỉ người có quyền cohort.manage mới nhập học
    assert (
        await (await login_as("reviewer", GAMMA)).post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")
    ).status_code == 403
    assert (
        await manager.post(f"/api/v1/cohorts/{cohort_id}/composer/runs", json={})
    ).status_code == 409  # chưa có học viên
    enrolled = (await manager.post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")).json()
    assert enrolled["enrolled"] == 60
    assert (await manager.post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")).json()[
        "enrolled"
    ] == 0  # không nhập trùng

    run = await manager.post(
        f"/api/v1/cohorts/{cohort_id}/composer/runs", json={"class_count": 3, "class_mode": "levels"}
    )
    assert run.status_code == 201, run.text
    metrics = run.json()["metrics"]
    assert metrics["learners"] == 60 and len(metrics["classes"]) == 3
    assert metrics["pref_top2_rate"] > 0.6 and metrics["placement_rate"] > 0.5
    # lớp theo trình độ: khoảng điểm không chồng lấn
    ranges = sorted((c["min_score"], c["max_score"]) for c in metrics["classes"])
    assert ranges[0][1] <= ranges[1][0] + 1e-9 and ranges[1][1] <= ranges[2][0] + 1e-9

    # thử what-if cân bằng: chênh lệch điểm trung bình giữa các lớp nhỏ hơn
    balanced = (
        await manager.post(
            f"/api/v1/cohorts/{cohort_id}/composer/runs", json={"class_count": 3, "class_mode": "balanced"}
        )
    ).json()
    assert balanced["metrics"]["class_mean_spread"] < metrics["class_mean_spread"]
    assert len((await manager.get(f"/api/v1/cohorts/{cohort_id}/composer/runs")).json()) == 2

    # thiếu sức chứa bị từ chối rõ ràng
    tiny = await manager.post(
        f"/api/v1/cohorts/{cohort_id}/composer/runs",
        json={"track_capacity": {"ai_products": 1, "ai_infrastructure": 1, "ai_applications": 1}},
    )
    assert tiny.status_code == 422 and "sức chứa" in tiny.json()["detail"]

    detail = (await manager.get(f"/api/v1/composer/runs/{run.json()['id']}")).json()
    assert len(detail["assignments"]) == 60 and all(a["name"] and a["explanation"] for a in detail["assignments"])

    applied = await manager.post(f"/api/v1/composer/runs/{run.json()['id']}/apply")
    assert applied.json() == {"applied": 60, "skipped": 0}
    assert (await manager.post(f"/api/v1/composer/runs/{run.json()['id']}/apply")).status_code == 409
    after = (await manager.get(f"/api/v1/cohorts/{cohort_id}/overview")).json()
    assert sum(c["assigned"] for c in after["classes"]) == 60 and sum(t["assigned"] for t in after["tracks"]) == 60
    assert all(t["assigned"] <= t["capacity"] for t in after["tracks"])
    assert after["unplaced"] < 60


async def test_mentor_assessment_qualification_and_stipend_flow(login_as, demo_env) -> None:  # type: ignore[no-untyped-def]
    manager = await login_as("cohort_manager", GAMMA)
    trainer = await login_as("training_manager", GAMMA)
    mentor = await login_as("mentor", GAMMA)
    admin = await login_as("admin", GAMMA)
    cohort_id = demo_env["cohort_id"]

    page = (await manager.get(f"/api/v1/cohorts/{cohort_id}/enrollments?limit=200")).json()
    if page["total"] == 0:
        await manager.post(f"/api/v1/cohorts/{cohort_id}/enroll-accepted")
        page = (await manager.get(f"/api/v1/cohorts/{cohort_id}/enrollments?limit=200")).json()
    learner = next(i for i in page["items"] if i["status"] == "active")
    if learner["track_id"] is None:
        overview = (await manager.get(f"/api/v1/cohorts/{cohort_id}/overview")).json()
        track = overview["tracks"][0]
        assert (
            await manager.patch(f"/api/v1/enrollments/{learner['id']}", json={"track_id": track["id"]})
        ).status_code == 200

    matrix = (await trainer.get(f"/api/v1/enrollments/{learner['id']}/competencies")).json()
    assert matrix["suggestion"] == "pending" and matrix["matrix"]

    # mentor chỉ đánh giá học viên mình phụ trách
    first = matrix["matrix"][0]
    denied = await mentor.post(
        f"/api/v1/enrollments/{learner['id']}/assessments",
        json={
            "competency_id": first["competency_id"],
            "level": 4,
            "evidence": "Hoàn thành tốt dự án thực chiến theo yêu cầu.",
        },
    )
    assert denied.status_code == 403
    # người quản lý đào tạo đánh giá được; kiểm tra các ràng buộc
    for body, code in (
        (
            {
                "competency_id": first["competency_id"],
                "level": 9,
                "evidence": "Hoàn thành tốt dự án thực chiến theo yêu cầu.",
            },
            422,
        ),
        ({"competency_id": first["competency_id"], "level": 4, "evidence": "ngắn"}, 422),
    ):
        assert (await trainer.post(f"/api/v1/enrollments/{learner['id']}/assessments", json=body)).status_code == code
    for m in matrix["matrix"]:
        ok = await trainer.post(
            f"/api/v1/enrollments/{learner['id']}/assessments",
            json={
                "competency_id": m["competency_id"],
                "level": m["target"],
                "evidence": "Đạt yêu cầu qua dự án thực chiến, có sản phẩm bàn giao.",
            },
        )
        assert ok.status_code == 201
    done = (await trainer.get(f"/api/v1/enrollments/{learner['id']}/competencies")).json()
    assert done["suggestion"] == "qualified"

    # chỉ người quản lý khoá chốt kết quả; cần lý do; không chốt hai lần
    assert (
        await trainer.post(
            f"/api/v1/enrollments/{learner['id']}/qualification",
            json={"outcome": "qualified", "reason": "Đạt đủ các năng lực mục tiêu"},
        )
    ).status_code == 403
    assert (
        await manager.post(
            f"/api/v1/enrollments/{learner['id']}/qualification", json={"outcome": "qualified", "reason": "ngắn"}
        )
    ).status_code == 422
    final = await manager.post(
        f"/api/v1/enrollments/{learner['id']}/qualification",
        json={"outcome": "qualified", "reason": "Đạt đủ các năng lực mục tiêu theo đánh giá mentor."},
    )
    assert final.status_code == 200 and final.json()["status"] == "qualified"
    assert (
        await manager.post(
            f"/api/v1/enrollments/{learner['id']}/qualification",
            json={"outcome": "not_qualified", "reason": "Đổi ý sau khi đã chốt kết quả."},
        )
    ).status_code == 409

    # phụ cấp: ghi nhận một kỳ, đánh dấu đã chi tạo bút toán chi phí hệ thống, chạy lại không trùng
    gen = (await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/generate", json={"period": "2026-10"})).json()
    assert gen["created"] > 0
    assert (await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/generate", json={"period": "2026-10"})).json()[
        "created"
    ] == 0
    before = (await admin.get(f"/api/v1/admin/costs/summary?cohort_id={cohort_id}")).json()["by_category"]["stipend"][
        "amount"
    ]
    paid = (await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/pay", json={"period": "2026-10"})).json()
    assert paid["count"] == gen["created"] and paid["total_vnd"] == gen["created"] * 8_000_000
    after = (await admin.get(f"/api/v1/admin/costs/summary?cohort_id={cohort_id}")).json()["by_category"]["stipend"][
        "amount"
    ]
    assert after == before + paid["total_vnd"]
    assert (await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/pay", json={"period": "2026-10"})).json()[
        "count"
    ] == 0
    assert (
        await manager.post(f"/api/v1/cohorts/{cohort_id}/stipends/generate", json={"period": "tháng mười"})
    ).status_code == 422
