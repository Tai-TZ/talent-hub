from src.ai.heuristic import HeuristicEngine
from src.ai.llm_engine import FallbackEngine, LLMEngine
from src.ai.providers import AnthropicProvider
from src.ai.screening import ScreeningEngine
from src.config import Settings


def get_engine(settings: Settings) -> ScreeningEngine:
    """Chọn động cơ theo cấu hình. `llm` thiếu khoá API thì dùng luật offline thay vì lỗi."""
    if settings.ai_engine == "llm" and settings.anthropic_api_key:
        provider = AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.ai_scoring_model)
        return FallbackEngine(LLMEngine(provider))
    return HeuristicEngine()
