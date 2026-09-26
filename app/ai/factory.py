import logging

from app.ai.llm_provider import LLMProvider
from app.config import get_settings
from app.models.enums import LLMProviderType
from app.models.project import ProjectSettings

logger = logging.getLogger(__name__)

# Loading a local GGUF model takes real time (seconds), so instances are
# cached per model path for the life of the process rather than reconstructed
# per request.
_local_provider_cache: dict[str, LLMProvider] = {}


def get_llm_provider(settings: ProjectSettings) -> LLMProvider | None:
    """Returns None whenever no usable provider is configured for this
    project's settings (no API key, or no local model selected/downloaded
    yet). Callers must treat that as a normal, expected case and degrade
    gracefully — never raise for it in a code path a user can reach without
    AI features.
    """
    if settings.llm_provider == LLMProviderType.ANTHROPIC:
        return _get_anthropic_provider()
    if settings.llm_provider == LLMProviderType.LOCAL:
        return _get_local_provider(settings.local_model_id)
    return None


def _get_anthropic_provider() -> LLMProvider | None:
    app_settings = get_settings()
    if not app_settings.anthropic_api_key:
        return None
    from app.ai.providers.anthropic_provider import AnthropicProvider

    return AnthropicProvider(
        api_key=app_settings.anthropic_api_key, model=app_settings.anthropic_model
    )


def _get_local_provider(local_model_id: str | None) -> LLMProvider | None:
    if not local_model_id:
        return None

    from app.services.model_service import get_model_path

    model_path = get_model_path(local_model_id)
    if model_path is None:
        return None  # selected but not downloaded yet

    if model_path not in _local_provider_cache:
        from app.ai.providers.local_llama_provider import LocalLlamaProvider

        logger.info("Loading local model into memory: %s", model_path)
        _local_provider_cache[model_path] = LocalLlamaProvider(model_path=model_path)
    return _local_provider_cache[model_path]
