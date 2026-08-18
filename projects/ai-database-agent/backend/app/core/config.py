from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "AI Database Agent API"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    db_type: Literal["mysql", "postgresql", "sqlserver", "oracle"] = "mysql"
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3307, ge=1, le=65535)
    db_name: str = "legacy_enterprise"
    db_schema: str | None = None
    db_user: str = "ai_reader"
    db_password: SecretStr
    db_write_user: str = "ai_writer"
    db_write_password: SecretStr
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    connection_profile_storage_dir: Path = BACKEND_DIR / "data" / "connections"
    credential_storage_dir: Path = BACKEND_DIR / "data" / "credentials"
    snapshot_storage_dir: Path = BACKEND_DIR / "data" / "snapshots"
    understanding_run_storage_dir: Path = BACKEND_DIR / "data" / "understanding_runs"
    understanding_max_evidence_rounds: int = Field(default=3, ge=1, le=10)
    understanding_graph_checkpoint_path: Path = (
        BACKEND_DIR / "data" / "checkpoints" / "understanding_graph.sqlite"
    )
    semantic_catalog_storage_dir: Path = BACKEND_DIR / "data" / "semantic_catalog"
    semantic_review_storage_dir: Path = BACKEND_DIR / "data" / "semantic_reviews"
    catalog_build_job_storage_dir: Path = BACKEND_DIR / "data" / "catalog_build_jobs"
    database_query_storage_dir: Path = BACKEND_DIR / "data" / "database_queries"
    query_graph_checkpoint_path: Path = (
        BACKEND_DIR / "data" / "checkpoints" / "query_graph.sqlite"
    )
    query_session_storage_dir: Path = BACKEND_DIR / "data" / "query_sessions"
    database_query_max_attempts: int = Field(default=3, ge=1, le=5)
    database_action_storage_dir: Path = BACKEND_DIR / "data" / "database_actions"
    database_action_max_affected_rows: int = Field(default=100, ge=1, le=1000)
    database_action_max_planning_rounds: int = Field(default=3, ge=1, le=10)
    action_graph_checkpoint_path: Path = (
        BACKEND_DIR / "data" / "checkpoints" / "action_graph.sqlite"
    )
    conversation_graph_checkpoint_path: Path = (
        BACKEND_DIR / "data" / "checkpoints" / "conversation_graph.sqlite"
    )

    auth_operator_username: str = "db_operator"
    auth_operator_password: SecretStr
    auth_token_secret: SecretStr
    auth_token_ttl_minutes: int = Field(default=480, ge=5, le=1440)

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = Field(default=90, ge=10, le=300)
    deepseek_temperature: float = Field(default=0.1, ge=0, le=1)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
