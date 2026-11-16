from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# /.../backend/src/safar_api/config.py -> /.../backend
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (
    _BACKEND_ROOT / ".env",  # backend/.env (optional)
    _BACKEND_ROOT.parent / ".env",  # app/.env (optional)
    _BACKEND_ROOT.parent.parent / ".env",  # repo/.env (optional)
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(p) for p in _ENV_FILES if p.exists()],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    serpapi_api_key: str = ""
    tavily_api_key: str = ""
    # planning_llm: itinerary, research, web answers, trip Q&A
    openai_secondary_model: str = "gpt-5.4-mini-2026-03-17"
    # utility_llm: weather extraction, airport extraction, chat summarization
    openai_weather_model: str = "gpt-4o-mini"
    openai_orchestrator_model: str = "gpt-6-luna"
    agent_max_steps: int = 10
    serpapi_timeout_s: float = 45.0
    # Context size controls (token savings)
    agent_tool_observation_chars: int = 4000
    agent_summarize_after_messages: int = 24
    agent_summarize_keep_messages: int = 10
    agent_clear_tools_trigger_tokens: int = 12000
    agent_clear_tools_keep: int = 3
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    langsmith_api_key: str = ""
    langsmith_project: str = "trip planner"
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    @property
    def supervisor_model(self) -> str:
        return self.openai_orchestrator_model or self.openai_secondary_model

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
