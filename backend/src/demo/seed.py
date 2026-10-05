"""Nạp dữ liệu minh hoạ cho một tổ chức: chương trình nhân tài AI, ba khoá lịch sử có kết quả và một đợt đang tuyển.

Tất cả là dữ liệu tổng hợp (xem synthetic.py). Đợt tuyển tên bắt đầu bằng "[Minh hoạ]" để giao diện hiện nhãn cảnh báo.
"""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.demo.kb_seed import seed_kb
from src.demo.synthetic import Person, make_content, make_person, outcome_probability, review_scores
from src.models import (
    Application,
    Budget,
    Cohort,
    CohortClass,
    CohortTrack,
    Competency,
    CompetencyAssessment,
    CostEntry,
    Enrollment,
    Intake,
    Organization,
    OrgMembership,
    Partner,
    PartnerDemand,
    Program,
    Review,
    Role,
    Rubric,
    Track,
    TrackTarget,
    User,
    UserRole,
)
from src.models.base import uuid7
from src.schemas.application import Content
from src.services import eligibility
from src.services.applications import candidate_code

DEMO_TAG = "[Minh hoạ]"
DEMO_DOMAIN = "demo.talenthub.invalid"

PORTFOLIO_CRITERIA = [
    {
        "id": "projects",
        "name": "Dự án thực tế",
        "description": "Dự án có sản phẩm, liên kết và kết quả đo được",
        "weight": 3,
        "max": 5,
        "kind": "projects",
    },
    {
        "id": "programming",
        "name": "Lập trình",
        "description": "Độ rộng và chiều sâu kỹ năng lập trình",
        "weight": 3,
        "max": 5,
        "kind": "programming",
    },
    {
        "id": "ai_ml",
        "name": "Nền tảng AI/ML",
        "description": "Hiểu biết và ứng dụng học máy",
        "weight": 2,
        "max": 5,
        "kind": "ai_ml",
    },
    {
        "id": "education",
        "name": "Học vấn",
        "description": "Ngành học, kết quả học tập",
        "weight": 1,
        "max": 5,
        "kind": "education",
    },
    {
        "id": "experience",
        "name": "Kinh nghiệm",
        "description": "Thực tập hoặc làm việc liên quan",
        "weight": 1,
        "max": 5,
        "kind": "experience",
    },
    {
        "id": "motivation",
        "name": "Động lực",
        "description": "Mức độ rõ ràng và cụ thể của động lực",
        "weight": 1.5,
        "max": 5,
        "kind": "motivation",
    },
    {
        "id": "communication",
        "name": "Giao tiếp",
        "description": "Cách trình bày mạch lạc",
        "weight": 1,
        "max": 5,
        "kind": "communication",
    },
]
APTITUDE_CRITERIA = [
    {"id": "programming", "name": "Lập trình cơ bản", "description": "", "weight": 3, "max": 5, "kind": "programming"},
    {
        "id": "problem_solving",
        "name": "Tư duy giải quyết vấn đề",
        "description": "",
        "weight": 3,
        "max": 5,
        "kind": "problem_solving",
    },
    {"id": "data", "name": "Xử lý dữ liệu", "description": "", "weight": 2, "max": 5, "kind": "data"},
]
ROUNDS = [
    {"key": "portfolio", "label": "Xét hồ sơ", "type": "review"},
    {"key": "aptitude", "label": "Đánh giá năng lực", "type": "assessment"},
]
TRACKS = [
    (
        "ai_products",
        "AI Products",
        ["product", "ux", "figma", "prompt", "phân tích", "người dùng", "roadmap", "đo lường", "a/b"],
    ),
    (
        "ai_infrastructure",
        "AI Infrastructure",
        ["docker", "kubernetes", "linux", "aws", "mlops", "ci/cd", "redis", "postgresql", "triển khai"],
    ),
    (
        "ai_applications",
        "AI Applications",
        ["python", "llm", "rag", "fastapi", "pytorch", "langchain", "nlp", "hugging face", "embedding"],
    ),
]
COMPETENCIES = [
    ("programming", "Lập trình và phát triển phần mềm", "Tham chiếu SFIA: Programming/software development"),
    ("machine_learning", "Học máy", "Tham chiếu SFIA: Machine learning"),
    ("data_engineering", "Kỹ thuật dữ liệu và triển khai", "Tham chiếu SFIA: Data management / Deployment"),
    ("product_thinking", "Tư duy sản phẩm", "Tham chiếu SFIA: Product management"),
    ("collaboration", "Làm việc nhóm và giao tiếp", "Tham chiếu SFIA: Relationship management / Communication"),
]
TRACK_TARGETS = {
    "ai_products": {"product_thinking": 4, "collaboration": 4, "programming": 3, "machine_learning": 3},
    "ai_infrastructure": {"data_engineering": 4, "programming": 4, "collaboration": 3, "machine_learning": 3},
    "ai_applications": {"machine_learning": 4, "programming": 4, "data_engineering": 3, "collaboration": 3},
}
PARTNERS = [
    ("Contoso AI", ["python", "pytorch", "llm", "nlp"]),
    ("Fabrikam Data", ["python", "sql", "spark", "data"]),
    ("Tailspin Cloud", ["docker", "kubernetes", "linux", "aws"]),
    ("Wingtip Product Studio", ["react", "typescript", "figma", "product"]),
    ("Adventure Works Health", ["python", "fastapi", "postgresql", "docker"]),
    ("Northwind AI Lab", ["python", "llm", "rag", "langchain"]),
]


