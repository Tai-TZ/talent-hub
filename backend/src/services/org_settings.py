"""Cài đặt theo tổ chức, có kiểm tra kiểu/khoảng giá trị. Admin đổi được; giá trị mặc định nằm ở đây."""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from src.errors import ValidationFailedError
from src.models import OrgSetting
from src.services.tenancy import OrgDb


def _number(lo: float, hi: float) -> Callable[[Any], float]:
    def check(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float) or not lo <= value <= hi:
            raise ValueError(f"phải là số trong khoảng {lo:g} đến {hi:g}")
        return float(value)

    return check


def _choice(*options: str) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        if value not in options:
            raise ValueError("phải là một trong: " + ", ".join(options))
        return str(value)

    return check


# key -> (mặc định, hàm kiểm tra, mô tả)
SPEC: dict[str, tuple[Any, Callable[[Any], Any], str]] = {
    "usd_vnd_rate": (25500.0, _number(10_000, 100_000), "Tỷ giá USD/VND để quy đổi chi phí AI"),
    "ai_monthly_budget_usd": (50.0, _number(0, 1_000_000), "Trần chi phí AI mỗi tháng (USD); 0 = không giới hạn"),
    "ai_engine": ("heuristic", _choice("heuristic", "llm"), "Động cơ sàng lọc: heuristic (offline) hoặc llm (Claude)"),
    "stipend_vnd_per_month": (8_000_000.0, _number(0, 100_000_000), "Phụ cấp mỗi học viên mỗi tháng (VND)"),
    "invite_ttl_hours": (72.0, _number(1, 720), "Thời hạn link lời mời (giờ)"),
}


async def get_all(db: OrgDb) -> dict[str, Any]:
    rows = (await db.session.execute(select(OrgSetting))).scalars().all()
    stored = {r.key: r.value for r in rows}
    return {key: stored.get(key, default) for key, (default, _, _) in SPEC.items()}


async def get(db: OrgDb, key: str) -> Any:
    row = (await db.session.execute(select(OrgSetting).where(OrgSetting.key == key))).scalar_one_or_none()
    return row.value if row is not None else SPEC[key][0]


async def update(db: OrgDb, values: dict[str, Any], *, actor_user_id: uuid.UUID) -> dict[str, Any]:
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}
    for key, value in values.items():
        if key not in SPEC:
            errors[key] = "Cài đặt không tồn tại"
            continue
        try:
            clean[key] = SPEC[key][1](value)
        except ValueError as exc:
            errors[key] = str(exc)
    if errors:
        raise ValidationFailedError("Cài đặt không hợp lệ", errors)
    for key, value in clean.items():
        stmt = insert(OrgSetting).values(organization_id=db.org.id, key=key, value=value, updated_by=actor_user_id)
        await db.session.execute(
            stmt.on_conflict_do_update(
                index_elements=[OrgSetting.organization_id, OrgSetting.key],
                set_={"value": value, "updated_by": actor_user_id, "updated_at": func.now()},
            )
        )
    return await get_all(db)
