"""Quét IDOR chéo tổ chức: mọi endpoint nhận ID đều phải coi ID của tổ chức khác như không tồn tại.

Khác với kiểm thử quyền (RBAC), ở đây người gọi CÓ quyền ở tổ chức của mình: nếu endpoint trả 2xx cho ID của
tổ chức A khi gọi từ tổ chức B thì dữ liệu đã rò rỉ qua lớp cách ly (RLS hoặc truy vấn thiếu điều kiện).
"""

import base64
import re
import uuid
from typing import Any

import pytest

from tests.helpers import FULL_SCORES, create_open_intake, submit_application

ROLES = ("admin", "reviewer", "approver", "cohort_manager", "training_manager", "mentor", "applicant")
PARAM = re.compile(r"\{(\w+)\}")
# Điểm vào công khai, không gắn với dữ liệu tổ chức qua ID
PUBLIC_PREFIXES = ("/api/v1/auth/",)


async def _alpha_ids(login_as: Any) -> dict[str, str]:
    admin = await login_as("admin")
    intake = await create_open_intake(admin)
    applicant = await login_as("applicant")
    app = await submit_application(applicant, intake["id"])
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/close")).status_code == 200
    assert (await admin.post(f"/api/v1/intakes/{intake['id']}/start")).status_code == 200
    reviewer = await login_as("reviewer")
    base = f"/api/v1/staff/applications/{app['id']}"
    await reviewer.put(
        f"{base}/review",
        json={"scores": FULL_SCORES, "comment": "Tốt, đủ dự án thực tế.", "recommendation": "advance", "submit": True},
    )
    version = (await reviewer.get(base)).json()["version"]
    proposal = await reviewer.post(
        f"{base}/proposals",
        json={"version": version, "outcome": "accepted", "reason": "Dự án thực tế tốt, đạt các tiêu chí chính."},
    )
    assert proposal.status_code == 201, proposal.text
    doc = await admin.post(
        "/api/v1/admin/documents",
        json={
            "title": "Tài liệu A",
            "visibility": "public",
            "filename": "a.txt",
            "content_base64": base64.b64encode(
                f"Tài liệu thử nghiệm {uuid.uuid4()} cho kiểm tra cách ly.".encode()
            ).decode(),
        },
    )
    cost = await admin.post(
        "/api/v1/admin/costs/entries", json={"category": "operations", "amount_vnd": 1000, "occurred_on": "2026-01-01"}
    )
    users = (await admin.get("/api/v1/admin/users?q=reviewer@alpha.test")).json()["items"]
    return {
        "intake_id": intake["id"],
        "program_id": intake["program_id"],
        "cohort_id": intake["cohort_id"],
        "application_id": app["id"],
        "decision_id": proposal.json()["decision_id"],
        "doc_id": doc.json()["id"],
        "entry_id": cost.json()["id"],
        "membership_id": users[0]["membership_id"],
    }


def _endpoints(app_openapi: dict[str, Any]) -> list[tuple[str, str]]:
    out = []
    for path, ops in app_openapi["paths"].items():
        if not PARAM.search(path) or path.startswith(PUBLIC_PREFIXES):
            continue
        out.extend((method.upper(), path) for method in ops if method in ("get", "post", "put", "patch", "delete"))
    return out


async def test_no_endpoint_serves_another_organisations_objects(login_as: Any, app_instance: Any) -> None:
    ids = await _alpha_ids(login_as)
    endpoints = _endpoints(app_instance.openapi())
    assert len(endpoints) > 40  # đủ rộng: không bỏ sót vì lỗi phân tích đường dẫn

    leaks: list[str] = []
    for role in ROLES:
        beta = await login_as(role, "beta")
        for method, template in endpoints:
            url = PARAM.sub(lambda m: ids.get(m.group(1), str(uuid.uuid4())), template)
            res = await beta.request(method, url, json={} if method != "GET" else None)
            if 200 <= res.status_code < 300:
                leaks.append(f"{role}@beta {method} {template} -> {res.status_code}")
    assert leaks == [], "\n".join(leaks)


@pytest.mark.parametrize(
    "path",
    ["/api/v1/staff/applications", "/api/v1/analytics/funnel", "/api/v1/analytics/fairness", "/api/v1/staff/approvals"],
)
async def test_listing_with_foreign_intake_id_returns_nothing(login_as: Any, path: str) -> None:
    ids = await _alpha_ids(login_as)
    beta = await login_as("admin", "beta")
    approver = await login_as("approver", "beta")
    for client in (beta, approver):
        res = await client.get(f"{path}?intake_id={ids['intake_id']}")
        if res.status_code == 200:
            body = res.json()
            assert body in ([], {}) or body.get("items") == [] or body.get("total") == 0, (path, body)
        else:
            assert res.status_code in (403, 404, 422)


# Điểm vào cố ý công khai (đăng nhập, lời mời, đăng nhập Microsoft, thông tin tổ chức để dựng trang đăng nhập)
PUBLIC = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/invitations/{token}"),
    ("POST", "/api/v1/auth/invitations/accept"),
    ("GET", "/api/v1/auth/microsoft/start"),
    ("GET", "/api/v1/auth/microsoft/callback"),
    ("GET", "/api/v1/org"),
}


async def test_every_other_endpoint_requires_authentication(client: Any, app_instance: Any) -> None:
    """Thêm endpoint mới mà quên gắn quyền sẽ làm test này đỏ: mặc định là đóng."""
    unprotected: list[str] = []
    checked = 0
    for path, ops in app_instance.openapi()["paths"].items():
        for method in ops:
            verb = method.upper()
            if verb not in ("GET", "POST", "PUT", "PATCH", "DELETE") or (verb, path) in PUBLIC:
                continue
            url = PARAM.sub(lambda m: str(uuid.uuid4()), path)
            res = await client.request(
                verb, url, json={} if verb != "GET" else None, headers={"X-Organization": "alpha"}
            )
            checked += 1
            if res.status_code not in (401, 403):
                unprotected.append(f"{verb} {path} -> {res.status_code}")
    assert checked > 80
    assert unprotected == [], "\n".join(unprotected)