def _composite(scores: dict[str, float], criteria: list[dict[str, Any]]) -> float:
    total_w = sum(c["weight"] for c in criteria)
    return float(sum(scores[c["id"]] / c["max"] * c["weight"] for c in criteria if c["id"] in scores) / total_w * 100)


# Khả năng một năng lực là chỗ học viên chưa đạt bị hụt (năng lực khó hơn thì hay hụt hơn).
FAIL_WEIGHTS = {
    "programming": 1.0,
    "machine_learning": 1.4,
    "data_engineering": 1.6,
    "product_thinking": 1.2,
    "collaboration": 0.8,
}


def _competency_levels(
    rng: random.Random, targets: dict[str, int], qualified: bool, *, last_cohort: bool
) -> dict[str, int]:
    """Mức năng lực minh hoạ khớp với kết quả xét đạt: đạt thì mọi năng lực đủ mức, chưa đạt thì hụt 1-2 năng lực.

    Khoá cuối được dựng yếu hẳn ở tư duy sản phẩm (kể cả vài người vẫn được xét đạt) để màn Chất lượng chương trình có
    ví dụ về năng lực tụt so với khoá trước và quyết định không khớp dữ liệu.
    """
    weights = {**FAIL_WEIGHTS, **({"product_thinking": 4.0} if last_cohort else {})}
    levels = {code: min(7, target + rng.choice((0, 0, 1, 1, 2))) for code, target in targets.items()}
    codes = list(targets)
    if not qualified:
        failing: set[str] = set()
        while len(failing) < min(1 if rng.random() < 0.6 else 2, len(codes)):
            failing.add(rng.choices(codes, weights=[weights.get(c, 1.0) for c in codes])[0])
        for code in failing:
            levels[code] = max(1, targets[code] - rng.choice((1, 1, 2)))
    elif last_cohort and "product_thinking" in targets and rng.random() < 0.3:
        levels["product_thinking"] = targets["product_thinking"] - 1
    return levels


async def _ensure_roles(session: AsyncSession) -> dict[str, uuid.UUID]:
    return {code: rid for code, rid in (await session.execute(select(Role.code, Role.id))).all()}


