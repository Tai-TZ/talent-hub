from src.ai.heuristic import HeuristicEngine
from src.ai.llm_engine import FallbackEngine, LLMEngine
from src.ai.providers import AnthropicProvider
from src.ai.screening import ScreeningEngine
from src.config import Settings


def get_engine(settings: Settings, org_engine: str | None = None) -> ScreeningEngine:
    """Chọn động cơ: cài đặt của tổ chức ưu tiên hơn mặc định hệ thống. `llm` thiếu khoá API thì dùng luật offline."""
    wanted = org_engine or settings.ai_engine
    if wanted == "llm" and settings.anthropic_api_key:
        provider = AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.ai_scoring_model)
        return FallbackEngine(LLMEngine(provider))
    return HeuristicEngine()
