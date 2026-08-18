from pathlib import Path

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    cors_origins: list[str] = [
        "http://localhost:3000",
    ]
    retrieval_min_similarity: float = 0.5
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    chat_model: str = "deepseek-v4-flash"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_dimension: int = 1024
    app_name: str = "Enterprise Knowledge Agent API"
    database_url: str
    storage_dir: Path = Path("storage")
    max_upload_size: int = 10 * 1024 * 1024
    max_document_retries: int = 3
    agent_max_steps: int = 4
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
