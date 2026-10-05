"""Chi phí chương trình và chi phí AI: sổ chi phí, ngân sách, cảnh báo vượt ngân sách, chi phí trên mỗi hồ sơ được nhận.

Chi phí AI không nhập tay: lấy từ nhật ký sử dụng (ai_usage) rồi quy đổi sang VND theo tỷ giá của tổ chức,
nên không thể ghi trùng. Các khoản còn lại là bút toán nhập tay, không sửa, chỉ huỷ (void) kèm lý do.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.elements import ColumnElement

from src.errors import ConflictError, NotFoundError, ValidationFailedError
from src.models import AiUsage, Application, Budget, CostEntry, Intake
from src.models.admin import COST_CATEGORIES
from src.services import org_settings
from src.services.audit import RequestMeta, write_audit
from src.services.tenancy import OrgDb

MANUAL_CATEGORIES = tuple(c for c in COST_CATEGORIES if c != "ai")
MAX_AMOUNT = Decimal("1000000000000")  # 1 nghìn tỷ VND: chặn nhập nhầm số


def _check_amount(value: Decimal) -> Decimal:
    if value <= 0 or value > MAX_AMOUNT:
        raise ValidationFailedError(
            "Số tiền không hợp lệ", {"amount_vnd": f"Phải lớn hơn 0 và không quá {MAX_AMOUNT:,.0f}"}
        )
    return value.quantize(Decimal("0.01"))


async def add_entry(
    db: OrgDb,
    *,
    actor_user_id: uuid.UUID,
    category: str,
    amount_vnd: Decimal,
    occurred_on: date,
    cohort_id: uuid.UUID | None,
    description: str,
    meta: RequestMeta,
) -> CostEntry:
    if category not in MANUAL_CATEGORIES:
        raise ValidationFailedError(
            "Danh mục không hợp lệ", {"category": "Chi phí AI được tính tự động từ nhật ký sử dụng"}
        )
    if occurred_on > datetime.now(UTC).date():
        raise ValidationFailedError("Ngày phát sinh không được ở tương lai", {"occurred_on": "Ngày ở tương lai"})
    entry = CostEntry(
        organization_id=db.org.id,
        category=category,
        amount_vnd=_check_amount(amount_vnd),
        occurred_on=occurred_on,
        cohort_id=cohort_id,
        description=description.strip()[:500],
        source="manual",
        created_by=actor_user_id,
    )
    db.session.add(entry)
    await db.session.flush()
    write_audit(
        db,
        action="cost.entry_added",
        entity_type="cost_entry",
        entity_id=entry.id,
        actor_user_id=actor_user_id,
        after={"category": category, "amount_vnd": str(entry.amount_vnd)},
        meta=meta,
    )
    return entry


async def void_entry(
    db: OrgDb, entry_id: uuid.UUID, *, reason: str, actor_user_id: uuid.UUID, meta: RequestMeta
) -> CostEntry:
    entry = (
        await db.session.execute(select(CostEntry).where(CostEntry.id == entry_id).with_for_update())
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Không tìm thấy bút toán")
    if entry.voided_at is not None:
        raise ConflictError("Bút toán đã bị huỷ")
    if entry.source != "manual":
        raise ConflictError("Bút toán do hệ thống tạo không thể huỷ")
    if len(reason.strip()) < 5:
        raise ValidationFailedError("Cần ghi lý do huỷ", {"reason": "Tối thiểu 5 ký tự"})
    entry.voided_at = datetime.now(UTC)
    entry.void_reason = reason.strip()[:300]
    write_audit(
        db,
        action="cost.entry_voided",
        entity_type="cost_entry",
        entity_id=entry.id,
        actor_user_id=actor_user_id,
        after={"reason": entry.void_reason},
        meta=meta,
    )
    return entry


async def list_entries(
    db: OrgDb,
    *,
    category: str | None,
    cohort_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[CostEntry], int]:
    conditions: list[ColumnElement[bool]] = []
    if category:
        conditions.append(CostEntry.category == category)
    if cohort_id:
        conditions.append(CostEntry.cohort_id == cohort_id)
    if date_from:
        conditions.append(CostEntry.occurred_on >= date_from)
    if date_to:
        conditions.append(CostEntry.occurred_on <= date_to)
    total = (await db.session.execute(select(func.count()).select_from(CostEntry).where(*conditions))).scalar_one()
    rows = (
        (
            await db.session.execute(
                select(CostEntry)
                .where(*conditions)
                .order_by(CostEntry.occurred_on.desc(), CostEntry.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def upsert_budget(
    db: OrgDb,
    *,
    actor_user_id: uuid.UUID,
    cohort_id: uuid.UUID | None,
    category: str | None,
    amount_vnd: Decimal,
    meta: RequestMeta,
) -> None:
    if category is not None and category not in COST_CATEGORIES:
        raise ValidationFailedError("Danh mục không hợp lệ", {"category": "Không tồn tại"})
    if amount_vnd < 0 or amount_vnd > MAX_AMOUNT:
        raise ValidationFailedError("Ngân sách không hợp lệ", {"amount_vnd": "Không hợp lệ"})
    stmt = insert(Budget).values(
        organization_id=db.org.id,
        cohort_id=cohort_id,
        category=category,
        amount_vnd=amount_vnd,
        updated_by=actor_user_id,
    )
    await db.session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_budgets_scope",
            set_={"amount_vnd": amount_vnd, "updated_by": actor_user_id, "updated_at": func.now()},
        )
    )
    write_audit(
        db,
        action="cost.budget_set",
        entity_type="budget",
        actor_user_id=actor_user_id,
        after={"cohort_id": str(cohort_id) if cohort_id else None, "category": category, "amount_vnd": str(amount_vnd)},
        meta=meta,
    )


def burn_status(spent: Decimal, budget: Decimal | None) -> dict[str, Any]:
    if budget is None or budget <= 0:
        return {
            "budget": float(budget) if budget is not None else None,
            "spent": float(spent),
            "ratio": None,
            "status": "none",
        }
    ratio = float(spent / budget)
    return {
        "budget": float(budget),
        "spent": float(spent),
        "ratio": round(ratio, 4),
        "status": "over" if ratio >= 1 else "warning" if ratio >= 0.8 else "ok",
    }


async def ai_month_to_date_usd(db: OrgDb) -> float:
    now = datetime.now(UTC)
    value = (
        await db.session.execute(
            select(func.coalesce(func.sum(AiUsage.cost_usd), 0.0)).where(
                extract("year", AiUsage.created_at) == now.year, extract("month", AiUsage.created_at) == now.month
            )
        )
    ).scalar_one()
    return float(value)


async def ai_budget_guard(db: OrgDb) -> None:
    """Chặn gọi LLM khi đã chạm trần chi phí AI của tháng (0 = không giới hạn)."""
    cap = float(await org_settings.get(db, "ai_monthly_budget_usd"))
    if cap > 0 and await ai_month_to_date_usd(db) >= cap:
        raise ConflictError(
            f"Đã chạm trần chi phí AI tháng này ({cap:g} USD). Tăng trần trong Cài đặt hoặc dùng động cơ offline."
        )


async def summary(
    db: OrgDb, *, cohort_id: uuid.UUID | None, date_from: date | None, date_to: date | None
) -> dict[str, Any]:
    rate = Decimal(str(await org_settings.get(db, "usd_vnd_rate")))
    manual_filters: list[ColumnElement[bool]] = [CostEntry.voided_at.is_(None)]
    if cohort_id:
        manual_filters.append(CostEntry.cohort_id == cohort_id)
    if date_from:
        manual_filters.append(CostEntry.occurred_on >= date_from)
    if date_to:
        manual_filters.append(CostEntry.occurred_on <= date_to)

    by_cat: dict[str, Decimal] = {c: Decimal(0) for c in COST_CATEGORIES}
    for category, total in (
        await db.session.execute(
            select(CostEntry.category, func.sum(CostEntry.amount_vnd))
            .where(*manual_filters)
            .group_by(CostEntry.category)
        )
    ).all():
        by_cat[category] += total

    ai_stmt = select(
        func.coalesce(func.sum(AiUsage.cost_usd), 0.0),
        func.coalesce(func.sum(AiUsage.input_tokens + AiUsage.output_tokens), 0),
        func.count(),
    )
    ai_month_col = func.date_trunc("month", AiUsage.created_at)
    ai_month = select(ai_month_col, func.sum(AiUsage.cost_usd)).group_by(ai_month_col)
    ai_filters: list[ColumnElement[bool]] = []
    if cohort_id:
        ai_stmt = ai_stmt.join(Application, Application.id == AiUsage.application_id).join(
            Intake, Intake.id == Application.intake_id
        )
        ai_month = ai_month.join(Application, Application.id == AiUsage.application_id).join(
            Intake, Intake.id == Application.intake_id
        )
        ai_filters.append(Intake.cohort_id == cohort_id)
    if date_from:
        ai_filters.append(AiUsage.created_at >= datetime.combine(date_from, datetime.min.time(), UTC))
    if date_to:
        ai_filters.append(AiUsage.created_at < datetime.combine(date_to, datetime.max.time(), UTC))
    usd, tokens, calls = (await db.session.execute(ai_stmt.where(*ai_filters))).one()
    ai_vnd = (Decimal(str(usd)) * rate).quantize(Decimal("0.01"))
    by_cat["ai"] = ai_vnd

    months: dict[str, dict[str, float]] = {}
    entry_month = func.date_trunc("month", CostEntry.occurred_on)
    for month_start, cat, total in (
        await db.session.execute(
            select(entry_month, CostEntry.category, func.sum(CostEntry.amount_vnd))
            .where(*manual_filters)
            .group_by(entry_month, CostEntry.category)
        )
    ).all():
        months.setdefault(month_start.strftime("%Y-%m"), {})[cat] = float(total)
    for month_start, month_usd in (await db.session.execute(ai_month.where(*ai_filters))).all():
        months.setdefault(month_start.strftime("%Y-%m"), {})["ai"] = float(Decimal(str(month_usd)) * rate)
    timeline = [{"month": m, "total": sum(v.values()), **v} for m, v in sorted(months.items())]

    total = sum(by_cat.values(), Decimal(0))
    budgets = (
        (
            await db.session.execute(
                select(Budget).where(Budget.cohort_id == cohort_id)
                if cohort_id
                else select(Budget).where(Budget.cohort_id.is_(None))
            )
        )
        .scalars()
        .all()
    )
    budget_by = {b.category: b.amount_vnd for b in budgets}
    cats = {c: {"amount": float(by_cat[c]), **burn_status(by_cat[c], budget_by.get(c))} for c in COST_CATEGORIES}
    overall = burn_status(total, budget_by.get(None))

    accepted_stmt = (
        select(func.count())
        .select_from(Application)
        .join(Intake, Intake.id == Application.intake_id)
        .where(Application.status.in_(("ACCEPTED", "ENROLLED")))
    )
    if cohort_id:
        accepted_stmt = accepted_stmt.where(Intake.cohort_id == cohort_id)
    accepted = (await db.session.execute(accepted_stmt)).scalar_one()

    alerts = [
        {"scope": cat, "status": data["status"], "ratio": data["ratio"]}
        for cat, data in cats.items()
        if data["status"] in ("warning", "over")
    ]
    if overall["status"] in ("warning", "over"):
        alerts.insert(0, {"scope": "total", "status": overall["status"], "ratio": overall["ratio"]})

    return {
        "currency": "VND",
        "usd_vnd_rate": float(rate),
        "total": float(total),
        "overall": overall,
        "by_category": cats,
        "timeline": timeline,
        "ai": {
            "usd": round(float(usd), 4),
            "vnd": float(ai_vnd),
            "tokens": int(tokens),
            "calls": int(calls),
            "month_to_date_usd": round(await ai_month_to_date_usd(db), 4),
        },
        "accepted_count": accepted,
        "cost_per_accepted": float(total / accepted) if accepted else None,
        "alerts": alerts,
    }


async def ai_breakdown(db: OrgDb, *, group: str, limit: int = 31) -> list[dict[str, Any]]:
    """Chi tiết sử dụng AI theo tính năng, mô hình hoặc ngày để IT thấy khoản nào tốn nhất."""
    column: Any = {
        "feature": AiUsage.feature,
        "model": AiUsage.model,
        "day": func.date_trunc("day", AiUsage.created_at),
    }.get(group)
    if column is None:
        raise ValidationFailedError("Cách nhóm không hợp lệ", {"group": "Chọn feature, model hoặc day"})
    rows = (
        await db.session.execute(
            select(
                column.label("k"),
                func.sum(AiUsage.cost_usd),
                func.sum(AiUsage.input_tokens),
                func.sum(AiUsage.output_tokens),
                func.count(),
            )
            .group_by(column)
            .order_by(column.desc() if group == "day" else func.sum(AiUsage.cost_usd).desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "key": r[0],
            "cost_usd": round(float(r[1]), 4),
            "input_tokens": int(r[2]),
            "output_tokens": int(r[3]),
            "calls": r[4],
        }
        for r in rows
    ]
