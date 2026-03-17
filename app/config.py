from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    model_name: str = Field("openai/gpt-4o-mini", description="OpenRouter model slug")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_referer: str = "https://github.com/automated-srs-generator"

    # Database
    db_uri: str = Field(
        "postgresql+psycopg://srs_user:srs_pass@localhost:5432/srs_db",
        description="PostgreSQL connection URI (psycopg3 driver)",
    )

    # Vector store
    chroma_path: str = Field(".chroma", description="ChromaDB persistence directory")
    chroma_collection: str = "regulatory_docs"

    # App server
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_reload: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_credentials: bool = True

    # LangGraph
    max_mermaid_retries: int = 3

    # Vector store lifecycle
    vectorstore_seed_if_empty: bool = True
    vectorstore_force_reseed: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:3000"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env once)."""
    return Settings()  # type: ignore[call-arg]
