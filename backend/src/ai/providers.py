"""Lớp nhà cung cấp LLM. Mỗi tác vụ chọn provider/model qua cấu hình; khoá API đọc từ biến môi trường.

Có Anthropic (SDK chính thức), một lớp chung cho mọi dịch vụ tương thích OpenAI Chat Completions (OpenRouter, OpenAI,
Gemini) và `fake` cho test/demo offline. Thêm provider khác = thêm một lớp thoả `LLMProvider`.
"""

import asyncio
import copy
import json
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

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


# Ràng buộc mà chế độ strict của OpenAI/Gemini không (hoặc chưa đồng đều) hỗ trợ: chuyển vào mô tả để mô hình vẫn biết,
# còn việc kiểm tra thật do Pydantic làm sau khi nhận kết quả (giống cách SDK Anthropic biến đổi schema).
_UNSUPPORTED_SCHEMA_KEYS = frozenset({"minLength", "maxLength", "minItems", "maxItems", "pattern", "format"})
_STRUCTURE_ERROR = "Mô hình không trả đầu ra đúng cấu trúc"
_REFUSAL_ERROR = "Mô hình từ chối đánh giá hồ sơ này"


def strict_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema dạng strict từ model Pydantic: mọi thuộc tính bắt buộc, `additionalProperties: false`, không `$ref`.

    Không đổi hành vi: trường có giá trị mặc định nay phải được mô hình trả (rỗng cũng được) và kết quả vẫn được
    `schema.model_validate_json` kiểm chứng đầy đủ, kể cả các ràng buộc độ dài đã chuyển vào mô tả.
    """
    raw = schema.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in node:
            target = defs[node["$ref"].rsplit("/", 1)[-1]]
            return convert({**copy.deepcopy(target), **{k: v for k, v in node.items() if k != "$ref"}})
        out: dict[str, Any] = {}
        notes: list[str] = []
        for key, value in node.items():
            if key in ("title", "default"):
                continue
            if key in _UNSUPPORTED_SCHEMA_KEYS:
                notes.append(f"{key}={value}")
            elif key == "properties":
                out[key] = {name: convert(sub) for name, sub in value.items()}
            elif key in ("items", "additionalProperties") and isinstance(value, dict):
                out[key] = convert(value)
            elif key in ("anyOf", "allOf", "oneOf"):
                out[key] = [convert(sub) for sub in value]
            else:
                out[key] = value
        if out.get("type") == "object" or "properties" in out:
            props = out.setdefault("properties", {})
            out["required"] = list(props)
            out["additionalProperties"] = False
        if notes:
            out["description"] = f"{out.get('description', '')} ({'; '.join(notes)})".strip()
        return out

    return convert(raw)


def _provider_label(base_url: str) -> str:
    """Tên ngắn để ghi nhật ký chi phí (ai_usage.provider) theo máy chủ của base URL."""
    host = (urlsplit(base_url).hostname or "").lower()
    if host.endswith("openrouter.ai"):
        return "openrouter"
    if host == "api.openai.com":
        return "openai"
    if host == "generativelanguage.googleapis.com":
        return "gemini"
    return "openai_compatible"


def _strip_fence(text: str) -> str:
    """Một số mô hình ở chế độ json_object bọc JSON trong ```json ... ```."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    return body.strip()


