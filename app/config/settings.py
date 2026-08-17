"""Environment-backed application settings.

The application reads runtime values from ``.env`` or the process environment.
Business logic must consume these settings rather than embedding operational
values such as model names, timeouts, or rate limits.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration for the API, AI, research, and persistence layers."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "groq"
    gemini_api_key: str = ""
    gemini_model: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    llm_rpm_limit: int = 15
    llm_request_delay: float = 4.0
    llm_max_retries: int = 3
    llm_retry_backoff: float = 2.0
    llm_timeout: float = 60.0

    pubmed_rpm_limit: int = 180
    pubmed_request_delay: float = 0.4
    pubmed_max_retries: int = 2
    pubmed_timeout: float = 30.0
    pubmed_max_results: int = 3
    pubmed_tool: str = "curapharm_research"
    pubmed_email: str = ""
    pubmed_api_key: str = ""

    openfda_rpm_limit: int = 40
    openfda_request_delay: float = 1.5
    openfda_max_retries: int = 2
    openfda_timeout: float = 30.0
    openfda_max_results: int = 3
    openfda_api_key: str = ""

    research_cache_minutes: int = 60

    database_url: str = "sqlite:///./data/curapharm.db"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    api_base_url: str = "http://127.0.0.1:8000/api"


@lru_cache(maxsize=1)
def get_settings():
    """Return one cached settings instance for the running process."""
    return Settings()
