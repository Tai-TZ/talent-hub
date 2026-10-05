"""Bảng giá để ước tính chi phí LLM (USD mỗi triệu token). Giá niêm yết của nhà cung cấp tại thời điểm viết;
cập nhật ở đây khi nhà cung cấp đổi giá. Chi phí này dùng cho trần ngân sách AI hằng tháng nên không được ước tính thiếu:
mô hình chưa có trong bảng (và không có giá tuỳ chỉnh qua LLM_PRICE_*) được tính theo giá dự phòng cao nhất và ghi
cảnh báo một lần.
"""

import logging

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

# model -> (input, output, cache_read, cache_write)
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
    # Mô hình mặc định qua OpenRouter/Gemini (OpenRouter tính đúng giá của nhà cung cấp gốc).
    "gemini-2.5-flash": (0.30, 2.50, 0.075, 0.30),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.025, 0.10),
    # Mô hình nhỏ thường dùng của OpenAI (gợi ý trong .env.example).
    "gpt-4.1-mini": (0.40, 1.60, 0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60, 0.075, 0.15),
    "gpt-5-mini": (0.25, 2.0, 0.025, 0.25),
}
FALLBACK_PRICE = (10.0, 50.0, 1.0, 12.5)
FREE_PRICE = (0.0, 0.0, 0.0, 0.0)

_warned_models: set[str] = set()


def _lookup(model: str) -> tuple[float, float, float, float] | None:
    """Khớp tên mô hình với bảng giá.

    Chấp nhận tiền tố hãng của OpenRouter (vd google/gemini-2.5-flash) và hậu tố ngày (vd claude-haiku-4-5-20251001
    khớp "claude-haiku-4-5"). Khoá dài nhất được ưu tiên để gemini-2.5-flash-lite không bị tính theo gemini-2.5-flash.
    """
    name = model.rsplit("/", 1)[-1]
    name, _, variant = name.partition(":")
    if variant == "free":  # biến thể miễn phí của OpenRouter
        return FREE_PRICE
    for key in sorted(PRICES, key=len, reverse=True):
        if name == key or name.startswith(f"{key}-"):
            return PRICES[key]
    return None


def price_for(model: str, settings: Settings | None = None) -> tuple[float, float, float, float]:
    settings = settings or get_settings()
    inp, out = settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok
    if inp is not None and out is not None and model in (settings.llm_scoring_model, settings.llm_assistant_model):
        # Giá tuỳ chỉnh: token đọc từ cache tính bằng giá đầu vào để không ước tính thiếu.
        return (inp, out, inp, inp)
    price = _lookup(model)
    if price is not None:
        return price
    if model not in _warned_models:
        _warned_models.add(model)
        logger.warning(
            "Chưa có giá cho mô hình AI; ước tính theo giá dự phòng cao nhất. "
            "Đặt LLM_PRICE_INPUT_PER_MTOK và LLM_PRICE_OUTPUT_PER_MTOK để tính đúng.",
            extra={"model": model},
        )
    return FALLBACK_PRICE


def estimate_cost_usd(model: str, usage: dict[str, int], settings: Settings | None = None) -> float:
    inp, out, c_read, c_write = price_for(model, settings)
    total = (
        usage.get("input_tokens", 0) * inp
        + usage.get("output_tokens", 0) * out
        + usage.get("cache_read_tokens", 0) * c_read
        + usage.get("cache_write_tokens", 0) * c_write
    )
    return round(total / 1_000_000, 6)
