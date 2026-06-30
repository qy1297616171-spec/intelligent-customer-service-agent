from customer_service.ai_platform.contracts import AnswerGenerator
from customer_service.ai_platform.generation import (
    FallbackGenerator,
    GroundedMockGenerator,
    OpenAICompatibleGenerator,
)
from customer_service.bootstrap.config import Settings


def build_answer_generator(settings: Settings) -> AnswerGenerator:
    provider = settings.ai_model_provider.strip().lower()
    fallback = GroundedMockGenerator()
    if provider == "mock":
        return fallback
    if provider not in {"openai-compatible", "openai_compatible"}:
        raise ValueError(
            "AI_MODEL_PROVIDER must be 'mock' or 'openai-compatible'"
        )
    if not settings.ai_model_api_key.strip():
        raise ValueError("AI_MODEL_API_KEY is required for a real model provider")
    if not settings.ai_model_base_url.startswith(("https://", "http://")):
        raise ValueError("AI_MODEL_BASE_URL must be an HTTP(S) URL")

    primary = OpenAICompatibleGenerator(
        base_url=settings.ai_model_base_url,
        api_key=settings.ai_model_api_key,
        model=settings.ai_model_name,
        timeout_seconds=settings.ai_model_timeout_seconds,
        temperature=settings.ai_model_temperature,
        max_tokens=settings.ai_model_max_tokens,
    )
    if settings.ai_model_fallback_enabled:
        return FallbackGenerator(primary, fallback)
    return primary

