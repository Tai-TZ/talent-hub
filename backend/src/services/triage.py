"""Sàng lọc hàng loạt bằng AI: chấm cả đợt, đánh dấu hồ sơ sao chép, phân nhóm gợi ý để con người tập trung đúng chỗ."""

import asyncio
import json
import multiprocessing
import time
import uuid
from collections import Counter, deque
from collections.abc import AsyncGenerator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import aclosing
from typing import Any

from sqlalchemy import Text, and_, cast, func, insert, select, text

from src.ai.heuristic import HeuristicEngine, screen_batch
from src.ai.pricing import estimate_cost_usd
from src.ai.screening import DEFAULT_THRESHOLDS, ScreeningEngine, ScreeningError, ScreeningResult, decide_tier
from src.ai.similarity import find_duplicates_json
from src.config import get_settings
from src.errors import ConflictError, ValidationFailedError
from src.models import AiAssessment, AiUsage, Application
from src.services.intakes import active_rubric, get_intake
from src.services.jobs import set_progress, update_progress
from src.services.tenancy import OrgDb, background_org_db

CHUNK = 25  # số hồ sơ chấm đồng thời mỗi lượt; giữ nhỏ để động cơ chạy CPU không chặn vòng sự kiện quá lâu
FLUSH_ROWS = 500  # ghi kết quả theo lô: đủ từng này dòng...
FLUSH_SECONDS = 2.0  # ...hoặc đã quá từng này giây (để tiến độ vẫn cập nhật đều khi chấm bằng LLM chậm)
POOL_MIN = 1000  # từ cỡ đợt này mới chấm ở tiến trình con (đợt nhỏ không bõ thời gian khởi động tiến trình)
POOL_BATCH = 250  # số hồ sơ mỗi lần gửi sang tiến trình con


def thresholds_of(triage_config: dict[str, Any]) -> dict[str, float]:
    return {
        **DEFAULT_THRESHOLDS,
        **{k: float(v) for k, v in (triage_config.get("thresholds") or {}).items() if k in DEFAULT_THRESHOLDS},
    }


async def preflight(db: OrgDb, intake_id: uuid.UUID, round_key: str | None) -> tuple[str, int]:
    """Kiểm tra điều kiện chạy; trả (vòng, số hồ sơ cần chấm)."""
    intake = await get_intake(db, intake_id)
    if not intake.ai_screening_enabled:
        raise ConflictError("Đợt tuyển này chưa bật sàng lọc bằng AI (ứng viên cần được thông báo trước)")
    keys = [r["key"] for r in intake.rounds]
    round_key = round_key or keys[0]
    if round_key not in keys:
        raise ValidationFailedError("Vòng không hợp lệ", {"round": "Không thuộc đợt tuyển"})
    if await active_rubric(db, intake_id, round_key) is None:
        raise ValidationFailedError("Vòng chưa có rubric")
    count = (
        await db.session.execute(
            select(func.count())
            .select_from(Application)
            .where(
                Application.intake_id == intake_id,
                Application.status == "IN_ROUND",
                Application.current_round == round_key,
            )
        )
    ).scalar_one()
    return round_key, count