async def _ensure_catalog(
    session: AsyncSession, org: Organization
) -> tuple[Program, dict[str, Track], dict[str, Competency]]:
    program = (await session.execute(select(Program).where(Program.code == "ai-talent"))).scalar_one_or_none()
    if program is None:
        program = Program(
            organization_id=org.id,
            code="ai-talent",
            name={"vi": "Chương trình nhân tài AI thực chiến", "en": "Applied AI Talent Program"},
            kind="cohort",
        )
        session.add(program)
        await session.flush()
    tracks: dict[str, Track] = {}
    for key, name, keywords in TRACKS:
        t = (
            await session.execute(select(Track).where(Track.program_id == program.id, Track.key == key))
        ).scalar_one_or_none()
        if t is None:
            t = Track(
                organization_id=org.id, program_id=program.id, key=key, name={"vi": name, "en": name}, keywords=keywords
            )
            session.add(t)
        tracks[key] = t
    comps: dict[str, Competency] = {}
    for code, name, desc in COMPETENCIES:
        c = (
            await session.execute(
                select(Competency).where(Competency.program_id == program.id, Competency.code == code)
            )
        ).scalar_one_or_none()
        if c is None:
            c = Competency(
                organization_id=org.id, program_id=program.id, code=code, name=name, description=desc, max_level=7
            )
            session.add(c)
        comps[code] = c
    await session.flush()
    for key, targets in TRACK_TARGETS.items():
        for code, level in targets.items():
            exists = (
                await session.execute(
                    select(TrackTarget).where(
                        TrackTarget.track_id == tracks[key].id, TrackTarget.competency_id == comps[code].id
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    TrackTarget(
                        organization_id=org.id,
                        track_id=tracks[key].id,
                        competency_id=comps[code].id,
                        target_level=level,
                    )
                )
    await session.flush()
    return program, tracks, comps


async def _make_people(
    session: AsyncSession, org: Organization, rng: random.Random, n: int, tag: str, role_id: uuid.UUID
) -> list[tuple[Person, uuid.UUID, uuid.UUID]]:
    """Tạo n người dùng giả (không có mật khẩu, không đăng nhập được) kèm membership ứng viên. Trả (người, user_id, membership_id)."""
    people = [make_person(rng) for _ in range(n)]
    users = [
        {
            "id": uuid7(),
            "email": f"{tag}.{i:04d}@{org.slug}.{DEMO_DOMAIN}",
            "full_name": p.full_name,
            "password_hash": None,
            "is_active": True,
            "must_change_password": False,
        }
        for i, p in enumerate(people)
    ]
    await session.execute(insert(User), users)
    members: list[dict[str, Any]] = [
        {"id": uuid7(), "organization_id": org.id, "user_id": u["id"], "status": "active"} for u in users
    ]
    await session.execute(insert(OrgMembership), members)
    await session.execute(
        insert(UserRole),
        [{"organization_id": org.id, "membership_id": m["id"], "role_id": role_id} for m in members],
    )
    return [(people[i], uuid.UUID(str(users[i]["id"])), uuid.UUID(str(members[i]["id"]))) for i in range(n)]


async def _ensure_reviewers(session: AsyncSession, org: Organization, roles: dict[str, uuid.UUID]) -> list[uuid.UUID]:
    out = []
    for i in range(3):
        email = f"reviewer.{i}@{org.slug}.{DEMO_DOMAIN}"  # theo tổ chức: users.email là duy nhất toàn cục
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, full_name=f"Reviewer minh hoạ {i + 1}", password_hash=None)
            session.add(user)
            await session.flush()
        m = (await session.execute(select(OrgMembership).where(OrgMembership.user_id == user.id))).scalar_one_or_none()
        if m is None:
            m = OrgMembership(organization_id=org.id, user_id=user.id, status="active")
            session.add(m)
            await session.flush()
            session.add(UserRole(organization_id=org.id, membership_id=m.id, role_id=roles["reviewer"]))
        out.append(m.id)
    return out


async def seed_demo(
    session: AsyncSession,
    org: Organization,
    *,
    current_applications: int = 600,
    history_sizes: tuple[int, ...] = (140, 150, 160),
    ready_size: int = 150,
    seed: int = 2026,
) -> dict[str, Any]:
    """Nạp dữ liệu minh hoạ trong một transaction đã đặt ngữ cảnh tổ chức. Chạy lại sẽ bị từ chối nếu đã nạp."""
    rng = random.Random(seed)  # noqa: S311 - dữ liệu giả, không cần ngẫu nhiên mật mã
    already = (
        await session.execute(select(Intake.id).where(Intake.name.like(f"{DEMO_TAG}%")).limit(1))
    ).scalar_one_or_none()
    if already:
        raise RuntimeError("Dữ liệu minh hoạ đã có trong tổ chức này")

    roles = await _ensure_roles(session)
    program, tracks, comps = await _ensure_catalog(session, org)
    reviewers = await _ensure_reviewers(session, org, roles)
    now = datetime.now(UTC)

    partners = []
    for name, skills in PARTNERS:
        p = (await session.execute(select(Partner).where(Partner.name == name))).scalar_one_or_none()
        if p is None:
            p = Partner(organization_id=org.id, name=name, skills=skills)
            session.add(p)
        partners.append(p)
    await session.flush()

    summary: dict[str, Any] = {"cohorts": [], "current": None}
    summary["kb_documents"] = await seed_kb(session, org)
    # ----- Ba khoá lịch sử -----
    for k, size in enumerate(history_sizes, start=1):
        code = f"K{k}"
        starts = date.today() - timedelta(days=150 * (len(history_sizes) - k + 1))
        cohort = Cohort(
            organization_id=org.id,
            program_id=program.id,
            code=code,
            name=f"Khoá {k}",
            starts_on=starts,
            capacity=size,
            status="completed",
        )
        session.add(cohort)
        await session.flush()
        intake = Intake(
            organization_id=org.id,
            program_id=program.id,
            cohort_id=cohort.id,
            name=f"{DEMO_TAG} Đợt tuyển khoá {k}",
            opens_at=now - timedelta(days=170 * (len(history_sizes) - k + 1)),
            closes_at=now - timedelta(days=160 * (len(history_sizes) - k + 1)),
            quota=size,
            status="closed",
            rounds=ROUNDS,
            approval_mode="two_level",
            ai_screening_enabled=True,
            blind_review=True,
            min_reviews=1,
        )
        session.add(intake)
        await session.flush()
        rub1 = Rubric(
            organization_id=org.id, intake_id=intake.id, round="portfolio", version=1, criteria=PORTFOLIO_CRITERIA
        )
        rub2 = Rubric(
            organization_id=org.id, intake_id=intake.id, round="aptitude", version=1, criteria=APTITUDE_CRITERIA
        )
        session.add_all([rub1, rub2])
        await session.flush()
        for track in tracks.values():
            session.add(
                CohortTrack(organization_id=org.id, cohort_id=cohort.id, track_id=track.id, capacity=int(size * 0.4))
            )
        for i, partner in enumerate(partners):
            session.add(
                PartnerDemand(
                    organization_id=org.id,
                    cohort_id=cohort.id,
                    partner_id=partner.id,
                    track_id=list(tracks.values())[i % 3].id,
                    slots=max(5, size // 8),
                )
            )
        klasses = [
            CohortClass(organization_id=org.id, cohort_id=cohort.id, name=f"Mức {lv}", level=lv, capacity=-(-size // 3))
            for lv in (1, 2, 3)
        ]
        session.add_all(klasses)
        await session.flush()

        applicants = await _make_people(session, org, rng, size * 2, f"{code.lower()}", roles["applicant"])
        scored = []
        for person, _user_id, mid in applicants:
            s1 = review_scores(rng, person, PORTFOLIO_CRITERIA)
            scored.append((_composite(s1, PORTFOLIO_CRITERIA) + rng.gauss(0, 4), person, _user_id, mid, s1))
        scored.sort(key=lambda t: -t[0])
        admitted_ids = {t[3] for t in scored[:size]}

        apps: list[dict[str, Any]] = []
        reviews: list[dict[str, Any]] = []
        enrollments: list[dict[str, Any]] = []
        assess_rows: list[dict[str, Any]] = []
        # RNG riêng cho đánh giá năng lực: không làm xáo dãy ngẫu nhiên của hồ sơ/điểm tuyển sinh (Rubric Lab dựa vào đó).
        arng = random.Random(f"{seed}-assess-{k}")  # noqa: S311 - dữ liệu giả
        track_list = list(tracks.values())
        qualified_n = 0
        for rank, (_, person, _uid, mid, s1) in enumerate(scored):
            app_id = uuid7()
            content = make_content(rng, person)
            admitted = mid in admitted_ids
            status = "ENROLLED" if admitted else ("WITHDRAWN" if rng.random() < 0.04 else "REJECTED")
            submitted = intake.opens_at + timedelta(days=rng.random() * 8)
            apps.append(
                {
                    "id": app_id,
                    "organization_id": org.id,
                    "intake_id": intake.id,
                    "applicant_membership_id": mid,
                    "status": status,
                    "current_round": "aptitude" if admitted else "portfolio",
                    "version": 5,
                    "candidate_code": candidate_code(app_id),
                    "profile": {
                        "full_name": person.full_name,
                        "gender": person.gender,
                        "city": person.city,
                        "phone": "0900000000",
                    },
                    "content": content,
                    "flags": [],
                    "submitted_at": submitted,
                    "consented_at": submitted,
                }
            )
            reviewer = reviewers[rank % len(reviewers)]
            reviews.append(
                {
                    "id": uuid7(),
                    "organization_id": org.id,
                    "application_id": app_id,
                    "reviewer_membership_id": reviewer,
                    "round": "portfolio",
                    "rubric_id": rub1.id,
                    "scores": s1,
                    "total_score": round(_composite(s1, PORTFOLIO_CRITERIA), 2),
                    "comment": "",
                    "recommendation": "advance" if admitted else "reject",
                    "submitted_at": submitted + timedelta(days=3),
                }
            )
            if admitted:
                s2 = review_scores(rng, person, APTITUDE_CRITERIA)
                reviews.append(
                    {
                        "id": uuid7(),
                        "organization_id": org.id,
                        "application_id": app_id,
                        "reviewer_membership_id": reviewers[(rank + 1) % len(reviewers)],
                        "round": "aptitude",
                        "rubric_id": rub2.id,
                        "scores": s2,
                        "total_score": round(_composite(s2, APTITUDE_CRITERIA), 2),
                        "comment": "",
                        "recommendation": "advance",
                        "submitted_at": submitted + timedelta(days=6),
                    }
                )
                prefs = content["preferences"]["tracks"]
                track = next((t for t in track_list if t.key in prefs), track_list[rank % 3])
                qualified = rng.random() < outcome_probability(person)
                qualified_n += qualified
                level = min(3, 1 + int((1 - person.skill) * 3))
                enrollment_id = uuid7()
                enrollments.append(
                    {
                        "id": enrollment_id,
                        "organization_id": org.id,
                        "application_id": app_id,
                        "membership_id": mid,
                        "cohort_id": cohort.id,
                        "class_id": klasses[level - 1].id,
                        "track_id": track.id,
                        "status": "qualified" if qualified else "not_qualified",
                        "qualification_reason": "Dữ liệu minh hoạ",
                        "enrolled_at": starts,
                    }
                )
                levels = _competency_levels(
                    arng, TRACK_TARGETS[track.key], qualified, last_cohort=k == len(history_sizes)
                )
                # Mentor thứ hai chấm rộng tay hơn (khoá 2 trở đi) để màn Chất lượng chương trình có ví dụ hiệu chuẩn.
                lenient = k >= 2 and len(reviewers) > 1 and arng.random() < 0.4
                assessor = reviewers[1] if lenient else reviewers[0]
                skip = k == len(history_sizes) and arng.random() < 0.02  # vài bản ghi còn thiếu
                jump = k == 2 and arng.random() < 0.03  # vài lần nhập nhầm rồi sửa
                for idx, (code_c, lvl) in enumerate(levels.items()):
                    if skip and idx == 0:
                        continue
                    if lenient and lvl >= TRACK_TARGETS[track.key][code_c]:
                        lvl = min(7, lvl + 1)
                    if jump and idx == 0:
                        assess_rows.append(
                            {
                                "id": uuid7(),
                                "organization_id": org.id,
                                "enrollment_id": enrollment_id,
                                "competency_id": comps[code_c].id,
                                "level": lvl - 3 if lvl >= 4 else lvl + 3,
                                "evidence": "Đánh giá minh hoạ (nhập nhầm, đã được đánh giá lại).",
                                "assessor_membership_id": assessor,
                                "assessed_at": now - timedelta(days=60),
                            }
                        )
                    assess_rows.append(
                        {
                            "id": uuid7(),
                            "organization_id": org.id,
                            "enrollment_id": enrollment_id,
                            "competency_id": comps[code_c].id,
                            "level": lvl,
                            "evidence": "Đánh giá minh hoạ của mentor dựa trên dự án thực chiến.",
                            "assessor_membership_id": assessor,
                            "assessed_at": now - timedelta(days=30),
                        }
                    )
        await session.execute(insert(Application), apps)
        await session.execute(insert(Review), reviews)
        await session.flush()
        await session.execute(insert(Enrollment), enrollments)
        await session.flush()
        await session.execute(insert(CompetencyAssessment), assess_rows)

        # chi phí lịch sử của khoá
        for month in range(3):
            session.add(
                CostEntry(
                    organization_id=org.id,
                    category="stipend",
                    amount_vnd=size * 8_000_000,
                    occurred_on=starts + timedelta(days=30 * month),
                    cohort_id=cohort.id,
                    description=f"Phụ cấp tháng {month + 1} (minh hoạ)",
                    source="manual",
                )
            )
        session.add(
            CostEntry(
                organization_id=org.id,
                category="infrastructure",
                amount_vnd=size * 1_200_000,
                occurred_on=starts,
                cohort_id=cohort.id,
                description="Hạ tầng và công cụ (minh hoạ)",
                source="manual",
            )
        )
        session.add(
            CostEntry(
                organization_id=org.id,
                category="partner",
                amount_vnd=size * 900_000,
                occurred_on=starts + timedelta(days=60),
                cohort_id=cohort.id,
                description="Điều phối đối tác (minh hoạ)",
                source="manual",
            )
        )
        session.add(Budget(organization_id=org.id, cohort_id=cohort.id, category=None, amount_vnd=size * 36_000_000))
        summary["cohorts"].append({"code": code, "applicants": size * 2, "admitted": size, "qualified": qualified_n})

    # ----- Khoá đã nhận học viên, chờ nhập học và xếp lớp -----
    n_hist = len(history_sizes)
    cohort_ready = Cohort(
        organization_id=org.id,
        program_id=program.id,
        code=f"K{n_hist + 1}",
        name=f"Khoá {n_hist + 1}",
        starts_on=date.today() + timedelta(days=14),
        capacity=ready_size,
        status="planned",
    )
    session.add(cohort_ready)
    await session.flush()
    intake_ready = Intake(
        organization_id=org.id,
        program_id=program.id,
        cohort_id=cohort_ready.id,
        name=f"{DEMO_TAG} Đợt tuyển khoá {n_hist + 1}",
        opens_at=now - timedelta(days=40),
        closes_at=now - timedelta(days=20),
        quota=ready_size,
        status="closed",
        rounds=ROUNDS,
        approval_mode="two_level",
        ai_screening_enabled=True,
        blind_review=True,
        min_reviews=1,
    )
    session.add(intake_ready)
    await session.flush()
    rub_a = Rubric(
        organization_id=org.id, intake_id=intake_ready.id, round="portfolio", version=1, criteria=PORTFOLIO_CRITERIA
    )
    rub_b = Rubric(
        organization_id=org.id, intake_id=intake_ready.id, round="aptitude", version=1, criteria=APTITUDE_CRITERIA
    )
    session.add_all([rub_a, rub_b])
    await session.flush()
    for track in tracks.values():
        session.add(
            CohortTrack(
                organization_id=org.id, cohort_id=cohort_ready.id, track_id=track.id, capacity=int(ready_size * 0.4)
            )
        )
    for i, partner in enumerate(partners):
        session.add(
            PartnerDemand(
                organization_id=org.id,
                cohort_id=cohort_ready.id,
                partner_id=partner.id,
                track_id=list(tracks.values())[i % 3].id,
                slots=max(8, ready_size // 6),
            )
        )
    ready_people = await _make_people(session, org, rng, ready_size, "ready", roles["applicant"])
    ready_apps: list[dict[str, Any]] = []
    ready_reviews: list[dict[str, Any]] = []
    for rank, (person, _uid, mid) in enumerate(ready_people):
        app_id = uuid7()
        submitted = now - timedelta(days=40 - rng.random() * 8)
        ready_apps.append(
            {
                "id": app_id,
                "organization_id": org.id,
                "intake_id": intake_ready.id,
                "applicant_membership_id": mid,
                "status": "ACCEPTED",
                "current_round": "aptitude",
                "version": 6,
                "candidate_code": candidate_code(app_id),
                "profile": {
                    "full_name": person.full_name,
                    "gender": person.gender,
                    "city": person.city,
                    "phone": "0900000000",
                },
                "content": make_content(rng, person),
                "flags": [],
                "submitted_at": submitted,
                "consented_at": submitted,
            }
        )
        for rnd_key, rub, crit in (("portfolio", rub_a, PORTFOLIO_CRITERIA), ("aptitude", rub_b, APTITUDE_CRITERIA)):
            sc = review_scores(rng, person, crit)
            ready_reviews.append(
                {
                    "id": uuid7(),
                    "organization_id": org.id,
                    "application_id": app_id,
                    "reviewer_membership_id": reviewers[rank % len(reviewers)],
                    "round": rnd_key,
                    "rubric_id": rub.id,
                    "scores": sc,
                    "total_score": round(_composite(sc, crit), 2),
                    "comment": "",
                    "recommendation": "advance",
                    "submitted_at": submitted + timedelta(days=4),
                }
            )
    await session.execute(insert(Application), ready_apps)
    await session.execute(insert(Review), ready_reviews)
    summary["ready_to_enroll"] = {
        "cohort_id": str(cohort_ready.id),
        "intake_id": str(intake_ready.id),
        "accepted": ready_size,
    }

    # ----- Khoá đang tuyển -----
    cohort4 = Cohort(
        organization_id=org.id,
        program_id=program.id,
        code=f"K{len(history_sizes) + 2}",
        name=f"Khoá {len(history_sizes) + 2}",
        starts_on=date.today() + timedelta(days=30),
        capacity=150,
        status="planned",
    )
    session.add(cohort4)
    await session.flush()
    intake4 = Intake(
        organization_id=org.id,
        program_id=program.id,
        cohort_id=cohort4.id,
        name=f"{DEMO_TAG} Đợt tuyển khoá {len(history_sizes) + 2}",
        description="Dữ liệu tổng hợp để trình diễn sàng lọc AI, xếp lớp và Rubric Lab.",
        opens_at=now - timedelta(days=12),
        closes_at=now + timedelta(days=2),
        quota=150,
        status="open",
        rounds=ROUNDS,
        approval_mode="two_level",
        ai_screening_enabled=True,
        blind_review=True,
        min_reviews=1,
        eligibility_rules=[
            {
                "id": "final_year",
                "label": "Sinh viên năm cuối hoặc đã tốt nghiệp",
                "type": "education_status_in",
                "values": ["final_year", "graduated"],
            }
        ],
    )
    session.add(intake4)
    await session.flush()
    session.add_all(
        [
            Rubric(
                organization_id=org.id, intake_id=intake4.id, round="portfolio", version=1, criteria=PORTFOLIO_CRITERIA
            ),
            Rubric(
                organization_id=org.id, intake_id=intake4.id, round="aptitude", version=1, criteria=APTITUDE_CRITERIA
            ),
        ]
    )
    for track in tracks.values():
        session.add(CohortTrack(organization_id=org.id, cohort_id=cohort4.id, track_id=track.id, capacity=60))
    for i, partner in enumerate(partners):
        session.add(
            PartnerDemand(
                organization_id=org.id,
                cohort_id=cohort4.id,
                partner_id=partner.id,
                track_id=list(tracks.values())[i % 3].id,
                slots=25,
            )
        )
    applicants = await _make_people(session, org, rng, current_applications, "k4", roles["applicant"])
    apps = []
    for person, _, mid in applicants:
        app_id = uuid7()
        content4 = make_content(rng, person)
        submitted = now - timedelta(days=rng.random() * 11)
        apps.append(
            {
                "id": app_id,
                "organization_id": org.id,
                "intake_id": intake4.id,
                "applicant_membership_id": mid,
                "status": "SUBMITTED",
                "current_round": None,
                "version": 2,
                "candidate_code": candidate_code(app_id),
                "profile": {
                    "full_name": person.full_name,
                    "gender": person.gender,
                    "city": person.city,
                    "phone": "0900000000",
                },
                "content": content4,
                "flags": eligibility.evaluate(intake4.eligibility_rules, Content.model_validate(content4)),
                "submitted_at": submitted,
                "consented_at": submitted,
            }
        )
    await session.execute(insert(Application), apps)
    summary["current"] = {
        "intake_id": str(intake4.id),
        "cohort_id": str(cohort4.id),
        "applications": current_applications,
    }
    return summary
