from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.adapters.database.sqlalchemy_adapter import SQLAlchemyDatabaseAdapter


class PostgreSQLDatabaseAdapter(SQLAlchemyDatabaseAdapter):
    driver_name = "postgresql+psycopg"

    def connect_args(self) -> dict[str, Any]:
        return {"connect_timeout": self.config.connect_timeout_seconds}

    def server_version(self, connection: Connection) -> str:
        return str(connection.execute(text("SHOW server_version")).scalar_one())

    def character_set(self, connection: Connection) -> str:
        return str(connection.execute(text("SHOW server_encoding")).scalar_one())

    def collation(self, connection: Connection) -> str:
        value = connection.execute(
            text("SELECT datcollate FROM pg_database WHERE datname = current_database()")
        ).scalar_one_or_none()
        return str(value or "")
