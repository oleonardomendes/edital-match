from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://edital:edital@localhost:5432/edital_match"

    # anthropic | openai (qualquer API compatível, como Groq) | demo
    llm_provider: str = "demo"
    llm_model: str = "claude-sonnet-5-5"
    llm_api_key: str | None = None
    llm_base_url: str | None = None  # ex.: https://api.groq.com/openai/v1

    # fastembed | openai | hashing
    embedding_provider: str = "hashing"
    embedding_model: str | None = None

    max_upload_mb: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
