"""Ngôn ngữ của người dùng cho nội dung backend tự sinh (cảnh báo, báo cáo). BFF gửi `Accept-Language` theo cookie
ngôn ngữ giao diện; mặc định tiếng Việt."""

from typing import Literal

from starlette.requests import Request

Locale = Literal["vi", "en"]


def locale_of(request: Request) -> Locale:
    header = (request.headers.get("accept-language") or "").strip().lower()
    return "en" if header.startswith("en") else "vi"
