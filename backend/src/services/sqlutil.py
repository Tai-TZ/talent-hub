"""Tiện ích SQL dùng chung."""

LIKE_ESCAPE = "\\"


def contains_pattern(text: str) -> str:
    """Mẫu `LIKE '%text%'` coi `%`, `_` và `\\` trong đầu vào là chữ thường, không phải ký tự đại diện.

    Dùng cùng `ilike(pattern, escape=LIKE_ESCAPE)`. Không escape thì người dùng gõ `%` sẽ khớp mọi bản ghi
    (và các mẫu phức tạp có thể gây quét chậm).
    """
    escaped = (
        text.strip()
        .replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"
