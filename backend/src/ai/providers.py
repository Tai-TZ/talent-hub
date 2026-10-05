"""Lớp nhà cung cấp LLM. Mỗi tác vụ chọn provider/model qua cấu hình; khoá API đọc từ biến môi trường.

Chỉ cài Anthropic (SDK chính thức) và `fake` cho test/demo offline. Thêm provider khác = thêm một lớp thoả `LLMProvider`.
"""

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


class ProviderError(Exception):
    """Lỗi dịch vụ LLM (mạng, quá tải, khoá sai...). `retryable` cho biết có nên thử lại sau."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderRefusalError(ProviderError):
    """Mô hình từ chối trả lời (bộ lọc an toàn)."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 4000
    ) -> tuple[T, Usage]: ...


class AnthropicProvider:
    """Gọi Claude qua SDK `anthropic`. Đầu ra có cấu trúc, được kiểm chứng bằng Pydantic."""

    name = "anthropic"

    def __init__(self, *, api_key: str | None, model: str, client: Any | None = None, timeout: float = 60.0) -> None:
        self.model = model
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 4000
    ) -> tuple[T, Usage]:
        import anthropic

        try:
            response = await self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except anthropic.RateLimitError as exc:
            raise ProviderError("Dịch vụ AI đang quá tải", retryable=True) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Không kết nối được dịch vụ AI", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Dịch vụ AI trả lỗi {exc.status_code}", retryable=exc.status_code >= 500) from exc

        if getattr(response, "stop_reason", None) == "refusal":
            raise ProviderRefusalError("Mô hình từ chối đánh giá hồ sơ này")
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderError("Mô hình không trả đầu ra đúng cấu trúc", retryable=True)
        u = response.usage
        usage = Usage(
            input_tokens=getattr(u, "input_tokens", 0) or 0,
            output_tokens=getattr(u, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        return parsed, usage


class FakeProvider:
    """Trả kết quả được dựng sẵn, dùng cho test và chạy demo không cần khoá API."""

    name = "fake"

    def __init__(self, responder: Any, model: str = "fake-model") -> None:
        self.model = model
        self._responder = responder
        self.calls: list[dict[str, str]] = []

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 4000
    ) -> tuple[T, Usage]:
        self.calls.append({"system": system, "user": user})
        out = self._responder(system, user)
        if isinstance(out, Exception):
            raise out
        return schema.model_validate(out), Usage(input_tokens=len(user) // 4, output_tokens=200)
