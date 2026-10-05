"""Sinh dữ liệu TỔNG HỢP để demo và kiểm thử. Toàn bộ người, hồ sơ, điểm và kết quả ở đây là giả.

Mô hình sinh: mỗi ứng viên có hai biến ẩn độc lập: `skill` (năng lực kỹ thuật) và `drive` (động lực thể hiện qua bài luận).
Kết quả đào tạo phụ thuộc chủ yếu vào `skill`, gần như không phụ thuộc `drive`. Nhờ vậy Rubric Lab có thứ để phát hiện:
tiêu chí dự án/lập trình có giá trị dự báo, tiêu chí động lực thì không. Điểm chấm bài luận cố ý có một độ lệch nhỏ theo giới
để minh hoạ kiểm tra công bằng. Không dùng số liệu sinh ở đây làm bằng chứng hiệu quả của chương trình thật.
"""

import math
import random
from dataclasses import dataclass
from typing import Any

FAMILY = [
    "Nguyễn",
    "Trần",
    "Lê",
    "Phạm",
    "Hoàng",
    "Huỳnh",
    "Phan",
    "Vũ",
    "Võ",
    "Đặng",
    "Bùi",
    "Đỗ",
    "Hồ",
    "Ngô",
    "Dương",
    "Lý",
]
MIDDLE_F = ["Thị", "Ngọc", "Thu", "Khánh", "Bảo", "Minh", "Phương", "Thanh"]
MIDDLE_M = ["Văn", "Đức", "Hữu", "Quốc", "Minh", "Anh", "Gia", "Thanh"]
GIVEN_F = ["Linh", "Trang", "Hà", "Lan", "Ngọc", "Mai", "Hương", "Thảo", "Vy", "Nhi", "Quyên", "Yến", "Chi", "Hạnh"]
GIVEN_M = ["Nam", "Hùng", "Dũng", "Khoa", "Long", "Phúc", "Tuấn", "Việt", "Bách", "Đạt", "Huy", "Sơn", "Thái", "Kiên"]
CITIES = ["Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Huế", "Nghệ An", "Thái Nguyên"]
SCHOOLS = [
    "Đại học Bách Khoa Hà Nội",
    "Đại học Công nghệ - ĐHQGHN",
    "Đại học Bách Khoa TP.HCM",
    "Đại học Khoa học Tự nhiên TP.HCM",
    "Học viện Công nghệ Bưu chính Viễn thông",
    "Đại học FPT",
    "Đại học Kinh tế Quốc dân",
    "Đại học Sư phạm Kỹ thuật TP.HCM",
    "Đại học Đà Nẵng",
    "Đại học Cần Thơ",
    "Đại học Khoa học Huế",
    "Đại học Thăng Long",
]
TECH_MAJORS = ["Khoa học máy tính", "Công nghệ thông tin", "Kỹ thuật phần mềm", "Khoa học dữ liệu", "An toàn thông tin"]
OTHER_MAJORS = ["Quản trị kinh doanh", "Kinh tế", "Toán ứng dụng", "Điện tử viễn thông", "Ngôn ngữ Anh", "Marketing"]
LANGS = ["Python", "Java", "JavaScript", "TypeScript", "C++", "Go", "SQL", "Kotlin"]
TOOLS = ["Docker", "Git", "Linux", "FastAPI", "React", "PostgreSQL", "Redis", "Kubernetes", "AWS"]
AI_TERMS = ["PyTorch", "TensorFlow", "scikit-learn", "Hugging Face", "LangChain", "RAG", "NLP", "computer vision"]
PROJECT_SUBJECTS = [
    "phân loại văn bản tiếng Việt",
    "hệ thống gợi ý sản phẩm",
    "chatbot hỗ trợ sinh viên",
    "nhận diện ký tự viết tay",
    "dự báo nhu cầu bán hàng",
    "phát hiện giao dịch bất thường",
    "tóm tắt tin tức tự động",
    "tìm kiếm tài liệu bằng RAG",
    "phân tích cảm xúc đánh giá khách hàng",
    "trợ lý lập trình nội bộ",
    "giám sát chất lượng dữ liệu",
    "tối ưu lịch học",
]
ESSAY_GENERIC = [
    "Tôi rất đam mê công nghệ và mong muốn được học hỏi trong môi trường chuyên nghiệp. Tôi là người chăm chỉ, cầu tiến và luôn nỗ lực hết mình.",
    "Chương trình có phụ cấp và cơ hội việc làm nên tôi muốn đăng ký. Tôi tin rằng đây là cơ hội tốt để phát triển bản thân trong tương lai.",
]
ESSAY_SPECIFIC = [
    "Tôi đã xây dựng {proj} bằng {lang} và muốn học cách đưa mô hình AI vào sản phẩm thật. Mục tiêu của tôi là triển khai một hệ thống phục vụ "
    "người dùng thật và đo lường chất lượng bằng bộ dữ liệu kiểm thử, rồi cải tiến theo từng vòng.",
    "Sau khi hoàn thành dự án {proj}, tôi nhận ra khoảng cách giữa mô hình trong notebook và hệ thống chạy ổn định. Tôi muốn làm việc cùng kỹ sư "
    "giàu kinh nghiệm để học triển khai, giám sát và đánh đổi giữa độ chính xác và chi phí.",
]
METHOD_TEXT = [
    "Khi gặp lỗi, trước hết tôi tái hiện lỗi, sau đó đặt giả thuyết và đo lường từng thay đổi. Tôi so sánh hai phương án, ghi lại đánh đổi rồi lặp lại cho đến khi chỉ số cải thiện.",
    "Tôi chia vấn đề thành các bước nhỏ, viết kiểm thử cho từng bước và phân tích kết quả trước khi chuyển sang bước tiếp theo.",
]
WEAK_PS = ["Tôi sẽ cố gắng hết sức để giải quyết vấn đề.", ""]


