import asyncio

from httpx import AsyncClient

from tests.helpers import FULL_SCORES, create_open_intake, good_content, submit_application


async def _close_and_start(admin: AsyncClient, intake_id: str) -> int:
    assert (await admin.post(f"/api/v1/intakes/{intake_id}/close")).status_code == 200
    started = await admin.post(f"/api/v1/intakes/{intake_id}/start")
    assert started.status_code == 200, started.text
    return int(started.json()["moved"])


async def _review(
    client: AsyncClient, app_id: str, scores: dict[str, float], rec: str = "advance", comment: str = ""
) -> object:
    return await client.put(
        f"/api/v1/staff/applications/{app_id}/review",
        json={"scores": scores, "comment": comment, "recommendation": rec, "submit": True},
    )


async def test_intake_needs_rubric_to_publish_and_is_hidden_until_open(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    program = (await admin.post("/api/v1/programs", json={"code": "px1", "name_vi": "P"})).json()
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    intake = (
        await admin.post(
            "/api/v1/intakes",
            json={
                "program_id": program["id"],
                "name": "Nháp",
                "opens_at": (now - timedelta(hours=1)).isoformat(),
                "closes_at": (now + timedelta(days=1)).isoformat(),
                "quota": 3,
                "rounds": [{"key": "r1", "label": "Vòng 1", "type": "review"}],
            },
        )
    ).json()
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/publish")).status_code == 422
    assert intake["id"] not in {i["id"] for i in (await applicant.get("/api/v1/intakes")).json()}
    assert (await applicant.get(f"/api/v1/intakes/{intake['id']}")).status_code == 404


async def test_applicant_draft_validation_submit_and_privacy(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    other = await login_as("applicant2")
    intake = await create_open_intake(admin)

    created = await applicant.post("/api/v1/applications", json={"intake_id": intake["id"]})
    assert created.status_code == 201
    app = created.json()
    again = await applicant.post("/api/v1/applications", json={"intake_id": intake["id"]})
    assert again.json()["id"] == app["id"]  # idempotent

    # thiếu thông tin: không nộp được, báo rõ từng trường
    incomplete = await applicant.post(f"/api/v1/applications/{app['id']}/submit", json={"consent": True})
    assert incomplete.status_code == 422
    assert "content.essays.motivation" in incomplete.json()["fields"]

    # dữ liệu sai định dạng bị chặn, không lưu
    bad_link = good_content()
    bad_link["projects"][0]["link"] = "javascript:alert(1)"
    assert (await applicant.patch(f"/api/v1/applications/{app['id']}", json={"content": bad_link})).status_code == 422
    unknown = await applicant.patch(f"/api/v1/applications/{app['id']}", json={"content": {"hack": "x"}})
    assert unknown.status_code == 422

    await applicant.patch(
        f"/api/v1/applications/{app['id']}",
        json={"profile": {"full_name": "Lê Thị B", "phone": "0901234567"}, "content": good_content()},
    )
    no_consent = await applicant.post(f"/api/v1/applications/{app['id']}/submit", json={"consent": False})
    assert no_consent.status_code == 422
    done = await applicant.post(f"/api/v1/applications/{app['id']}/submit", json={"consent": True})
    assert done.status_code == 200
    assert done.json()["status"] == "SUBMITTED"
    # cờ đủ điều kiện được tính, không tự loại
    assert done.json()["flags"] == []

    # đã nộp thì không sửa được
    assert (
        await applicant.patch(f"/api/v1/applications/{app['id']}", json={"content": good_content()})
    ).status_code == 409
    # người khác không thấy hồ sơ (404, không lộ sự tồn tại)
    assert (await other.get(f"/api/v1/applications/{app['id']}")).status_code == 404
    assert (await other.patch(f"/api/v1/applications/{app['id']}", json={"content": good_content()})).status_code == 404

    timeline = (await applicant.get(f"/api/v1/applications/{app['id']}/timeline")).json()
    assert [e["type"] for e in timeline] == ["application.created", "application.submitted"]


async def test_eligibility_flags_but_never_auto_rejects(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    intake = await create_open_intake(admin)
    content = good_content()
    content["education"][0]["status"] = "student"
    app = await submit_application(applicant, intake["id"], content=content)
    assert app["status"] == "SUBMITTED"
    assert [f["rule"] for f in app["flags"]] == ["final_year"]


async def test_full_happy_path_with_blind_review_and_four_eyes(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    reviewer = await login_as("reviewer")
    approver = await login_as("approver")
    intake = await create_open_intake(admin)
    app = await submit_application(applicant, intake["id"], name="Trần Thị Bí Mật")

    # chưa bắt đầu vòng xét thì chưa thể đóng/bắt đầu sớm
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/start")).status_code == 409
    assert await _close_and_start(admin, intake["id"]) == 1

    # chấm mù: reviewer không thấy tên; admin (có pii.read) thấy
    queue = (await reviewer.get(f"/api/v1/staff/applications?intake_id={intake['id']}")).json()
    assert queue["items"][0]["name"] is None and queue["items"][0]["candidate_code"].startswith("A-")
    assert (await admin.get(f"/api/v1/staff/applications?intake_id={intake['id']}")).json()["items"][0][
        "name"
    ] == "Trần Thị Bí Mật"
    detail = (await reviewer.get(f"/api/v1/staff/applications/{app['id']}")).json()
    assert detail["profile"] is None and detail["content"]["links"]["github"] == "(ẩn)"
    assert detail["rubric"]["criteria"] and detail["ai"] is None

    # điểm tuyệt đối cần nhận xét; thiếu tiêu chí không chốt được
    extreme = await _review(reviewer, app["id"], {"projects": 5, "programming": 4, "motivation": 3})
    assert extreme.status_code == 422
    partial = await _review(reviewer, app["id"], {"projects": 3})
    assert partial.status_code == 422
    out_of_range = await _review(reviewer, app["id"], {"projects": 9, "programming": 4, "motivation": 3})
    assert out_of_range.status_code == 422

    # chưa đủ reviewer thì không chuyển vòng
    assert (await reviewer.post(f"/api/v1/staff/applications/{app['id']}/advance", json={})).status_code == 409
    ok = await _review(reviewer, app["id"], FULL_SCORES)
    assert ok.status_code == 200 and ok.json()["total_score"] == 76.67
    # đã chốt thì không sửa
    assert (await _review(reviewer, app["id"], FULL_SCORES)).status_code == 409

    advanced = await reviewer.post(f"/api/v1/staff/applications/{app['id']}/advance", json={})
    assert advanced.status_code == 200 and advanced.json()["current_round"] == "aptitude"

    # vòng cuối: không "advance" nữa, phải đề xuất quyết định
    await _review(reviewer, app["id"], FULL_SCORES)
    assert (await reviewer.post(f"/api/v1/staff/applications/{app['id']}/advance", json={})).status_code == 422
    short = await reviewer.post(
        f"/api/v1/staff/applications/{app['id']}/proposals", json={"outcome": "accepted", "reason": "tốt"}
    )
    assert short.status_code == 422
    proposal = await reviewer.post(
        f"/api/v1/staff/applications/{app['id']}/proposals",
        json={"outcome": "accepted", "reason": "Dự án thực tế mạnh và nền tảng lập trình vững qua cả hai vòng."},
    )
    assert proposal.status_code == 201, proposal.text
    decision_id = proposal.json()["decision_id"]

    # reviewer không có quyền phê duyệt
    body = {
        "outcome": "accepted",
        "reason": "Đồng ý với đề xuất vì kết quả hai vòng tốt.",
        "applicant_message": "Chúc mừng bạn đã được nhận!",
    }
    assert (await reviewer.post(f"/api/v1/staff/decisions/{decision_id}/approve", json=body)).status_code == 403
    pending = (await approver.get("/api/v1/staff/approvals")).json()
    assert any(p["decision_id"] == decision_id for p in pending)
    approved = await approver.post(f"/api/v1/staff/decisions/{decision_id}/approve", json=body)
    assert approved.status_code == 200 and approved.json()["status"] == "ACCEPTED"
    # đã xử lý thì không duyệt lại
    assert (await approver.post(f"/api/v1/staff/decisions/{decision_id}/approve", json=body)).status_code == 409

    mine = (await applicant.get(f"/api/v1/applications/{app['id']}")).json()
    assert mine["status"] == "ACCEPTED"
    events = (await applicant.get(f"/api/v1/applications/{app['id']}/timeline")).json()
    types = [e["type"] for e in events]
    assert "decision.accepted" in types and "decision.proposed" not in types  # nội bộ không lộ
    notes = (await applicant.get("/api/v1/notifications")).json()
    assert notes["unread"] >= 3 and any(n["type"] == "decision.accepted" for n in notes["items"])


async def test_proposer_cannot_approve_own_proposal(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    dual = await login_as("dual")
    applicant = await login_as("applicant")
    intake = await create_open_intake(admin)
    app = await submit_application(applicant, intake["id"])
    await _close_and_start(admin, intake["id"])
    await _review(dual, app["id"], FULL_SCORES)
    proposal = await dual.post(
        f"/api/v1/staff/applications/{app['id']}/proposals",
        json={"outcome": "rejected", "reason": "Không đủ kinh nghiệm thực tế cho cường độ chương trình."},
    )
    decision_id = proposal.json()["decision_id"]
    own = await dual.post(
        f"/api/v1/staff/decisions/{decision_id}/approve",
        json={
            "outcome": "rejected",
            "reason": "Tự duyệt đề xuất của chính mình, không hợp lệ.",
            "applicant_message": "Rất tiếc về kết quả.",
        },
    )
    assert own.status_code == 403


async def test_reviewer_cannot_review_own_application(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    dual = await login_as("dual")
    intake = await create_open_intake(admin)
    app = await submit_application(dual, intake["id"], name="Dual Role")
    await _close_and_start(admin, intake["id"])
    res = await _review(dual, app["id"], FULL_SCORES)
    assert res.status_code == 403
    proposal = await dual.post(
        f"/api/v1/staff/applications/{app['id']}/proposals",
        json={"outcome": "accepted", "reason": "Tự đề xuất cho chính mình, không hợp lệ theo quy định."},
    )
    assert proposal.status_code == 403


async def test_reviewer_disagreement_blocks_advance_and_other_reviews_hidden_until_submit(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    r1 = await login_as("reviewer")
    r2 = await login_as("reviewer2")
    # đợt yêu cầu 2 reviewer
    intake = await create_open_intake(admin)
    await admin.patch(f"/api/v1/intakes/{intake['id']}", json={"min_reviews": 2})
    app = await submit_application(applicant, intake["id"])
    await _close_and_start(admin, intake["id"])

    await _review(r1, app["id"], FULL_SCORES, "advance")
    # r2 chưa chốt: chưa thấy điểm của r1 (độc lập)
    assert (await r2.get(f"/api/v1/staff/applications/{app['id']}")).json()["reviews"] == []
    assert (
        await r1.post(f"/api/v1/staff/applications/{app['id']}/advance", json={})
    ).status_code == 409  # thiếu reviewer

    await _review(r2, app["id"], {"projects": 2, "programming": 2, "motivation": 2}, "reject")
    after = (await r2.get(f"/api/v1/staff/applications/{app['id']}")).json()
    assert len(after["reviews"]) == 2 and after["disagreement"] is True
    blocked = await r1.post(f"/api/v1/staff/applications/{app['id']}/advance", json={})
    assert blocked.status_code == 409 and "bất đồng" in blocked.json()["detail"]


async def test_request_info_and_resubmit_cycle(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    reviewer = await login_as("reviewer")
    intake = await create_open_intake(admin)
    app = await submit_application(applicant, intake["id"])
    await _close_and_start(admin, intake["id"])

    assert (
        await reviewer.post(f"/api/v1/staff/applications/{app['id']}/request-info", json={"message": "ngắn"})
    ).status_code == 422
    asked = await reviewer.post(
        f"/api/v1/staff/applications/{app['id']}/request-info",
        json={"message": "Vui lòng bổ sung đường dẫn tới mã nguồn dự án."},
    )
    assert asked.status_code == 200 and asked.json()["status"] == "NEEDS_INFO"
    # được sửa lại khi cần bổ sung, rồi gửi lại về đúng vòng đang xét
    edit = await applicant.patch(f"/api/v1/applications/{app['id']}", json={"content": good_content()})
    assert edit.status_code == 200
    back = await applicant.post(f"/api/v1/applications/{app['id']}/resubmit", json={})
    assert (
        back.status_code == 200 and back.json()["status"] == "IN_ROUND" and back.json()["current_round"] == "portfolio"
    )
    events = (await applicant.get(f"/api/v1/applications/{app['id']}/timeline")).json()
    assert any(e["type"] == "info.requested" and "mã nguồn" in (e["message"] or "") for e in events)


async def test_optimistic_locking_and_concurrent_approval(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    reviewer = await login_as("reviewer")
    a1 = await login_as("approver")
    a2 = await login_as("approver2")
    intake = await create_open_intake(admin)
    app = await submit_application(applicant, intake["id"])
    await _close_and_start(admin, intake["id"])
    await _review(reviewer, app["id"], FULL_SCORES)

    stale = await reviewer.post(
        f"/api/v1/staff/applications/{app['id']}/proposals",
        json={"outcome": "accepted", "reason": "Hồ sơ đạt yêu cầu ở mọi tiêu chí chính của vòng.", "version": 1},
    )
    assert stale.status_code == 409

    proposal = await reviewer.post(
        f"/api/v1/staff/applications/{app['id']}/proposals",
        json={"outcome": "accepted", "reason": "Hồ sơ đạt yêu cầu ở mọi tiêu chí chính của vòng."},
    )
    decision_id = proposal.json()["decision_id"]
    body = {
        "outcome": "accepted",
        "reason": "Đồng ý vì hồ sơ đạt các tiêu chí chính.",
        "applicant_message": "Chúc mừng bạn được nhận!",
    }
    results = await asyncio.gather(
        a1.post(f"/api/v1/staff/decisions/{decision_id}/approve", json=body),
        a2.post(f"/api/v1/staff/decisions/{decision_id}/approve", json=body),
    )
    assert sorted(r.status_code for r in results) == [200, 409]


async def test_quota_blocks_over_acceptance(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    reviewer = await login_as("reviewer")
    approver = await login_as("approver")
    intake = await create_open_intake(admin, quota=1)
    apps = []
    for who, name in (("applicant", "A"), ("applicant2", "B")):
        apps.append(await submit_application(await login_as(who), intake["id"], name=name))
    await _close_and_start(admin, intake["id"])

    decisions = []
    for app in apps:
        await _review(reviewer, app["id"], FULL_SCORES)
        proposal = await reviewer.post(
            f"/api/v1/staff/applications/{app['id']}/proposals",
            json={"outcome": "accepted", "reason": "Đạt yêu cầu theo đánh giá của reviewer ở vòng này."},
        )
        decisions.append(proposal.json()["decision_id"])
    body = {
        "outcome": "accepted",
        "reason": "Đồng ý nhận hồ sơ này vào chương trình.",
        "applicant_message": "Chúc mừng bạn được nhận!",
    }
    assert (await approver.post(f"/api/v1/staff/decisions/{decisions[0]}/approve", json=body)).status_code == 200
    full = await approver.post(f"/api/v1/staff/decisions/{decisions[1]}/approve", json=body)
    assert full.status_code == 409 and "chỉ tiêu" in full.json()["detail"]
    waitlist = await approver.post(
        f"/api/v1/staff/decisions/{decisions[1]}/approve",
        json={**body, "outcome": "waitlisted", "applicant_message": "Bạn trong danh sách chờ."},
    )
    assert waitlist.status_code == 200 and waitlist.json()["status"] == "WAITLISTED"


async def test_withdraw_and_return_flow(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    applicant = await login_as("applicant")
    reviewer = await login_as("reviewer")
    approver = await login_as("approver")
    intake = await create_open_intake(admin)
    app = await submit_application(applicant, intake["id"])
    await _close_and_start(admin, intake["id"])
    await _review(reviewer, app["id"], FULL_SCORES)
    proposal = await reviewer.post(
        f"/api/v1/staff/applications/{app['id']}/proposals",
        json={"outcome": "rejected", "reason": "Chưa thấy bằng chứng đủ mạnh về dự án thực tế."},
    )
    returned = await approver.post(
        f"/api/v1/staff/decisions/{proposal.json()['decision_id']}/return",
        json={"note": "Hãy xem lại bài luận trước khi loại."},
    )
    assert returned.status_code == 200 and returned.json()["status"] == "IN_ROUND"
    notes = (await reviewer.get("/api/v1/notifications")).json()
    assert any(n["type"] == "decision.returned" for n in notes["items"])

    withdrawn = await applicant.post(f"/api/v1/applications/{app['id']}/withdraw", json={"reason": "Đổi kế hoạch"})
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "WITHDRAWN"
    assert (await applicant.post(f"/api/v1/applications/{app['id']}/withdraw", json={})).status_code == 422
