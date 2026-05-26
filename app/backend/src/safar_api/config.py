from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILES = (
    _ROOT / "app" / ".env",
    _ROOT / ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(p) for p in _ENV_FILES if p.exists()],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    serpapi_api_key: str = ""
    # traveltest.ipynb: secondary_llm, flight llm, weather llm
    openai_secondary_model: str = "gpt-5.4-mini-2026-03-17"
    openai_flight_model: str = "gpt-5-mini-2025-08-07"
    openai_weather_model: str = "gpt-4o-mini"
    cors_origins: str = "http://localhost:3000"
    langsmith_api_key: str = ""
    langsmith_project: str = "trip planner"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
