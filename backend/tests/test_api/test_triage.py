import copy

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.ai.llm_engine import FallbackEngine, LLMEngine
from src.ai.providers import FakeProvider
from src.services import jobs
from tests.conftest import OWNER_URL
from tests.helpers import FULL_SCORES, create_open_intake, good_content, submit_application
from tests.test_services.test_screening import strong_content

GENERIC_ESSAY = (
    "Tôi muốn tham gia chương trình vì nghe nói có phụ cấp và cơ hội việc làm sau khi hoàn thành khoá học. "
    "Tôi nghĩ đây là cơ hội tốt để thay đổi công việc hiện tại và học một lĩnh vực mới cho tương lai của mình."
)


def weak_submittable() -> dict:
    return {
        "education": [{"school": "Trường Y", "major": "Quản trị kinh doanh", "status": "graduated"}],
        "experience": [
            {
                "org": "Cửa hàng Z",
                "role": "Nhân viên bán hàng",
                "years": 2,
                "description": "Bán hàng và chăm sóc khách hàng tại cửa hàng thời trang.",
            }
        ],
        "skills": ["Giao tiếp", "Excel"],
        "essays": {"motivation": GENERIC_ESSAY, "problem_solving": ""},
    }


async def _prepare(login_as, ai: bool = True):  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    intake = await create_open_intake(admin, quota=10, ai=ai)
    apps = {}
    for who, key, content in (
        ("applicant", "strong", strong_content()),
        ("applicant2", "weak", weak_submittable()),
        ("applicant3", "good", good_content()),
    ):
        apps[key] = await submit_application(await login_as(who), intake["id"], name=key, content=content)
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/close")).status_code == 200
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/start")).json()["moved"] == 3
    return admin, intake, apps


async def _run(admin: AsyncClient, intake_id: str, **body):  # type: ignore[no-untyped-def]
    res = await admin.post(f"/api/v1/intakes/{intake_id}/triage", json=body)
    assert res.status_code == 202, res.text
    await jobs.wait_for_all()
    job = (await admin.get(f"/api/v1/jobs/{res.json()['job_id']}")).json()
    return res.json(), job


async def test_triage_scores_batch_and_builds_board(login_as) -> None:  # type: ignore[no-untyped-def]
    admin, intake, apps = await _prepare(login_as)
    started, job = await _run(admin, intake["id"])
    assert started["engine"] == "heuristic" and started["total"] == 3
    assert job["status"] == "done" and job["done"] == 3 and job["total"] == 3
    assert job["result"]["processed"] == 3 and job["result"]["failed"] == 0

    board = (await admin.get(f"/api/v1/intakes/{intake['id']}/triage")).json()
    assert board["scored"] == 3 and board["pool"] == 3
    assert sum(t["count"] for t in board["tiers"].values()) == 3
    scores = [i["total_score"] for i in board["items"]]
    assert scores == sorted(scores, reverse=True)  # xếp theo điểm giảm dần
    by_code = {i["candidate_code"]: i for i in board["items"]}
    strong, weak = by_code[apps["strong"]["candidate_code"]], by_code[apps["weak"]["candidate_code"]]
    assert strong["tier"] == "invite" and weak["tier"] == "decline_likely"
    assert strong["total_score"] > weak["total_score"] + 40
    # admin có pii.read nên thấy tên; lọc theo nhóm hoạt động
    assert {i["name"] for i in board["items"]} == {"strong", "weak", "good"}
    only = (await admin.get(f"/api/v1/intakes/{intake['id']}/triage?tier=invite")).json()["items"]
    assert [i["candidate_code"] for i in only] == [apps["strong"]["candidate_code"]]

    # chạy lại không chấm trùng; force thì chấm lại
    _, again = await _run(admin, intake["id"])
    assert again["total"] == 0
    _, forced = await _run(admin, intake["id"], force=True)
    assert forced["result"]["processed"] == 3


