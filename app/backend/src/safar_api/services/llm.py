import logging

from langchain_openai import ChatOpenAI

from safar_api.config import settings

logger = logging.getLogger(__name__)


def planning_llm() -> ChatOpenAI:
    """Model for itineraries, destination research, web answers, and trip Q&A."""
    return ChatOpenAI(
        model=settings.openai_secondary_model,
        temperature=0.2,
        api_key=settings.openai_api_key or None,
        store=True,
    )


def utility_llm() -> ChatOpenAI:
    """Smaller model for structured extraction and conversation summarization."""
    return ChatOpenAI(
        model=settings.openai_weather_model,
        temperature=0.2,
        api_key=settings.openai_api_key or None,
        store=True,
    )


def supervisor_llm() -> ChatOpenAI:
    """Model that decides which trip tools to call and writes the user reply."""
    model = settings.supervisor_model
    logger.info("Using supervisor model=%s", model)
    # gpt-6-luna rejects reasoning_effort on /v1/chat/completions when tools
    # are bound. The Responses API accepts both.
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key or None,
        store=True,
        use_responses_api=True,
        reasoning_effort="medium",
    )
