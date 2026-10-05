"""Chất lượng chương trình: mức đạt chuẩn đầu ra, cảnh báo dữ liệu thiếu/bất thường, đề xuất cải tiến (hàm thuần)."""

import uuid
from datetime import UTC, datetime, timedelta

from src.services.quality import Assessment, CohortData, Learner, analyse, to_markdown

NOW = datetime(2026, 10, 5, tzinfo=UTC)
A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
TRACK, OTHER = uuid.uuid4(), uuid.uuid4()
M1, M2 = uuid.uuid4(), uuid.uuid4()


def learner(
    name: str,
    levels: dict[uuid.UUID, int],
    *,
    status: str = "qualified",
    assessor: uuid.UUID = M1,
    track: uuid.UUID | None = TRACK,
    days_ago: int = 10,
) -> Learner:
    return Learner(
        id=uuid.uuid4(),
        name=name,
        code=name.upper(),
        status=status,
        track_id=track,
        class_id=uuid.uuid4(),
        assessments=[Assessment(cid, lvl, assessor, NOW - timedelta(days=days_ago)) for cid, lvl in levels.items()],
    )


def cohort(learners: list[Learner], previous: dict | None = None) -> CohortData:
    return CohortData(
        cohort={"id": uuid.uuid4(), "code": "K9", "name": "Khoá 9", "status": "completed", "classes": 2},
        learners=learners,
        competencies={
            A: {"code": "a", "name": "Lập trình", "max_level": 7},
            B: {"code": "b", "name": "Học máy", "max_level": 7},
            C: {"code": "c", "name": "Sản phẩm", "max_level": 7},
        },
        targets={TRACK: {A: 4, B: 3, C: 3}, OTHER: {A: 3}},
        tracks={TRACK: "AI Products", OTHER: "AI Infra"},
        assessors={M1: "Mentor Một", M2: "Mentor Hai"},
        previous=previous,
    )


def healthy(n: int, start: int = 0, **kw) -> list[Learner]:  # type: ignore[no-untyped-def]
    return [learner(f"hv{start + i}", {A: 4 + i % 2, B: 3 + i % 2, C: 3 + i % 2}, **kw) for i in range(n)]


def by_code(result: dict) -> dict:
    return {a["code"]: a for a in result["alerts"]}


def test_clean_cohort_has_full_coverage_and_no_alerts() -> None:
    result = analyse(cohort(healthy(30)), "vi", now=NOW)
    assert result["summary"]["coverage"] == 1.0 and result["summary"]["attainment"] == 1.0
    assert result["summary"]["qualified_rate"] == 1.0
    assert result["alerts"] == []
    assert [r["area"] for r in result["recommendations"]] == ["general"]
    comp = next(c for c in result["competencies"] if c["code"] == "a")
    assert comp["targeted"] == comp["assessed"] == comp["met"] == 30 and comp["by_track"][0]["track"] == "AI Products"


def test_data_gaps_and_anomalies_are_flagged() -> None:
    people = healthy(25)
    people.append(learner("khong-nhanh", {}, track=None, status="active"))
    people.append(learner("thieu", {A: 5, B: 4}, status="active"))  # chưa đánh giá C
    people.append(learner("cu", {A: 5, B: 4, C: 4}, status="active", days_ago=90))
    jumper = learner("nhay", {A: 5, B: 4, C: 4})
    jumper.assessments.insert(0, Assessment(A, 1, M1, NOW - timedelta(days=40)))
    people.append(jumper)
    people.append(learner("ngoc", {A: 4, B: 2, C: 3}, status="qualified"))  # xét đạt dù B chưa đủ
    people.append(learner("rut", {}, status="withdrawn", track=None))  # đã rút: không tính

    alerts = by_code(analyse(cohort(people), "vi", now=NOW))
    assert set(alerts) == {"no_track", "missing_assessment", "stale_assessment", "level_jump", "decision_mismatch"}
    assert alerts["no_track"]["count"] == 1 and alerts["missing_assessment"]["count"] == 1
    assert "1 → 5" in alerts["level_jump"]["items"][0]["label"]
    assert alerts["decision_mismatch"]["items"][0]["ref_type"] == "enrollment"


def test_low_attainment_drop_and_lenient_mentor_drive_recommendations() -> None:
    strict = [
        learner(f"s{i}", {A: 4, B: 3, C: 2 if i % 2 else 3}, status="not_qualified" if i % 2 else "qualified")
        for i in range(30)
    ]
    lenient = [
        learner(
            f"l{i}",
            {A: 6, B: 5, C: 2 if i % 3 == 0 else 5},
            assessor=M2,
            status="not_qualified" if i % 3 == 0 else "qualified",
        )
        for i in range(30)
    ]
    result = analyse(
        cohort(strict + lenient, previous={"code": "K8", "attainment": {"c": 0.95, "a": 1.0}}), "vi", now=NOW
    )
    alerts = by_code(result)
    assert (
        alerts["low_attainment"]["severity"] == "danger" and "Sản phẩm" in alerts["low_attainment"]["items"][0]["label"]
    )
    assert "attainment_drop" in alerts and "K8" in alerts["attainment_drop"]["items"][0]["label"]
    assert "assessor_bias" in alerts and any("Mentor Hai" in i["label"] for i in alerts["assessor_bias"]["items"])
    assert result["alerts"][0]["severity"] == "danger"  # nặng nhất đứng đầu
    first = result["recommendations"][0]
    assert first["priority"] == "high" and "Sản phẩm" in first["title"] and len(first["actions"]) >= 3
    assert {"assessment"} <= {r["area"] for r in result["recommendations"]}
    comp_c = next(c for c in result["competencies"] if c["code"] == "c")
    assert comp_c["previous"] == 0.95 and comp_c["avg_gap"] == 1.0


def test_small_samples_do_not_raise_statistical_alerts() -> None:
    few = [learner(f"x{i}", {A: 4, B: 3, C: 1}, status="not_qualified") for i in range(5)]
    alerts = by_code(analyse(cohort(few, previous={"code": "K8", "attainment": {"c": 1.0}}), "vi", now=NOW))
    assert "low_attainment" not in alerts and "attainment_drop" not in alerts


def test_english_output_and_markdown_report() -> None:
    people = healthy(25) + [learner("khong-nhanh", {}, track=None, status="active")]
    result = analyse(cohort(people), "en", now=NOW)
    assert result["alerts"][0]["title"] == "Learners without a track"
    assert result["recommendations"][0]["title"] == "Complete the data before qualification"
    md = to_markdown(result, "en", now=NOW)
    assert md.startswith("# Programme quality report — K9 Khoá 9")
    assert "## Learning outcomes by competency" in md and "| Lập trình | 25/25 | 25 | 100% |" in md
    assert "## Improvement recommendations" in md and "khong-nhanh" in md
    vi = to_markdown(analyse(cohort(healthy(3)), "vi", now=NOW), "vi", now=NOW)
    assert "## Đề xuất cải tiến" in vi and "Không có cảnh báo." in vi
