"""Trợ lý hỏi đáp: truy xuất đoạn tài liệu phù hợp quyền xem, trả lời có nguồn hoặc từ chối, ghi nhật ký để cải thiện tài liệu."""

import uuid
from typing import Any

from sqlalchemy import func, select

from src.ai.assistant import (
    Answer,
    Answerer,
    ExtractiveAnswerer,
    FallbackAnswerer,
    LLMAnswerer,
    Passage,
    abstain,
    content_terms,
    fold,
    rerank,
)
from src.ai.factory import make_provider
from src.ai.pricing import estimate_cost_usd
from src.config import Settings
from src.db import set_org_context
from src.errors import ConflictError, ValidationFailedError
from src.models import AiUsage, AssistantQuery
from src.services import costs, kb, org_settings
from src.services.tenancy import OrgDb

MAX_QUESTION = 500
RETRIEVE_LIMIT = 16  # lấy rộng rồi xếp hạng lại bằng hàm chấm điểm của trợ lý
KEEP_PASSAGES = 6
STAFF_PERMISSIONS = frozenset(
    {"application.read", "training.read", "mentor.assess", "kb.manage", "intake.manage", "cohort.read"}
)


def clean_question(raw: str) -> str:
    question = " ".join(raw.split())
    if len(question) < 3:
        raise ValidationFailedError("Hãy nhập câu hỏi cụ thể hơn", {"question": "Tối thiểu 3 ký tự"})
    if len(question) > MAX_QUESTION:
        raise ValidationFailedError(f"Câu hỏi tối đa {MAX_QUESTION} ký tự", {"question": "Quá dài"})
    return question


def can_see_internal(permissions: frozenset[str] | set[str]) -> bool:
    """Tài liệu nội bộ chỉ dành cho nhân sự; ứng viên (chỉ có quyền của ứng viên) chỉ thấy tài liệu công khai."""
    return bool(set(permissions) & STAFF_PERMISSIONS)


async def retrieve(db: OrgDb, question: str, *, internal: bool, limit: int = RETRIEVE_LIMIT) -> list[Passage]:
    terms = content_terms(question)
    if not terms:
        return []
    visibility = ["public", "internal"] if internal else ["public"]
    hits = await kb.search(db, " ".join(terms), visibility=visibility, limit=limit)
    full = await kb.chunks_by_ids(db, [h["chunk_id"] for h in hits])
    found = [
        Passage(n=i, title=h["title"], heading=h["heading"] or "", content=full.get(h["chunk_id"], h["snippet"]))
        for i, h in enumerate(hits, start=1)
    ]
    return rerank(question, found, KEEP_PASSAGES)


def build_answerer(settings: Settings, engine_setting: str) -> Answerer:
    """`llm` thiếu khoá API thì dùng động cơ trích xuất. Nhà cung cấp chọn chung với chấm hồ sơ (`make_provider`)."""
    provider = make_provider(settings, "assistant") if engine_setting == "llm" else None
    if provider is not None:
        return FallbackAnswerer(LLMAnswerer(provider), ExtractiveAnswerer())
    return ExtractiveAnswerer()


def _citations(answer: Answer, passages: list[Passage]) -> list[dict[str, Any]]:
    by_n = {p.n: p for p in passages}
    return [
        {"n": n, "title": by_n[n].title, "heading": by_n[n].heading, "snippet": by_n[n].content[:300]}
        for n in answer.citations
        if n in by_n
    ]