@dataclass(frozen=True)
class Person:
    full_name: str
    gender: str
    city: str
    skill: float
    drive: float


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def make_person(rng: random.Random) -> Person:
    female = rng.random() < 0.42
    name = f"{rng.choice(FAMILY)} {rng.choice(MIDDLE_F if female else MIDDLE_M)} {rng.choice(GIVEN_F if female else GIVEN_M)}"
    return Person(
        full_name=name,
        gender="female" if female else "male",
        city=rng.choices(CITIES, weights=[26, 30, 9, 7, 6, 5, 9, 8])[0],
        skill=clip(rng.betavariate(2.4, 2.6)),
        drive=clip(rng.betavariate(2.6, 2.4)),
    )


def make_content(rng: random.Random, p: Person) -> dict[str, Any]:
    tech_major = rng.random() < 0.35 + 0.5 * p.skill
    major = rng.choice(TECH_MAJORS if tech_major else OTHER_MAJORS)
    gpa = round(clip(5.8 + 3.6 * (0.5 * p.skill + 0.3 * p.drive + 0.2 * rng.random()), 5, 10), 1)
    n_projects = max(0, min(4, round(p.skill * 3.2 + rng.gauss(0, 0.6))))
    langs = rng.sample(LANGS, k=max(1, min(len(LANGS), round(1 + p.skill * 4 + rng.gauss(0, 0.7)))))
    tools = rng.sample(TOOLS, k=max(0, min(len(TOOLS), round(p.skill * 4 + rng.gauss(0, 0.8)))))
    ai = rng.sample(AI_TERMS, k=max(0, min(len(AI_TERMS), round(p.skill * 3.2 + rng.gauss(0, 0.8)))))
    projects = []
    for i in range(n_projects):
        subject = rng.choice(PROJECT_SUBJECTS)
        tech = rng.sample(langs + tools + ai, k=min(len(langs + tools + ai), 2 + rng.randint(0, 3)))
        detail = (
            f"Xây dựng {subject} bằng {', '.join(tech[:3])}. "
            + (
                "Triển khai bằng Docker và đo lường độ chính xác trên bộ dữ liệu kiểm thử, đạt "
                + f"{60 + int(35 * p.skill)}% sau nhiều vòng cải tiến. "
                if p.skill > 0.45
                else ""
            )
            + ("Có người dùng thật là bạn học trong lớp. " if rng.random() < p.skill else "")
        )
        projects.append(
            {
                "title": f"Dự án {subject}",
                "description": detail[:1900] if p.skill > 0.25 else f"Bài tập môn học về {subject}.",
                "link": f"https://github.com/demo-{rng.randrange(10**6)}/project-{i}"
                if rng.random() < 0.35 + 0.6 * p.skill
                else None,
                "tech": tech,
            }
        )
    essays_m = (
        rng.choice(ESSAY_SPECIFIC).format(proj=rng.choice(PROJECT_SUBJECTS), lang=rng.choice(langs))
        if p.drive > 0.45 and p.skill > 0.2
        else rng.choice(ESSAY_GENERIC)
    )
    essays_m += " " + ("Tôi đã tìm hiểu kỹ chương trình và lộ trình ba giai đoạn. " * (1 if p.drive > 0.3 else 0))
    if len(essays_m) < 220:
        essays_m += " Tôi mong được tham gia để học hỏi và đóng góp cho các dự án thực tế của chương trình."
    experience = []
    if rng.random() < 0.15 + 0.6 * p.skill:
        experience.append(
            {
                "org": rng.choice(["Startup FinTech A", "Công ty phần mềm B", "Viện nghiên cứu C", "CLB AI trường"]),
                "role": rng.choice(["Thực tập sinh AI", "Thực tập sinh Backend", "Cộng tác viên dữ liệu"]),
                "years": round(0.3 + 1.8 * p.skill * rng.random(), 1),
                "description": f"Làm việc với {', '.join(rng.sample(langs + tools, k=min(2, len(langs + tools))))} trong các tác vụ xử lý dữ liệu và xây dựng API.",
            }
        )
    track_pool = ["ai_products", "ai_infrastructure", "ai_applications"]
    infra_lean = len([t for t in tools if t in ("Docker", "Kubernetes", "Linux", "AWS")])
    product_lean = 1 if not tech_major else 0
    weights = [1 + 2 * product_lean, 1 + infra_lean, 1 + len(ai)]
    prefs: list[str] = []
    while len(prefs) < rng.randint(1, 3):
        choice = rng.choices(track_pool, weights=weights)[0]
        if choice not in prefs:
            prefs.append(choice)
    return {
        "education": [
            {
                "school": rng.choice(SCHOOLS),
                "major": major,
                "degree": "Cử nhân",
                "status": rng.choices(
                    ["final_year", "graduated", "student"], weights=[5, 4, 1 if p.skill > 0.3 else 2]
                )[0],
                "year": rng.choice([2025, 2026]),
                "gpa": gpa,
            }
        ],
        "experience": experience,
        "projects": projects,
        "skills": (langs + tools[:3] + ai[:2])[:10] or ["Excel"],
        "essays": {
            "motivation": essays_m.strip(),
            "problem_solving": rng.choice(METHOD_TEXT) if p.skill > 0.5 else rng.choice(WEAK_PS),
        },
        "links": {"github": f"https://github.com/demo-{rng.randrange(10**6)}"}
        if rng.random() < 0.3 + 0.5 * p.skill
        else {},
        "preferences": {"tracks": prefs},
    }