async def _scored_batches(
    engine: ScreeningEngine,
    pending: list[tuple[uuid.UUID, str]],
    criteria: list[dict[str, Any]],
    thresholds: dict[str, float],
    pool: ProcessPoolExecutor | None,
) -> AsyncGenerator[Sequence[tuple[uuid.UUID, ScreeningResult | None]], None]:
    """Chấm `pending` (nội dung dạng JSON) và trả kết quả theo từng lô; None nghĩa là động cơ không chấm được hồ sơ đó."""
    if pool is not None:
        # Động cơ luật thuần CPU: chấm ở tiến trình con để dùng nhiều nhân và không chặn vòng sự kiện của API.
        loop = asyncio.get_running_loop()
        in_flight: deque[tuple[list[uuid.UUID], asyncio.Future[list[ScreeningResult]]]] = deque()
        for start in range(0, len(pending), POOL_BATCH):
            batch = pending[start : start + POOL_BATCH]
            future = loop.run_in_executor(pool, screen_batch, [c for _, c in batch], criteria, thresholds)
            in_flight.append(([app_id for app_id, _ in batch], future))
            if len(in_flight) >= 2 * get_settings().triage_workers:  # đủ việc cho các tiến trình, không ôm hết vào RAM
                ids, done_future = in_flight.popleft()
                yield list(zip(ids, await done_future, strict=True))
        while in_flight:
            ids, done_future = in_flight.popleft()
            yield list(zip(ids, await done_future, strict=True))
        return

    semaphore = asyncio.Semaphore(get_settings().ai_concurrency)

    async def score(app_id: uuid.UUID, content: str) -> tuple[uuid.UUID, ScreeningResult | None]:
        async with semaphore:
            try:
                return app_id, await engine.screen(json.loads(content), criteria, thresholds)
            except ScreeningError:
                return app_id, None

    for start in range(0, len(pending), CHUNK):
        yield await asyncio.gather(*(score(app_id, content) for app_id, content in pending[start : start + CHUNK]))


def _assessment_row(
    org_id: uuid.UUID,
    app_id: uuid.UUID,
    round_key: str,
    result: ScreeningResult,
    tier: str,
    attention: bool,
    flags: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "organization_id": org_id,
        "application_id": app_id,
        "round": round_key,
        "engine": result.engine,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "total_score": result.total_score,
        "confidence": result.confidence,
        "tier": tier,
        "needs_attention": attention,
        "scores": {
            r.id: {"score": r.score, "max": r.max, "confidence": r.confidence, "rationale": r.rationale}
            for r in result.criteria
        },
        "evidence": {
            r.id: [{"field": e.field, "quote": e.quote, "start": e.start, "end": e.end} for e in r.evidence]
            for r in result.criteria
        },
        "flags": flags,
        "rationale": result.summary,
        "input_fields": result.input_fields,
    }