class OpenAICompatibleProvider:
    """Gọi mọi dịch vụ tương thích OpenAI Chat Completions qua `httpx` (OpenRouter, OpenAI, Gemini...).

    Hợp đồng giống `AnthropicProvider`: trả (đối tượng Pydantic đã kiểm chứng, Usage); lỗi quá tải/mạng/5xx là
    `ProviderError(retryable=True)`, lỗi 4xx khác không thử lại, bộ lọc nội dung là `ProviderRefusalError`.
    Khoá API chỉ nằm trong header Authorization, không bao giờ được ghi vào thông báo lỗi hay log.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
        json_mode: str = "json_schema",
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        app_url: str | None = None,
        app_title: str = "Talent Hub",
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.name = _provider_label(base_url)
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._timeout = timeout
        self._json_mode = json_mode
        self._max_retries = max(0, max_retries)
        self._retry_backoff = retry_backoff
        self._app_url = app_url
        self._app_title = app_title
        self._client = client
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if self.name == "openrouter":
            # Ghi nguồn ứng dụng trên OpenRouter (tuỳ chọn, không ảnh hưởng kết quả).
            if self._app_url:
                headers["HTTP-Referer"] = self._app_url
            headers["X-Title"] = self._app_title
        return headers

    def _body(self, *, system: str, user: str, schema: type[BaseModel], max_tokens: int) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model}
        if self._json_mode == "json_object":
            spec = json.dumps(strict_json_schema(schema), ensure_ascii=False)
            system = f"{system}\n\nChỉ trả về DUY NHẤT một đối tượng JSON hợp lệ theo JSON Schema sau:\n{spec}"
            body["response_format"] = {"type": "json_object"}
        else:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": strict_json_schema(schema), "strict": True},
            }
            if self.name == "openrouter":
                # Chỉ định tuyến tới nhà cung cấp hỗ trợ response_format, tránh nhận văn bản tự do.
                body["provider"] = {"require_parameters": True}
        body["messages"] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        # OpenAI dùng max_completion_tokens (mô hình suy luận không nhận max_tokens); các dịch vụ khác dùng max_tokens.
        body["max_completion_tokens" if self.name == "openai" else "max_tokens"] = max_tokens
        return body

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(self._url, json=body, headers=self._headers(), timeout=self._timeout)
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            return await client.post(self._url, json=body, headers=self._headers())

    async def _send(self, body: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                return await self._send_once(body)
            except ProviderError as exc:
                if not exc.retryable or attempt >= self._max_retries:
                    raise
                await asyncio.sleep(self._retry_backoff * 2**attempt)
                attempt += 1

    async def _send_once(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._post(body)
        except httpx.TimeoutException as exc:
            raise ProviderError("Dịch vụ AI phản hồi quá lâu", retryable=True) from exc
        except httpx.TransportError as exc:
            raise ProviderError("Không kết nối được dịch vụ AI", retryable=True) from exc
        status = response.status_code
        if status == 429:
            raise ProviderError("Dịch vụ AI đang quá tải", retryable=True)
        if status >= 400:
            raise ProviderError(f"Dịch vụ AI trả lỗi {status}", retryable=status >= 500 or status == 408)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("Dịch vụ AI trả phản hồi không hợp lệ", retryable=True) from exc
        if not isinstance(data, dict):
            raise ProviderError("Dịch vụ AI trả phản hồi không hợp lệ", retryable=True)
        error = data.get("error")
        if error and not data.get("choices"):
            # OpenRouter có thể trả HTTP 200 kèm lỗi của nhà cung cấp phía sau.
            code = error.get("code") if isinstance(error, dict) else None
            code = code if isinstance(code, int) else 502
            if code == 429:
                raise ProviderError("Dịch vụ AI đang quá tải", retryable=True)
            raise ProviderError(f"Dịch vụ AI trả lỗi {code}", retryable=code >= 500 or code == 408)
        return data

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], max_tokens: int = 4000
    ) -> tuple[T, Usage]:
        data = await self._send(self._body(system=system, user=user, schema=schema, max_tokens=max_tokens))
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError("Dịch vụ AI trả phản hồi không hợp lệ", retryable=True)
        choice = choices[0]
        message = _as_dict(choice.get("message"))
        finish = choice.get("finish_reason")
        if finish == "content_filter" or message.get("refusal"):
            raise ProviderRefusalError(_REFUSAL_ERROR)

        content = message.get("content")
        if isinstance(content, list):  # một số dịch vụ trả danh sách phần văn bản
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        try:
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty")
            parsed = schema.model_validate_json(_strip_fence(content))
        except (ValidationError, ValueError) as exc:
            if finish == "length":
                raise ProviderError("Đầu ra của mô hình bị cắt do vượt giới hạn token") from exc
            raise ProviderError(_STRUCTURE_ERROR, retryable=True) from exc
        return parsed, _usage(data.get("usage"))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _usage(raw: Any) -> Usage:
    """`prompt_tokens` của OpenAI đã gồm token đọc từ cache; tách ra để khớp cách tính của Anthropic."""
    u = _as_dict(raw)
    details = _as_dict(u.get("prompt_tokens_details"))

    def num(source: dict[str, Any], key: str) -> int:
        value = source.get(key)
        return int(value) if isinstance(value, int | float) and value > 0 else 0

    prompt, cached, written = num(u, "prompt_tokens"), num(details, "cached_tokens"), num(details, "cache_write_tokens")
    return Usage(
        input_tokens=max(prompt - cached - written, 0),
        output_tokens=num(u, "completion_tokens"),
        cache_read_tokens=cached,
        cache_write_tokens=written,
    )


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
