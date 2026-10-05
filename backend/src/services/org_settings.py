"""Cài đặt theo tổ chức, có kiểm tra kiểu/khoảng giá trị. Admin đổi được; giá trị mặc định nằm ở đây."""

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from src.errors import ValidationFailedError
from src.models import OrgSetting
from src.services.tenancy import OrgDb


class _Number:
    kind = "number"
    options: tuple[str, ...] = ()

    def __init__(self, lo: float, hi: float) -> None:
        self.lo, self.hi = lo, hi

    def __call__(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float) or not self.lo <= value <= self.hi:
            raise ValueError(f"phải là số trong khoảng {self.lo:g} đến {self.hi:g}")
        return float(value)


class _Choice:
    kind = "choice"

    def __init__(self, *options: str) -> None:
        self.options = options

    def __call__(self, value: Any) -> str:
        if value not in self.options:
            raise ValueError("phải là một trong: " + ", ".join(self.options))
        return str(value)


_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class _GuidList:
    """Danh sách GUID tenant cách nhau bằng dấu phẩy; rỗng nghĩa là không giới hạn."""

    kind = "text"
    options: tuple[str, ...] = ()

    def __call__(self, value: Any) -> str:
        if not isinstance(value, str) or len(value) > 500:
            raise ValueError("phải là chuỗi tối đa 500 ký tự")
        items = [x.strip().lower() for x in value.split(",") if x.strip()]
        bad = [x for x in items if not _GUID.match(x)]
        if bad:
            raise ValueError(f"không phải GUID tenant hợp lệ: {bad[0]}")
        return ",".join(items)


# key -> (mặc định, hàm kiểm tra, mô tả)
SPEC: dict[str, tuple[Any, _Number | _Choice | _GuidList, str]] = {
    "usd_vnd_rate": (25500.0, _Number(10_000, 100_000), "Tỷ giá USD/VND để quy đổi chi phí AI"),
    "ai_monthly_budget_usd": (50.0, _Number(0, 1_000_000), "Trần chi phí AI mỗi tháng (USD); 0 = không giới hạn"),
    "ai_engine": ("heuristic", _Choice("heuristic", "llm"), "Động cơ sàng lọc: heuristic (offline) hoặc llm (Claude)"),
    "stipend_vnd_per_month": (8_000_000.0, _Number(0, 100_000_000), "Phụ cấp mỗi học viên mỗi tháng (VND)"),
    "invite_ttl_hours": (72.0, _Number(1, 720), "Thời hạn link lời mời (giờ)"),
    "microsoft_signup": (
        "on",
        _Choice("on", "off"),
        "Cho phép ứng viên tự tạo tài khoản bằng Microsoft (nhân sự luôn cần lời mời)",
    ),
    "microsoft_allowed_tenants": (
        "",
        _GuidList(),
        "Chỉ nhận đăng nhập Microsoft từ các tenant này (GUID, cách nhau bằng dấu phẩy); để trống = mọi tenant",
    ),
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
