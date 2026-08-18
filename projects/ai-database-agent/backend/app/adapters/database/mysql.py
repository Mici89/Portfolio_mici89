from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.adapters.database.sqlalchemy_adapter import SQLAlchemyDatabaseAdapter


class MySQLDatabaseAdapter(SQLAlchemyDatabaseAdapter):
    driver_name = "mysql+pymysql"

    def connect_args(self) -> dict[str, Any]:
        timeout = self.config.connect_timeout_seconds
        return {
            "connect_timeout": timeout,
            "read_timeout": timeout,
            "write_timeout": timeout,
            "charset": "utf8mb4",
        }

    def character_set(self, connection: Connection) -> str:
        return str(connection.execute(text("SELECT @@character_set_database")).scalar_one())

    def collation(self, connection: Connection) -> str:
        return str(connection.execute(text("SELECT @@collation_database")).scalar_one())
