"""Đo độ trễ các endpoint chính trên dữ liệu minh hoạ đã nạp (make seed-demo) và backend đang chạy.

Dùng: python tools/bench_api.py [--base http://localhost:8000] [--org northwind] [--runs 20]
In bảng p50/p95/max (ms) theo endpoint. Chỉ đọc, trừ POST phân tích Rubric Lab, Composer và hỏi trợ lý (không đổi dữ liệu nghiệp vụ).
"""

import argparse
import statistics
import sys
import time
from typing import Any

import httpx

PASSWORD = "Passw0rd!dev"


def login(client: httpx.Client, org: str, role: str) -> httpx.Client:
    c = httpx.Client(
        base_url=client.base_url, headers={"X-Organization": org, "Origin": "http://localhost:3000"}, timeout=60
    )
    r = c.post("/api/v1/auth/login", json={"email": f"{role}@{org}.test", "password": PASSWORD})
    r.raise_for_status()
    return c


def timed(fn: Any, runs: int) -> list[float]:
    out = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--org", default="northwind")
    ap.add_argument("--runs", type=int, default=20)
    args = ap.parse_args()
    base = httpx.Client(base_url=args.base)
    admin, reviewer, approver, manager, trainer, applicant = (
        login(base, args.org, r)
        for r in ("admin", "reviewer", "approver", "cohort_manager", "training_manager", "applicant")
    )

    intakes = admin.get("/api/v1/intakes").json()
    with_apps = max(intakes, key=lambda i: sum(i["counts"].values()))
    history = [
        i
        for i in intakes
        if i["name"].startswith("[Minh hoạ]") and (i["counts"].get("ACCEPTED") or i["counts"].get("ENROLLED"))
    ]
    done = history[0] if history else with_apps
    programs = admin.get("/api/v1/programs").json()
    cohorts = [c for p in programs for c in p["cohorts"]]
    big = next((c for c in cohorts if c["code"] == "K3"), cohorts[0])
    # Khoá có học viên đang học để chạy Composer: chọn khoá có nhiều học viên đang học nhất.
    active = {
        c["id"]: admin.get(f"/api/v1/cohorts/{c['id']}/overview").json()["enrollments"].get("active", 0)
        for c in cohorts
    }
    composer_cohort = max(active, key=lambda k: active[k])
    iid, did, cid = with_apps["id"], done["id"], big["id"]
    pool = sum(with_apps["counts"].values())

    cases: list[tuple[str, Any]] = [
        (
            f"Hàng đợi hồ sơ, trang đầu ({pool} hồ sơ trong đợt)",
            lambda: reviewer.get(f"/api/v1/staff/applications?intake_id={iid}&limit=50"),
        ),
        ("Hàng đợi: tìm theo mã", lambda: reviewer.get(f"/api/v1/staff/applications?intake_id={iid}&q=A-1B")),
        (
            "Hàng đợi: lọc 'ưu tiên xem kỹ'",
            lambda: reviewer.get(f"/api/v1/staff/applications?intake_id={iid}&needs_attention=true&limit=50"),
        ),
        (
            "Bàn làm việc: mở một hồ sơ",
            lambda: reviewer.get(
                f"/api/v1/staff/applications/{reviewer.get(f'/api/v1/staff/applications?intake_id={iid}&limit=1').json()['items'][0]['id']}"
            ),
        ),
        ("Bảng triage AI", lambda: admin.get(f"/api/v1/intakes/{iid}/triage?limit=25")),
        ("Phễu tuyển sinh", lambda: reviewer.get(f"/api/v1/analytics/funnel?intake_id={did}")),
        ("Giám sát công bằng", lambda: reviewer.get(f"/api/v1/analytics/fairness?intake_id={did}")),
        (
            "Rubric Lab (3 đợt, ~450 học viên có kết quả)",
            lambda: reviewer.post("/api/v1/analytics/lab", json={"intake_ids": [i["id"] for i in history]}),
        ),
        ("Tổng quan khoá học", lambda: manager.get(f"/api/v1/cohorts/{cid}/overview")),
        ("Danh sách học viên (25/trang)", lambda: manager.get(f"/api/v1/cohorts/{cid}/enrollments?limit=25")),
        ("Báo cáo xét đạt (cả khoá)", lambda: manager.get(f"/api/v1/cohorts/{cid}/qualification")),
        ("Phụ cấp", lambda: manager.get(f"/api/v1/cohorts/{cid}/stipends")),
        (
            "Composer: chạy bộ giải cho cả khoá",
            lambda: manager.post(
                f"/api/v1/cohorts/{composer_cohort}/composer/runs", json={"class_count": 3, "class_mode": "balanced"}
            ),
        ),
        ("Admin: danh sách tài khoản", lambda: admin.get("/api/v1/admin/users?audience=staff&limit=25")),
        (
            "Admin: tìm tài khoản ứng viên (hàng nghìn)",
            lambda: admin.get("/api/v1/admin/users?audience=applicant&q=demo&limit=25"),
        ),
        ("Admin: tổng quan hệ thống", lambda: admin.get("/api/v1/admin/overview")),
        ("Admin: tóm tắt chi phí", lambda: admin.get("/api/v1/admin/costs/summary")),
        ("Nhật ký hoạt động", lambda: admin.get("/api/v1/audit-logs?limit=25")),
        (
            "Trợ lý hỏi đáp (offline)",
            lambda: applicant.post("/api/v1/assistant/ask", json={"question": "Phụ cấp hàng tháng là bao nhiêu?"}),
        ),
        ("Phê duyệt: danh sách chờ", lambda: approver.get("/api/v1/staff/approvals")),
        ("Thông tin người dùng /me", lambda: reviewer.get("/api/v1/me")),
    ]

    print(f"Dữ liệu: đợt lớn nhất {pool} hồ sơ; khoá '{big['code']}'; {args.runs} lượt mỗi endpoint\n")
    print(f"{'Endpoint':<62}{'p50':>8}{'p95':>8}{'max':>8}  trạng thái")
    worst: list[tuple[float, str]] = []
    for name, call in cases:
        # Khởi động nguội một lần, không tính vào số đo.
        probe = call()
        status = probe.status_code
        times = sorted(timed(call, args.runs))
        p50, p95 = statistics.median(times), times[int(len(times) * 0.95) - 1]
        worst.append((p95, name))
        flag = "" if status < 400 else "  LỖI"
        print(f"{name:<62}{p50:>8.1f}{p95:>8.1f}{times[-1]:>8.1f}  {status}{flag}")
    print("\nChậm nhất (p95):", ", ".join(f"{n} {p:.0f}ms" for p, n in sorted(worst, reverse=True)[:3]))


if __name__ == "__main__":
    main()
