from app.ai.llm_provider import LLMProvider
from app.config import get_settings


def get_llm_provider() -> LLMProvider | None:
    """Returns None when no provider is configured.

    Callers must treat that as a normal, expected case (no ANTHROPIC_API_KEY
    set) and degrade gracefully to milestone-1 behavior — never raise for it
    in a code path a user can reach without AI features.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None

    from app.ai.providers.anthropic_provider import AnthropicProvider

    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