async def ask(
    db: OrgDb,
    *,
    question: str,
    permissions: frozenset[str],
    membership_id: uuid.UUID | None,
    answerer: Answerer,
    persist: bool = True,
    release_connection: bool = False,
) -> dict[str, Any]:
    """`release_connection`: trả kết nối về pool trong lúc chờ LLM (dùng trong request; không dùng với session đang
    nằm trong `session.begin()` như CLI/test)."""
    question = clean_question(question)
    passages = await retrieve(db, question, internal=can_see_internal(permissions))
    if release_connection:
        await db.session.commit()
    answer = await answerer.answer(question, passages) if passages else abstain(answerer.name, "no_passages")
    if release_connection:
        await set_org_context(db.session, db.org.id)  # SET LOCAL mất khi commit

    if answer.usage is not None and answer.model:
        usage = answer.usage.as_dict()
        db.session.add(
            AiUsage(
                organization_id=db.org.id,
                feature="assistant",
                provider=answer.engine.split(":", 1)[-1],
                model=answer.model,
                cost_usd=estimate_cost_usd(answer.model, usage),
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cache_read_tokens=usage["cache_read_tokens"],
                cache_write_tokens=usage["cache_write_tokens"],
            )
        )

    citations = _citations(answer, passages)
    query_id = uuid.uuid4()
    if persist:
        db.session.add(
            AssistantQuery(
                id=query_id,
                organization_id=db.org.id,
                membership_id=membership_id,
                question=question,
                question_key=fold(question)[:500],
                answered=not answer.abstained,
                reason=answer.note[:80],
                engine=answer.engine[:60],
                citations=[{"n": c["n"], "title": c["title"], "heading": c["heading"]} for c in citations],
            )
        )
        await db.session.flush()
    return {
        "id": query_id,
        "answer": answer.text,
        "answered": not answer.abstained,
        "citations": citations,
        "engine": answer.engine,
    }


async def pick_answerer(db: OrgDb, settings: Settings) -> Answerer:
    """Động cơ theo cài đặt tổ chức. Chạm trần ngân sách AI thì tự dùng động cơ trích xuất, không làm gián đoạn người hỏi."""
    wanted = str(await org_settings.get(db, "assistant_engine"))
    if wanted == "llm":
        try:
            await costs.ai_budget_guard(db)
        except ConflictError:
            wanted = "extractive"
    return build_answerer(settings, wanted)


async def set_feedback(db: OrgDb, query_id: uuid.UUID, membership_id: uuid.UUID, helpful: bool) -> bool:
    row = (
        await db.session.execute(
            select(AssistantQuery).where(AssistantQuery.id == query_id, AssistantQuery.membership_id == membership_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.helpful = helpful
    return True


async def insights(db: OrgDb, *, days: int = 30, limit: int = 20) -> dict[str, Any]:
    """Cho ban tuyển sinh: tỉ lệ trả lời được, mức hữu ích, và các câu hỏi chưa trả lời được (cần bổ sung tài liệu)."""
    window = func.now() - func.make_interval(0, 0, 0, days)
    base = select(AssistantQuery).where(AssistantQuery.created_at >= window)
    total = (await db.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    answered = (
        await db.session.execute(
            select(func.count()).select_from(base.where(AssistantQuery.answered.is_(True)).subquery())
        )
    ).scalar_one()
    rated = (
        await db.session.execute(
            select(AssistantQuery.helpful, func.count())
            .where(AssistantQuery.created_at >= window, AssistantQuery.helpful.is_not(None))
            .group_by(AssistantQuery.helpful)
        )
    ).all()
    rated_map = {bool(h): n for h, n in rated}
    gaps = (
        await db.session.execute(
            select(func.min(AssistantQuery.question), func.count(), func.max(AssistantQuery.created_at))
            .where(AssistantQuery.created_at >= window, AssistantQuery.answered.is_(False))
            .group_by(AssistantQuery.question_key)
            .order_by(func.count().desc(), func.max(AssistantQuery.created_at).desc())
            .limit(limit)
        )
    ).all()
    helpful_total = rated_map.get(True, 0) + rated_map.get(False, 0)
    return {
        "days": days,
        "total": total,
        "answered": answered,
        "answer_rate": round(answered / total, 3) if total else None,
        "helpful_rate": round(rated_map.get(True, 0) / helpful_total, 3) if helpful_total else None,
        "unanswered": [{"question": q, "count": n, "last_at": at} for q, n, at in gaps],
    }