async def test_triage_requires_ai_enabled_and_permissions(login_as) -> None:  # type: ignore[no-untyped-def]
    admin, intake, _ = await _prepare(login_as, ai=False)
    off = await admin.post(f"/api/v1/intakes/{intake['id']}/triage", json={})
    assert off.status_code == 409 and "chưa bật" in off.json()["detail"]

    admin2, intake2, _ = await _prepare(login_as, ai=True)
    reviewer, applicant, approver = await login_as("reviewer"), await login_as("applicant"), await login_as("approver")
    assert (await reviewer.post(f"/api/v1/intakes/{intake2['id']}/triage", json={})).status_code == 403
    assert (await applicant.post(f"/api/v1/intakes/{intake2['id']}/triage", json={})).status_code == 403
    assert (await reviewer.get(f"/api/v1/intakes/{intake2['id']}/triage")).status_code == 403
    assert (
        await approver.get(f"/api/v1/intakes/{intake2['id']}/triage")
    ).status_code == 200  # người phê duyệt được xem
    assert (await reviewer.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")).status_code == 403
    assert (await admin2.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_only_one_triage_job_per_intake_at_a_time(login_as) -> None:  # type: ignore[no-untyped-def]
    admin, intake, _ = await _prepare(login_as)
    first = await admin.post(f"/api/v1/intakes/{intake['id']}/triage", json={})
    second = await admin.post(f"/api/v1/intakes/{intake['id']}/triage", json={})
    assert first.status_code == 202 and second.status_code == 409
    await jobs.wait_for_all()


async def test_reviewer_independence_ai_hidden_until_own_score_submitted(login_as) -> None:  # type: ignore[no-untyped-def]
    admin, intake, apps = await _prepare(login_as)
    await _run(admin, intake["id"])
    reviewer = await login_as("reviewer")
    app_id = apps["strong"]["id"]

    # hàng đợi của reviewer chỉ có cờ trung tính, không có nhóm/điểm của AI
    queue = (await reviewer.get(f"/api/v1/staff/applications?intake_id={intake['id']}")).json()
    for item in queue["items"]:
        assert "ai_tier" not in item and "ai_score" not in item and item["ai_attention"] in (True, False)
    # chi tiết: AI bị khoá cho đến khi reviewer chốt điểm của mình
    locked = (await reviewer.get(f"/api/v1/staff/applications/{app_id}")).json()["ai"]
    assert locked["locked"] is True and "total_score" not in locked

    submit = await reviewer.put(
        f"/api/v1/staff/applications/{app_id}/review",
        json={"scores": FULL_SCORES, "comment": "", "recommendation": "advance", "submit": True},
    )
    assert submit.status_code == 200
    ai = (await reviewer.get(f"/api/v1/staff/applications/{app_id}")).json()["ai"]
    assert ai["tier"] == "invite" and ai["engine"] == "heuristic" and ai["prompt_version"] == "screen-v1"
    assert ai["input_fields"] and not any(f.startswith("profile") for f in ai["input_fields"])
    assert any(e["quote"] for ev in ai["evidence"].values() for e in ev)  # có bằng chứng nguyên văn

    # admin (triage.read) thấy ngay không cần chấm
    admin_view = (await admin.get(f"/api/v1/staff/applications/{app_id}")).json()["ai"]
    assert admin_view["tier"] == "invite"


async def test_duplicate_essays_across_applications_are_flagged(login_as) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin")
    intake = await create_open_intake(admin, ai=True)
    shared = (GENERIC_ESSAY + " ") * 2
    a, b = weak_submittable(), copy.deepcopy(weak_submittable())
    a["essays"]["motivation"] = shared
    b["essays"]["motivation"] = shared
    for who, content in (("applicant", a), ("applicant2", b), ("applicant3", strong_content())):
        await submit_application(await login_as(who), intake["id"], content=content)
    await admin.post(f"/api/v1/intakes/{intake['id']}/close")
    await admin.post(f"/api/v1/intakes/{intake['id']}/start")
    _, job = await _run(admin, intake["id"])
    assert job["result"]["duplicates_flagged"] == 2
    items = (await admin.get(f"/api/v1/intakes/{intake['id']}/triage?attention=true")).json()["items"]
    assert len([i for i in items if i["flag_count"] >= 1]) >= 2


async def test_llm_engine_usage_is_logged_with_cost(login_as, app_instance, orgs) -> None:  # type: ignore[no-untyped-def]
    admin, intake, apps = await _prepare(login_as)

    def fake(system: str, user: str) -> dict:
        crit = [
            {"id": c, "score": 3, "confidence": 0.8, "rationale": "ok", "evidence": []}
            for c in ("projects", "programming", "motivation")
        ]
        return {"criteria": crit, "flags": [], "summary": "Tạm ổn."}

    app_instance.state.screening_engine = FallbackEngine(LLMEngine(FakeProvider(fake, model="claude-opus-5-5")))
    try:
        started, job = await _run(admin, intake["id"])
    finally:
        app_instance.state.screening_engine = None
    assert started["engine"] == "llm:fake" and job["result"]["processed"] == 3 and job["result"]["cost_usd"] > 0

    eng = create_async_engine(OWNER_URL)
    async with eng.connect() as conn:
        # RLS áp dụng cả với chủ sở hữu bảng (FORCE), nên cần đặt ngữ cảnh tổ chức.
        await conn.execute(text("SELECT set_config('app.org_id', :o, false)"), {"o": str(orgs["alpha"].id)})
        rows = (
            await conn.execute(
                text("SELECT model, feature, cost_usd FROM ai_usage WHERE job_id = :j"), {"j": started["job_id"]}
            )
        ).all()
    await eng.dispose()
    assert len(rows) == 3 and all(r[0] == "claude-opus-5-5" and r[1] == "screening" and r[2] > 0 for r in rows)