def review_scores(rng: random.Random, p: Person, criteria: list[dict[str, Any]]) -> dict[str, float]:
    """Điểm reviewer theo từng tiêu chí; bài luận (motivation) bị lệch nhẹ theo giới để minh hoạ kiểm tra công bằng."""
    loading = {
        "projects": (0.85, 0.1),
        "programming": (0.85, 0.1),
        "ai_ml": (0.8, 0.1),
        "data": (0.75, 0.1),
        "education": (0.55, 0.3),
        "experience": (0.6, 0.1),
        "motivation": (0.05, 0.85),
        "problem_solving": (0.7, 0.2),
        "communication": (0.2, 0.7),
    }
    out: dict[str, float] = {}
    for c in criteria:
        s_w, d_w = loading.get(c.get("kind", "custom"), (0.5, 0.3))
        base = s_w * p.skill + d_w * p.drive + (1 - s_w - d_w) * 0.5
        if c.get("kind") in ("motivation", "communication") and p.gender == "male":
            base += 0.05
        value = clip(base + rng.gauss(0, 0.1))
        out[c["id"]] = round(value * c["max"] * 2) / 2
    return out


def outcome_probability(p: Person) -> float:
    """Xác suất đạt yêu cầu cuối khoá: phụ thuộc năng lực, gần như không phụ thuộc động lực."""
    return 1 / (1 + math.exp(-(7.5 * (p.skill - 0.5) + 1.2 * (p.drive - 0.5) + 0.3)))
