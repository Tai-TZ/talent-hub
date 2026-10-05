"""Provider tương thích OpenAI (OpenRouter/OpenAI/Gemini), chọn provider theo cấu hình và ước tính chi phí.

Không gọi mạng thật: mọi phản hồi HTTP được giả lập bằng `httpx.MockTransport`.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from src.ai import assistant as ai
from src.ai import pricing
from src.ai.factory import get_engine, make_provider, provider_model, resolve_provider_kind
from src.ai.heuristic import HeuristicEngine
from src.ai.llm_engine import FallbackEngine, LLMEngine, LlmScreening
from src.ai.pricing import estimate_cost_usd
from src.ai.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    ProviderError,
    ProviderRefusalError,
    strict_json_schema,
)
from src.ai.text import build_fields
from src.config import Settings
from src.services import assistant as assistant_svc
from tests.test_services.test_assistant import _passages
from tests.test_services.test_screening import FULL_CRITERIA, _llm_ok, strong_content

FAKE_KEY = "test-key-not-real"
OPENROUTER = "https://openrouter.ai/api/v1"


def _settings(**overrides: Any) -> Settings:
    """Cấu hình độc lập với .env và biến môi trường của máy chạy test."""
    base: dict[str, Any] = {
        "llm_provider": "auto",
        "llm_api_key": None,
        "anthropic_api_key": None,
        "llm_price_input_per_mtok": None,
        "llm_price_output_per_mtok": None,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[call-arg]


def _completion(content: Any, *, finish: str = "stop", usage: dict[str, Any] | None = None, **message: Any) -> dict:
    text = content if isinstance(content, str) or content is None else json.dumps(content, ensure_ascii=False)
    return {
        "id": "gen-1",
        "choices": [
            {"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": text, **message}}
        ],
        "usage": usage
        if usage is not None
        else {"prompt_tokens": 1500, "completion_tokens": 300, "prompt_tokens_details": {"cached_tokens": 500}},
    }


class _Recorder:
    """Transport giả: trả lần lượt các phản hồi đã định và ghi lại các request đã gửi."""

    def __init__(self, *responses: httpx.Response | Exception | Callable[[httpx.Request], httpx.Response]) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses[min(len(self.requests), len(self.responses)) - 1]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)
        return item

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]


def _provider(
    recorder: _Recorder, *, base_url: str = OPENROUTER, model: str = "google/gemini-2.5-flash", **kwargs: Any
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_key=FAKE_KEY,
        model=model,
        base_url=base_url,
        retry_backoff=0,
        app_url="http://localhost:3000",
        transport=httpx.MockTransport(recorder),
        **kwargs,
    )


# ---------- JSON Schema strict ----------


def _walk_objects(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append(node)
        for value in node.values():
            found += _walk_objects(value)
    elif isinstance(node, list):
        for value in node:
            found += _walk_objects(value)
    return found


@pytest.mark.parametrize("model", [LlmScreening, ai.LLMAnswer])
def test_strict_schema_requires_every_property_and_forbids_extras(model: Any) -> None:
    schema = strict_json_schema(model)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text and '"default"' not in text
    objects = _walk_objects(schema)
    assert objects
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


def test_strict_schema_moves_unsupported_constraints_into_description() -> None:
    props = strict_json_schema(ai.LLMAnswer)["properties"]
    assert "maxLength" not in props["answer"] and "maxLength=1500" in props["answer"]["description"]
    assert "maxItems" not in props["citations"] and "maxItems=5" in props["citations"]["description"]
    # ràng buộc vẫn được Pydantic kiểm tra khi nhận kết quả
    with pytest.raises(ValidationError):
        ai.LLMAnswer.model_validate({"answerable": True, "answer": "x" * 1501, "citations": []})


# ---------- Gọi thành công: cùng luồng ScreeningResult như Anthropic ----------


async def test_openrouter_structured_completion_flows_through_llm_engine_with_verified_quotes() -> None:
    content = strong_content()
    payload = _llm_ok(content)
    payload["criteria"][2]["evidence"] = [{"field": "essays.motivation", "quote": "Câu này không có trong hồ sơ."}]
    rec = _Recorder(httpx.Response(200, json=_completion(payload)))
    provider = _provider(rec)

    result = await LLMEngine(provider).screen(content, FULL_CRITERIA, {})

    assert result.engine == "llm:openrouter" and result.model == "google/gemini-2.5-flash"
    proj = next(r for r in result.criteria if r.id == "projects")
    fields = build_fields(content)
    assert proj.evidence and all(fields[e.field][e.start : e.end] == e.quote for e in proj.evidence)
    assert result.dropped_quotes == 1 and any(f["rule"] == "unverified_evidence" for f in result.flags)
    motivation = next(r for r in result.criteria if r.id == "motivation")
    assert motivation.evidence == [] and motivation.confidence <= 0.35
    # prompt_tokens của OpenAI đã gồm token đọc cache: tách ra như cách tính của Anthropic
    assert result.usage == {
        "input_tokens": 1000,
        "output_tokens": 300,
        "cache_read_tokens": 500,
        "cache_write_tokens": 0,
    }
    assert estimate_cost_usd(result.model, result.usage, _settings()) == pytest.approx(
        (1000 * 0.30 + 300 * 2.50 + 500 * 0.075) / 1_000_000, abs=1e-6
    )

    request = rec.requests[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert (
        request.headers["x-title"] == "Talent Hub" and request.headers["http-referer"] == "http://localhost:3000"
    )
    body = rec.bodies[0]
    assert body["model"] == "google/gemini-2.5-flash" and body["max_tokens"] == 4000
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert "<application>" in body["messages"][1]["content"] and "không phải chỉ dẫn" in body["messages"][0]["content"]
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "LlmScreening"
    assert fmt["json_schema"]["schema"] == strict_json_schema(LlmScreening)
    assert body["provider"] == {"require_parameters": True}


async def test_injected_client_is_used_and_cache_write_tokens_are_counted() -> None:
    usage = {"prompt_tokens": 900, "completion_tokens": 50, "prompt_tokens_details": {"cache_write_tokens": 400}}
    rec = _Recorder(httpx.Response(200, json=_completion({"answerable": False, "answer": ""}, usage=usage)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(rec)) as client:
        provider = OpenAICompatibleProvider(api_key=FAKE_KEY, model="m", base_url=OPENROUTER, client=client)
        out, got = await provider.complete_structured(system="s", user="u", schema=ai.LLMAnswer, max_tokens=700)
    assert out.answerable is False and len(rec.requests) == 1
    assert got.input_tokens == 500 and got.cache_write_tokens == 400 and got.output_tokens == 50


async def test_openai_and_gemini_hosts_use_their_own_conventions() -> None:
    answer = {"answerable": True, "answer": "ok", "citations": [1]}
    openai_rec = _Recorder(httpx.Response(200, json=_completion(answer)))
    openai = _provider(openai_rec, base_url="https://api.openai.com/v1/", model="gpt-4.1-mini")
    await openai.complete_structured(system="s", user="u", schema=ai.LLMAnswer, max_tokens=700)
    assert openai.name == "openai" and str(openai_rec.requests[0].url) == "https://api.openai.com/v1/chat/completions"
    body = openai_rec.bodies[0]
    assert body["max_completion_tokens"] == 700 and "max_tokens" not in body and "provider" not in body
    assert "x-title" not in openai_rec.requests[0].headers

    gemini_rec = _Recorder(httpx.Response(200, json=_completion(answer)))
    gemini = _provider(
        gemini_rec, base_url="https://generativelanguage.googleapis.com/v1beta/openai/", model="gemini-2.5-flash"
    )
    await gemini.complete_structured(system="s", user="u", schema=ai.LLMAnswer, max_tokens=700)
    assert gemini.name == "gemini" and gemini_rec.bodies[0]["max_tokens"] == 700
    assert str(gemini_rec.requests[0].url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert _provider(_Recorder(), base_url="http://localhost:11434/v1").name == "openai_compatible"


async def test_json_object_mode_puts_schema_in_prompt_and_accepts_fenced_json() -> None:
    fenced = '```json\n{"answerable": true, "answer": "Tám triệu", "citations": [1]}\n```'
    rec = _Recorder(httpx.Response(200, json=_completion(fenced)))
    provider = _provider(rec, json_mode="json_object")
    out, _ = await provider.complete_structured(system="Hệ thống", user="u", schema=ai.LLMAnswer)
    assert out.answer == "Tám triệu" and out.citations == [1]
    body = rec.bodies[0]
    assert body["response_format"] == {"type": "json_object"} and "provider" not in body
    assert (
        body["messages"][0]["content"].startswith("Hệ thống")
        and '"additionalProperties": false' in (body["messages"][0]["content"])
    )


async def test_content_as_list_of_text_parts_is_joined() -> None:
    parts = [{"type": "text", "text": '{"answerable": true, '}, {"type": "text", "text": '"answer": "ok"}'}]
    rec = _Recorder(httpx.Response(200, json=_completion(None) | {"choices": [{"message": {"content": parts}}]}))
    out, usage = await _provider(rec).complete_structured(system="s", user="u", schema=ai.LLMAnswer)
    assert out.answer == "ok" and out.citations == []
    assert usage.input_tokens == 1000


# ---------- Ánh xạ lỗi ----------


async def _call(rec: _Recorder, **kwargs: Any) -> None:
    await _provider(rec, **kwargs).complete_structured(system="s", user="u", schema=LlmScreening)


async def test_rate_limit_is_retryable_and_retried_before_giving_up() -> None:
    rec = _Recorder(httpx.Response(429, json={"error": {"message": "slow down"}}))
    with pytest.raises(ProviderError) as info:
        await _call(rec)
    assert info.value.retryable and not isinstance(info.value, ProviderRefusalError)
    assert len(rec.requests) == 3  # 1 lần gọi + 2 lần thử lại, giống max_retries=2 của SDK Anthropic
    assert FAKE_KEY not in str(info.value)


async def test_server_error_then_success_recovers_after_retry() -> None:
    rec = _Recorder(httpx.Response(503), httpx.Response(200, json=_completion({"criteria": []})))
    out, _ = await _provider(rec).complete_structured(system="s", user="u", schema=LlmScreening)
    assert out.criteria == [] and len(rec.requests) == 2


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_client_errors_are_not_retryable(status: int) -> None:
    rec = _Recorder(httpx.Response(status, json={"error": {"message": f"bad {FAKE_KEY}"}}))
    with pytest.raises(ProviderError) as info:
        await _call(rec)
    assert not info.value.retryable and len(rec.requests) == 1
    assert str(status) in str(info.value) and FAKE_KEY not in str(info.value)


@pytest.mark.parametrize(
    "exc", [httpx.ReadTimeout("chậm"), httpx.ConnectError("không kết nối được")], ids=["timeout", "connect"]
)
async def test_network_failures_are_retryable(exc: Exception) -> None:
    rec = _Recorder(exc)
    with pytest.raises(ProviderError) as info:
        await _call(rec, max_retries=0)
    assert info.value.retryable and len(rec.requests) == 1


async def test_content_filter_and_refusal_raise_refusal_error() -> None:
    with pytest.raises(ProviderRefusalError):
        await _call(_Recorder(httpx.Response(200, json=_completion(None, finish="content_filter"))))
    with pytest.raises(ProviderRefusalError):
        await _call(_Recorder(httpx.Response(200, json=_completion(None, refusal="Tôi không thể hỗ trợ."))))


@pytest.mark.parametrize(
    ("content", "finish", "retryable"),
    [
        ('{"criteria": [', "stop", True),  # JSON hỏng
        ('{"criteria": "không phải danh sách"}', "stop", True),  # sai schema
        ("", "stop", True),  # rỗng
        ('{"criteria": [{"id": "a"', "length", False),  # bị cắt do giới hạn token
    ],
)
async def test_malformed_output_raises_provider_error(content: str, finish: str, retryable: bool) -> None:
    rec = _Recorder(httpx.Response(200, json=_completion(content, finish=finish)))
    with pytest.raises(ProviderError) as info:
        await _call(rec)
    assert info.value.retryable is retryable and not isinstance(info.value, ProviderRefusalError)
    assert len(rec.requests) == 1  # đầu ra sai cấu trúc không tự gọi lại (giống đường Anthropic)


@pytest.mark.parametrize(
    ("response", "retryable"),
    [
        (httpx.Response(200, text="<html>bad gateway</html>"), True),
        (httpx.Response(200, json=["không phải đối tượng"]), True),
        (httpx.Response(200, json={"choices": []}), True),
        (httpx.Response(200, json={"error": {"code": 429, "message": "quá tải"}}), True),
        (httpx.Response(200, json={"error": {"code": 502, "message": "upstream"}}), True),
        (httpx.Response(200, json={"error": {"code": 400, "message": "bad model"}}), False),
    ],
)
async def test_invalid_or_error_bodies_with_http_200(response: httpx.Response, retryable: bool) -> None:
    with pytest.raises(ProviderError) as info:
        await _call(_Recorder(response), max_retries=0)
    assert info.value.retryable is retryable


async def test_fallback_engine_still_uses_offline_rules_when_openai_compatible_fails() -> None:
    rec = _Recorder(httpx.Response(500))
    result = await FallbackEngine(LLMEngine(_provider(rec))).screen(strong_content(), FULL_CRITERIA, {})
    assert result.engine == "heuristic" and result.needs_attention
    assert any(f["rule"] == "llm_fallback" for f in result.flags)


# ---------- Trợ lý hỏi đáp qua provider tương thích OpenAI ----------


async def test_assistant_answers_via_openai_compatible_and_falls_back_on_error() -> None:
    passages = _passages("phu-cap")
    answer = {"answerable": True, "answer": "Học viên nhận tám triệu đồng mỗi tháng.", "citations": [1]}
    rec = _Recorder(httpx.Response(200, json=_completion(answer)))
    got = await ai.LLMAnswerer(_provider(rec, model="google/gemini-2.5-flash-lite")).answer("Phụ cấp?", passages)
    assert not got.abstained and got.citations == [1] and got.engine == "llm:openrouter"
    assert got.model == "google/gemini-2.5-flash-lite" and got.usage is not None and got.usage.output_tokens == 300
    assert rec.bodies[0]["response_format"]["json_schema"]["name"] == "LLMAnswer"

    broken = ai.LLMAnswerer(_provider(_Recorder(httpx.Response(200, json=_completion("không phải JSON")))))
    fallback = await ai.FallbackAnswerer(broken, ai.ExtractiveAnswerer()).answer(
        "Phụ cấp hàng tháng là bao nhiêu?", passages
    )
    assert fallback.engine == "extractive" and fallback.note == "fallback:ProviderError"


# ---------- Chọn provider theo cấu hình ----------


@pytest.mark.parametrize(
    ("choice", "llm_key", "anthropic_key", "expected"),
    [
        ("auto", FAKE_KEY, None, "openai_compatible"),
        ("auto", FAKE_KEY, "sk-ant-test", "openai_compatible"),  # có cả hai: ưu tiên OpenRouter
        ("auto", None, "sk-ant-test", "anthropic"),
        ("auto", None, None, None),
        ("auto", "", "", None),
        ("openai_compatible", FAKE_KEY, "sk-ant-test", "openai_compatible"),
        ("openai_compatible", None, "sk-ant-test", None),  # chỉ định rõ thì không tự đổi nhà cung cấp
        ("anthropic", FAKE_KEY, "sk-ant-test", "anthropic"),
        ("anthropic", FAKE_KEY, None, None),
    ],
)
def test_provider_kind_resolution(choice: str, llm_key: str | None, anthropic_key: str | None, expected: Any) -> None:
    settings = _settings(llm_provider=choice, llm_api_key=llm_key, anthropic_api_key=anthropic_key)
    assert resolve_provider_kind(settings) == expected


def test_get_engine_picks_openai_compatible_by_default_and_offline_without_key() -> None:
    settings = _settings(llm_api_key=FAKE_KEY)
    engine = get_engine(settings, "llm")
    assert isinstance(engine, FallbackEngine) and engine.name == "llm:openrouter"
    provider = engine.primary.provider
    assert isinstance(provider, OpenAICompatibleProvider) and provider.model == settings.llm_scoring_model
    assert isinstance(get_engine(settings, "heuristic"), HeuristicEngine)  # tổ chức chọn offline thì vẫn offline
    assert isinstance(get_engine(settings), HeuristicEngine)  # AI_ENGINE mặc định là heuristic
    assert isinstance(get_engine(_settings(), "llm"), HeuristicEngine)


def test_get_engine_keeps_anthropic_when_only_anthropic_key() -> None:
    settings = _settings(anthropic_api_key="sk-ant-test", ai_engine="llm")
    engine = get_engine(settings)
    assert isinstance(engine, FallbackEngine) and engine.name == "llm:anthropic"
    assert isinstance(engine.primary.provider, AnthropicProvider)
    assert engine.primary.provider.model == settings.ai_scoring_model
    assert provider_model(settings, "assistant") == settings.assistant_model


def test_make_provider_uses_purpose_specific_model_and_timeout() -> None:
    settings = _settings(llm_api_key=FAKE_KEY, llm_base_url="https://api.openai.com/v1", llm_json_mode="json_object")
    scoring, assistant = make_provider(settings, "scoring"), make_provider(settings, "assistant")
    assert isinstance(scoring, OpenAICompatibleProvider) and isinstance(assistant, OpenAICompatibleProvider)
    assert scoring.model == settings.llm_scoring_model and assistant.model == settings.llm_assistant_model
    assert scoring._timeout == 60.0 and assistant._timeout == 20.0 and assistant._json_mode == "json_object"
    assert assistant.name == "openai"
    assert make_provider(_settings(), "scoring") is None


def test_build_answerer_selects_provider_like_screening() -> None:
    with_key = _settings(llm_api_key=FAKE_KEY)
    answerer = assistant_svc.build_answerer(with_key, "llm")
    assert isinstance(answerer, ai.FallbackAnswerer) and answerer.name == "llm:openrouter"
    assert isinstance(assistant_svc.build_answerer(with_key, "extractive"), ai.ExtractiveAnswerer)
    assert isinstance(assistant_svc.build_answerer(_settings(), "llm"), ai.ExtractiveAnswerer)
    claude = assistant_svc.build_answerer(_settings(anthropic_api_key="sk-ant-test"), "llm")
    assert isinstance(claude, ai.FallbackAnswerer) and claude.name == "llm:anthropic"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("OpenRouter", "openai_compatible"), ("gemini", "openai_compatible"), ("", "auto"), (" Anthropic ", "anthropic")],
)
def test_llm_provider_setting_accepts_aliases(raw: str, expected: str) -> None:
    assert _settings(llm_provider=raw).llm_provider == expected


@pytest.mark.parametrize("field", ["llm_provider", "llm_json_mode"])
def test_invalid_llm_settings_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: "khong-co"})


async def test_overview_reports_llm_configured_for_openai_compatible_key(login_as, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.services import overview

    settings = _settings(llm_api_key=FAKE_KEY)
    monkeypatch.setattr(overview, "get_settings", lambda: settings)
    admin = await login_as("admin")
    data = (await admin.get("/api/v1/admin/overview")).json()
    assert data["ai"]["llm_configured"] is True and data["ai"]["model"] == settings.llm_scoring_model
    assert FAKE_KEY not in json.dumps(data)


# ---------- Chi phí ----------


def test_default_models_have_known_prices() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    settings = _settings()
    assert estimate_cost_usd("google/gemini-2.5-flash", usage, settings) == pytest.approx(2.80)
    assert estimate_cost_usd("google/gemini-2.5-flash-lite", usage, settings) == pytest.approx(0.50)
    assert estimate_cost_usd("gemini-2.5-flash-lite", usage, settings) == pytest.approx(0.50)
    assert estimate_cost_usd("gpt-4.1-mini", usage, settings) == pytest.approx(2.00)
    assert estimate_cost_usd("claude-haiku-4-5-20251001", usage, settings) == pytest.approx(6.00)
    assert estimate_cost_usd("meta-llama/llama-3.3-70b-instruct:free", usage, settings) == 0.0
    for model in (settings.llm_scoring_model, settings.llm_assistant_model):
        assert estimate_cost_usd(model, usage, settings) > 0


def test_price_override_applies_to_configured_models(caplog: pytest.LogCaptureFixture) -> None:
    settings = _settings(
        llm_scoring_model="acme/new-model", llm_price_input_per_mtok=0.5, llm_price_output_per_mtok=1.5
    )
    usage = {"input_tokens": 2_000_000, "output_tokens": 1_000_000, "cache_read_tokens": 1_000_000}
    with caplog.at_level(logging.WARNING, logger="src.ai.pricing"):
        assert estimate_cost_usd("acme/new-model", usage, settings) == pytest.approx(2 * 0.5 + 1.5 + 0.5)
    assert not caplog.records
    # chỉ đặt một trong hai giá thì chưa có hiệu lực
    half = _settings(llm_scoring_model="acme/new-model", llm_price_input_per_mtok=0.5)
    assert pricing.price_for("acme/new-model", half) == pricing.FALLBACK_PRICE


def test_unknown_model_uses_fallback_price_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    pricing._warned_models.discard("acme/unknown-xyz")
    usage = {"input_tokens": 1_000_000}
    with caplog.at_level(logging.WARNING, logger="src.ai.pricing"):
        first = estimate_cost_usd("acme/unknown-xyz", usage, _settings())
        second = estimate_cost_usd("acme/unknown-xyz", usage, _settings())
    assert first == second == pricing.FALLBACK_PRICE[0]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and getattr(warnings[0], "model", None) == "acme/unknown-xyz"
    assert FAKE_KEY not in caplog.text