async def run_triage(
    org_id: uuid.UUID, job_id: uuid.UUID, *, engine: ScreeningEngine, intake_id: uuid.UUID, round_key: str, force: bool
) -> dict[str, Any]:
    started = time.perf_counter()
    async with background_org_db(org_id) as db:
        intake = await get_intake(db, intake_id)
        rubric = await active_rubric(db, intake_id, round_key)
        assert rubric is not None
        criteria = rubric.criteria
        thresholds = thresholds_of(intake.triage_config)

        to_score = and_(Application.status == "IN_ROUND", Application.current_round == round_key)
        if not force:
            has_assessment = (
                select(AiAssessment.id)
                .where(AiAssessment.application_id == Application.id, AiAssessment.round == round_key)
                .exists()
            )
            to_score = and_(to_score, ~has_assessment)
        # Một truy vấn cho cả hai việc: mọi hồ sơ đã nộp của đợt tham gia dò trùng (kể cả hồ sơ không nằm trong lượt
        # chấm này), cột `to_score` đánh dấu hồ sơ cần chấm. Nội dung lấy dạng chuỗi JSON: tiến trình API không phải
        # giữ hàng chục nghìn dict lồng nhau (GC duyệt lại chúng nhiều lần gây khựng); việc giải mã làm ở nơi chấm.
        rows = (
            await db.session.execute(
                select(Application.id, cast(Application.content, Text), to_score.label("to_score")).where(
                    Application.intake_id == intake_id, Application.status != "DRAFT"
                )
            )
        ).all()
    contents = {row[0]: row[1] for row in rows}
    pending = [(row[0], row[1]) for row in rows if row[2]]
    await set_progress(org_id, job_id, done=0, total=len(pending))

    workers = get_settings().triage_workers
    use_pool = isinstance(engine, HeuristicEngine) and workers > 0 and len(pending) >= POOL_MIN
    # Luôn dùng `spawn` (mặc định trên Linux là `fork`): sao chép một tiến trình API đang có nhiều luồng có thể treo
    # do khoá bị giữ dở; tiến trình con chỉ cần nạp `src.ai.heuristic`.
    pool = (
        ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) if use_pool else None
    )
    tiers: Counter[str] = Counter()
    failed = 0
    scores: list[float] = []
    dropped = 0
    cost = 0.0
    done = 0
    assessments: list[dict[str, Any]] = []
    usages: list[dict[str, Any]] = []
    waiting: list[tuple[uuid.UUID, ScreeningResult | None]] = []  # đã chấm, chờ kết quả dò trùng
    last_flush = time.perf_counter()

    def collect(
        results: list[tuple[uuid.UUID, ScreeningResult | None]], duplicates: dict[uuid.UUID, list[dict[str, Any]]]
    ) -> None:
        nonlocal failed, dropped, cost, done
        for app_id, result in results:
            done += 1
            if result is None:
                failed += 1
                continue
            flags = result.flags + duplicates.get(app_id, [])
            tier, attention = decide_tier(result.total_score, result.confidence, flags, thresholds)
            assessments.append(
                _assessment_row(org_id, app_id, round_key, result, tier, attention or result.needs_attention, flags)
            )
            tiers[tier] += 1
            scores.append(result.total_score)
            dropped += result.dropped_quotes
            if result.usage and result.model:
                usd = estimate_cost_usd(result.model, result.usage)
                cost += usd
                usages.append(
                    {
                        "organization_id": org_id,
                        "feature": "screening",
                        "provider": result.engine.split(":", 1)[-1],
                        "model": result.model,
                        "application_id": app_id,
                        "job_id": job_id,
                        "cost_usd": usd,
                        "input_tokens": result.usage.get("input_tokens", 0),
                        "output_tokens": result.usage.get("output_tokens", 0),
                        "cache_read_tokens": result.usage.get("cache_read_tokens", 0),
                        "cache_write_tokens": result.usage.get("cache_write_tokens", 0),
                    }
                )

    async def flush() -> None:
        """Ghi kết quả đã chấm bằng INSERT nhiều dòng và cập nhật tiến độ trong cùng một giao dịch."""
        nonlocal last_flush
        async with background_org_db(org_id) as db:
            if assessments:
                await db.session.execute(insert(AiAssessment), assessments)
            if usages:
                await db.session.execute(insert(AiUsage), usages)
            await update_progress(db, job_id, done=done)
        assessments.clear()
        usages.clear()
        last_flush = time.perf_counter()

    async def drain(duplicates: dict[uuid.UUID, list[dict[str, Any]]]) -> None:
        """Xử lý kết quả đang chờ theo từng phần, ghi xen kẽ để không giữ vòng sự kiện quá lâu một lần."""
        while waiting:
            collect(waiting[:FLUSH_ROWS], duplicates)
            del waiting[:FLUSH_ROWS]
            if len(assessments) >= FLUSH_ROWS or time.perf_counter() - last_flush >= FLUSH_SECONDS:
                await flush()

    try:
        # Dò trùng chạy song song với việc chấm: ở tiến trình con nếu có, không thì ở luồng riêng (pool=None).
        duplicates_future = asyncio.get_running_loop().run_in_executor(pool, find_duplicates_json, contents)
        async with aclosing(_scored_batches(engine, pending, criteria, thresholds, pool)) as batches:
            async for results in batches:
                waiting.extend(results)
                if duplicates_future.done():  # chưa có kết quả dò trùng thì giữ lại, việc chấm vẫn tiếp tục
                    await drain(duplicates_future.result())
        duplicates = await duplicates_future
        await drain(duplicates)
        await flush()
    finally:
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    return {
        "round": round_key,
        "engine": engine.name,
        "processed": len(pending) - failed,
        "failed": failed,
        "tiers": dict(tiers),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "dropped_quotes": dropped,
        "cost_usd": round(cost, 4),
        "duration_s": round(time.perf_counter() - started, 2),
        "duplicates_flagged": sum(1 for app_id, _ in pending if app_id in duplicates),
    }


