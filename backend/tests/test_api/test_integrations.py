"""Tích hợp bằng khoá API: quản lý khoá, phạm vi, export CSV (Power BI), LMS (roster + đẩy đánh giá), CRM (luồng thay đổi)."""

import csv
import io

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

DELTA = "delta"


def external(app: FastAPI, token: str | None) -> AsyncClient:
    """Client của hệ thống ngoài: không cookie, chỉ có khoá Bearer."""
    headers = {"X-Organization": DELTA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


async def make_key(admin: AsyncClient, scopes: list[str], name: str = "Power BI") -> str:
    res = await admin.post("/api/v1/integrations/keys", json={"name": name, "scopes": scopes})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token"].startswith("thk_" + body["key"]["prefix"]) and body["key"]["scopes"] == sorted(scopes)
    return str(body["token"])


async def test_admin_manages_keys_and_tokens_are_shown_once(login_as, training_env) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", DELTA)
    token = await make_key(admin, ["export.read"], name="Khoá xem")
    listed = (await admin.get("/api/v1/integrations/keys")).json()
    mine = next(k for k in listed if k["name"] == "Khoá xem")
    assert "token" not in mine and mine["revoked_at"] is None and mine["last_used_at"] is None
    assert token not in str(listed)

    bad = await admin.post("/api/v1/integrations/keys", json={"name": "x", "scopes": ["admin.all"]})
    assert bad.status_code == 422
    reviewer = await login_as("reviewer", DELTA)
    assert (await reviewer.get("/api/v1/integrations/keys")).status_code == 403
    assert (
        await reviewer.post("/api/v1/integrations/keys", json={"name": "Khoá lạ", "scopes": ["crm.read"]})
    ).status_code == 403

    revoked = await admin.post(f"/api/v1/integrations/keys/{mine['id']}/revoke")
    assert revoked.status_code == 200 and revoked.json()["revoked_at"] is not None


async def test_power_bi_exports_are_deidentified_and_scope_checked(login_as, training_env, app_instance) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", DELTA)
    token = await make_key(admin, ["export.read"])
    async with external(app_instance, token) as bi:
        apps = await bi.get("/api/v1/integrations/exports/applications.csv")
        assert apps.status_code == 200 and apps.headers["content-type"].startswith("text/csv")
        table = rows(apps.text)
        assert table and {"candidate_code", "status", "gender", "region", "ai_tier"} <= set(table[0])
        assert not {"full_name", "email", "phone"} & set(table[0])  # khử định danh
        attainment = rows((await bi.get("/api/v1/integrations/exports/competency_attainment.csv")).text)
        assert attainment and {"competency_code", "target_level", "latest_level", "met"} <= set(attainment[0])
        assert {r["met"] for r in attainment} <= {"0", "1", ""}
        enrollments = rows((await bi.get("/api/v1/integrations/exports/enrollments.csv")).text)
        assert enrollments and enrollments[0]["cohort_code"]
        assert (await bi.get("/api/v1/integrations/exports/secrets.csv")).status_code == 404
        assert (await bi.get("/api/v1/integrations/lms/roster?cohort=K1")).status_code == 403  # sai phạm vi

    listed = (await admin.get("/api/v1/integrations/keys")).json()
    assert next(k for k in listed if k["name"] == "Power BI")["last_used_at"] is not None
    # Admin tải trực tiếp bằng phiên đăng nhập (quyền export.read), không cần khoá.
    assert (await admin.get("/api/v1/integrations/exports/enrollments.csv")).status_code == 200
    applicant = await login_as("applicant", DELTA)
    assert (await applicant.get("/api/v1/integrations/exports/applications.csv")).status_code == 403

    async with external(app_instance, None) as anon:
        assert (await anon.get("/api/v1/integrations/exports/applications.csv")).status_code == 401
    async with external(app_instance, "thk_khong_hop_le") as fake:
        assert (await fake.get("/api/v1/integrations/exports/applications.csv")).status_code == 401


async def test_lms_roster_and_idempotent_assessment_push(login_as, training_env, app_instance) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", DELTA)
    token = await make_key(admin, ["lms.read", "lms.write"], name="LMS Moodle")
    async with external(app_instance, token) as lms:
        roster = await lms.get("/api/v1/integrations/lms/roster?cohort=K1")
        assert roster.status_code == 200, roster.text
        learner = next(r for r in roster.json() if r["track"])
        assert learner["email"] and learner["candidate_code"]
        assert (await lms.get("/api/v1/integrations/lms/roster?cohort=KHONG_CO")).status_code == 404

        payload = {
            "items": [
                {
                    "external_ref": "moodle-1",
                    "candidate_code": learner["candidate_code"],
                    "competency_code": "programming",
                    "level": 5,
                    "evidence": "Bài kiểm tra cuối học phần",
                },
                {
                    "external_ref": "moodle-2",
                    "candidate_code": "KHONG-CO",
                    "competency_code": "programming",
                    "level": 3,
                },
                {
                    "external_ref": "moodle-3",
                    "candidate_code": learner["candidate_code"],
                    "competency_code": "bay_luon",
                    "level": 3,
                },
                {
                    "external_ref": "moodle-4",
                    "candidate_code": learner["candidate_code"],
                    "competency_code": "programming",
                    "level": 9,
                },
            ]
        }
        first = (await lms.post("/api/v1/integrations/lms/assessments", json=payload)).json()
        assert first["created"] == 1 and first["duplicates"] == 0
        assert [e["error"] for e in first["errors"]] == [
            "unknown_candidate",
            "unknown_competency",
            "level_out_of_range",
        ]
        again = (await lms.post("/api/v1/integrations/lms/assessments", json=payload)).json()
        assert again["created"] == 0 and again["duplicates"] == 1  # gửi lại không tạo trùng

    # Đánh giá từ LMS hiện trong ma trận năng lực, ghi nhận tác nhân là tài khoản dịch vụ của khoá.
    manager = await login_as("training_manager", DELTA)
    matrix = (await manager.get(f"/api/v1/enrollments/{learner['enrollment_id']}/competencies")).json()
    assert str(matrix).count("Bài kiểm tra cuối học phần") == 1
    logs = (await admin.get("/api/v1/audit-logs?action=integration.lms_assessments")).json()["items"]
    assert logs and logs[0]["action"] == "integration.lms_assessments"


async def test_crm_change_feed_pages_by_cursor(login_as, training_env, app_instance) -> None:  # type: ignore[no-untyped-def]
    admin = await login_as("admin", DELTA)
    token = await make_key(admin, ["crm.read"], name="HubSpot")
    async with external(app_instance, token) as crm:
        first = (await crm.get("/api/v1/integrations/crm/applications?limit=5")).json()
        assert len(first["items"]) == 5 and first["next_cursor"]
        assert first["items"][0]["email"] and first["items"][0]["status"] != "DRAFT"
        second = (
            await crm.get("/api/v1/integrations/crm/applications", params={"limit": 5, "cursor": first["next_cursor"]})
        ).json()
        assert {i["application_id"] for i in first["items"]}.isdisjoint({i["application_id"] for i in second["items"]})
        future = (
            await crm.get("/api/v1/integrations/crm/applications", params={"updated_since": "2999-01-01T00:00:00Z"})
        ).json()
        assert future == {"items": [], "next_cursor": None}
        assert (await crm.get("/api/v1/integrations/crm/applications?cursor=hong")).status_code == 422
        assert (await crm.get("/api/v1/integrations/exports/applications.csv")).status_code == 403

    # Thu hồi thì khoá hết hiệu lực ngay.
    key_id = next(k["id"] for k in (await admin.get("/api/v1/integrations/keys")).json() if k["name"] == "HubSpot")
    await admin.post(f"/api/v1/integrations/keys/{key_id}/revoke")
    async with external(app_instance, token) as crm:
        assert (await crm.get("/api/v1/integrations/crm/applications")).status_code == 401
