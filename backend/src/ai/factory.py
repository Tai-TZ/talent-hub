from typing import Literal

from src.ai.heuristic import HeuristicEngine
from src.ai.llm_engine import FallbackEngine, LLMEngine
from src.ai.providers import AnthropicProvider, LLMProvider, OpenAICompatibleProvider
from src.ai.screening import ScreeningEngine
from src.config import Settings

Purpose = Literal["scoring", "assistant"]
ProviderKind = Literal["openai_compatible", "anthropic"]

# Trợ lý trả lời người dùng trực tiếp nên chờ ngắn hơn; chấm hồ sơ chạy nền nên cho phép lâu hơn.
TIMEOUTS: dict[Purpose, float] = {"scoring": 60.0, "assistant": 20.0}


def resolve_provider_kind(settings: Settings) -> ProviderKind | None:
    """Nhà cung cấp LLM dùng được theo cấu hình; None khi thiếu khoá (khi đó chạy động cơ offline).

    `auto`: ưu tiên dịch vụ tương thích OpenAI (LLM_API_KEY), rồi Anthropic (ANTHROPIC_API_KEY).
    Chỉ định rõ một nhà cung cấp mà thiếu khoá của nó thì không tự chuyển sang nhà cung cấp kia.
    """
    choice = settings.llm_provider
    if choice in ("auto", "openai_compatible") and settings.llm_api_key:
        return "openai_compatible"
    if choice in ("auto", "anthropic") and settings.anthropic_api_key:
        return "anthropic"
    return None


def provider_model(settings: Settings, purpose: Purpose) -> str | None:
    """Mô hình sẽ được gọi cho tác vụ này (None khi không có LLM nào được cấu hình)."""
    kind = resolve_provider_kind(settings)
    if kind == "openai_compatible":
        return settings.llm_scoring_model if purpose == "scoring" else settings.llm_assistant_model
    if kind == "anthropic":
        return settings.ai_scoring_model if purpose == "scoring" else settings.assistant_model
    return None


def make_provider(settings: Settings, purpose: Purpose) -> LLMProvider | None:
    """Một chỗ duy nhất chọn và dựng provider cho cả chấm hồ sơ lẫn trợ lý hỏi đáp."""
    kind = resolve_provider_kind(settings)
    model = provider_model(settings, purpose)
    if kind is None or model is None:
        return None
    timeout = TIMEOUTS[purpose]
    if kind == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=settings.llm_api_key or "",
            model=model,
            base_url=settings.llm_base_url,
            timeout=timeout,
            json_mode=settings.llm_json_mode,
            app_url=settings.public_base_url,
        )
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=model, timeout=timeout)


def get_engine(settings: Settings, org_engine: str | None = None) -> ScreeningEngine:
    """Chọn động cơ: cài đặt của tổ chức ưu tiên hơn mặc định hệ thống. `llm` thiếu khoá API thì dùng luật offline."""
    wanted = org_engine or settings.ai_engine
    provider = make_provider(settings, "scoring") if wanted == "llm" else None
    if provider is not None:
        return FallbackEngine(LLMEngine(provider))
    return HeuristicEngine()
