"""Bảng giá để ước tính chi phí LLM (USD mỗi triệu token). Giá niêm yết của Anthropic tại thời điểm viết;
cập nhật ở đây khi nhà cung cấp đổi giá. Mô hình chưa có trong bảng được tính theo giá cao nhất để không ước tính thiếu."""

# model -> (input, output, cache_read, cache_write)
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
}
FALLBACK_PRICE = (10.0, 50.0, 1.0, 12.5)


def estimate_cost_usd(model: str, usage: dict[str, int]) -> float:
    # Chấp nhận mã có hậu tố ngày (vd claude-haiku-4-5-20251001) khớp với khoá giá "claude-haiku-4-5".
    key = next((k for k in PRICES if model == k or model.startswith(f"{k}-")), None)
    inp, out, c_read, c_write = PRICES[key] if key else FALLBACK_PRICE
    total = (
        usage.get("input_tokens", 0) * inp
        + usage.get("output_tokens", 0) * out
        + usage.get("cache_read_tokens", 0) * c_read
        + usage.get("cache_write_tokens", 0) * c_write
    )
    return round(total / 1_000_000, 6)
