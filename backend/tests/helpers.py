"""Hàm dựng dữ liệu dùng chung cho test nghiệp vụ."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

ROUNDS = [
    {"key": "portfolio", "label": "Xét hồ sơ", "type": "review"},
    {"key": "aptitude", "label": "Đánh giá năng lực", "type": "assessment"},
]

CRITERIA = [
    {"id": "projects", "name": "Dự án thực tế", "description": "", "weight": 3, "max": 5, "kind": "projects"},
    {"id": "programming", "name": "Lập trình", "description": "", "weight": 2, "max": 5, "kind": "programming"},
    {"id": "motivation", "name": "Động lực", "description": "", "weight": 1, "max": 5, "kind": "motivation"},
]

ESSAY = (
    "Tôi muốn tham gia chương trình vì đã xây dựng một hệ thống phân loại tài liệu bằng Python và FastAPI cho "
    "câu lạc bộ sinh viên, và muốn học cách đưa mô hình AI vào sản phẩm thật cùng các kỹ sư giàu kinh nghiệm."
)


def good_content() -> dict[str, Any]:
    return {
        "education": [
            {
                "school": "Đại học Bách Khoa",
                "major": "Khoa học máy tính",
                "status": "final_year",
                "year": 2026,
                "gpa": 8.3,
            }
        ],
        "experience": [
            {
                "org": "Startup A",
                "role": "Thực tập AI",
                "years": 0.5,
                "description": "Huấn luyện mô hình phân loại văn bản",
            }
        ],
        "projects": [
            {
                "title": "Phân loại tài liệu",
                "description": "Xây dựng API FastAPI và mô hình PyTorch phân loại văn bản tiếng Việt, triển khai bằng Docker.",
                "link": "https://github.com/example/doc-classifier",
                "tech": ["Python", "FastAPI", "PyTorch"],
            }
        ],
        "skills": ["Python", "SQL", "Machine Learning"],
        "essays": {
            "motivation": ESSAY,
            "problem_solving": "Tôi chia vấn đề thành bước nhỏ, đo lường rồi cải tiến dần.",
        },
        "links": {"github": "https://github.com/example"},
    }


def good_profile(name: str = "Nguyễn Văn A") -> dict[str, Any]:
    return {"full_name": name, "phone": "0901234567", "gender": "undisclosed", "city": "Hà Nội"}


async def create_open_intake(admin: AsyncClient, *, quota: int = 5, name: str | None = None) -> dict[str, Any]:
    """Tạo chương trình, khoá, đợt tuyển, rubric cho cả hai vòng rồi mở đợt."""
    code = f"p{uuid.uuid4().hex[:8]}"
    program = (await admin.post("/api/v1/programs", json={"code": code, "name_vi": "Chương trình thử"})).json()
    cohort = (
        await admin.post(
            f"/api/v1/programs/{program['id']}/cohorts", json={"code": "K1", "name": "Khoá 1", "capacity": quota}
        )
    ).json()
    now = datetime.now(UTC)
    res = await admin.post(
        "/api/v1/intakes",
        json={
            "program_id": program["id"],
            "cohort_id": cohort["id"],
            "name": name or f"Đợt {code}",
            "opens_at": (now - timedelta(hours=1)).isoformat(),
            "closes_at": (now + timedelta(days=7)).isoformat(),
            "quota": quota,
            "rounds": ROUNDS,
            "eligibility_rules": [
                {
                    "id": "final_year",
                    "label": "Sinh viên năm cuối hoặc đã tốt nghiệp",
                    "type": "education_status_in",
                    "values": ["final_year", "graduated"],
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    intake = res.json()
    for rnd in ROUNDS:
        put = await admin.put(f"/api/v1/intakes/{intake['id']}/rubrics/{rnd['key']}", json={"criteria": CRITERIA})
        assert put.status_code == 200, put.text
    pub = await admin.post(f"/api/v1/intakes/{intake['id']}/publish")
    assert pub.status_code == 200, pub.text
    return pub.json()


async def submit_application(
    applicant: AsyncClient, intake_id: str, *, name: str = "Nguyễn Văn A", content: dict[str, Any] | None = None
) -> dict[str, Any]:
    created = await applicant.post("/api/v1/applications", json={"intake_id": intake_id})
    assert created.status_code == 201, created.text
    app = created.json()
    saved = await applicant.patch(
        f"/api/v1/applications/{app['id']}", json={"profile": good_profile(name), "content": content or good_content()}
    )
    assert saved.status_code == 200, saved.text
    done = await applicant.post(f"/api/v1/applications/{app['id']}/submit", json={"consent": True})
    assert done.status_code == 200, done.text
    return done.json()


FULL_SCORES = {"projects": 4, "programming": 4, "motivation": 3}
