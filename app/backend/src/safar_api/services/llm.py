from langchain_openai import ChatOpenAI

from safar_api.config import settings


def secondary_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_secondary_model,
        temperature=0.2,
        api_key=settings.openai_api_key or None,
    )


def flight_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_flight_model,
        temperature=0.2,
        api_key=settings.openai_api_key or None,
    )


def weather_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_weather_model,
        temperature=0.2,
        api_key=settings.openai_api_key or None,
    )