_LATEST = """
SELECT DISTINCT ON (a.application_id) a.application_id, a.total_score, a.confidence, a.tier, a.needs_attention, a.flags, a.engine, a.created_at
  FROM ai_assessments a
  JOIN applications p ON p.id = a.application_id
 WHERE p.intake_id = :intake AND a.round = :round
 ORDER BY a.application_id, a.created_at DESC
"""


# Khung SQL cố định; chỉ ghép các đoạn hằng số (không có dữ liệu người dùng), mọi giá trị đều là tham số ràng buộc.
_TIER_SQL = "SELECT tier, count(*), count(*) FILTER (WHERE needs_attention) FROM (__LATEST__) t GROUP BY tier".replace(
    "__LATEST__", _LATEST
)
_HIST_SQL = (
    "SELECT least(width_bucket(total_score, 0, 100, 10), 10) AS b, tier, count(*) FROM (__LATEST__) t GROUP BY b, tier ORDER BY b"
).replace("__LATEST__", _LATEST)
_ITEMS_SQL = """
SELECT t.application_id, p.candidate_code, p.profile ->> 'full_name', p.status, t.total_score, t.confidence, t.tier,
       t.needs_attention, jsonb_array_length(t.flags), t.engine
  FROM (__LATEST__) t JOIN applications p ON p.id = t.application_id
  __WHERE__
 ORDER BY t.total_score DESC, t.application_id
 LIMIT :limit OFFSET :offset
""".replace("__LATEST__", _LATEST)


async def board(db: OrgDb, intake_id: uuid.UUID, round_key: str) -> dict[str, Any]:
    """Dữ liệu bảng triage: số lượng theo nhóm, phân bố điểm, hồ sơ cần xem kỹ."""
    params = {"intake": intake_id, "round": round_key}
    tier_rows = (await db.session.execute(text(_TIER_SQL), params)).all()
    hist_rows = (await db.session.execute(text(_HIST_SQL), params)).all()
    pool = (
        await db.session.execute(
            select(func.count())
            .select_from(Application)
            .where(
                Application.intake_id == intake_id,
                Application.status == "IN_ROUND",
                Application.current_round == round_key,
            )
        )
    ).scalar_one()
    scored = sum(r[1] for r in tier_rows)
    return {
        "round": round_key,
        "pool": pool,
        "scored": scored,
        "tiers": {r[0]: {"count": r[1], "attention": r[2]} for r in tier_rows},
        "histogram": [{"bucket": int(r[0]), "tier": r[1], "count": r[2]} for r in hist_rows],
    }


async def board_items(
    db: OrgDb,
    intake_id: uuid.UUID,
    round_key: str,
    *,
    tier: str | None,
    attention: bool | None,
    limit: int,
    offset: int,
    can_see_pii: bool,
    blind: bool,
) -> list[dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {"intake": intake_id, "round": round_key, "limit": limit, "offset": offset}
    if tier:
        clauses.append("t.tier = :tier")
        params["tier"] = tier
    if attention is not None:
        clauses.append("t.needs_attention = :attention")
        params["attention"] = attention
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    # Khung SQL và các mệnh đề lọc đều là hằng số trong file này; giá trị người dùng chỉ đi qua tham số ràng buộc.
    statement = text(_ITEMS_SQL.replace("__WHERE__", where))  # nosemgrep: avoid-sqlalchemy-text
    rows = (await db.session.execute(statement, params)).all()
    show_name = can_see_pii or not blind
    return [
        {
            "application_id": r[0],
            "candidate_code": r[1],
            "name": r[2] if show_name else None,
            "status": r[3],
            "total_score": r[4],
            "confidence": r[5],
            "tier": r[6],
            "needs_attention": r[7],
            "flag_count": r[8],
            "engine": r[9],
        }
        for r in rows
    ]
