from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, Connection

from app.adapters.database.sqlalchemy_adapter import SQLAlchemyDatabaseAdapter


class SQLServerDatabaseAdapter(SQLAlchemyDatabaseAdapter):
    driver_name = "mssql+pyodbc"

    def build_url(self) -> URL:
        options = {
            "driver": "ODBC Driver 18 for SQL Server",
            "TrustServerCertificate": "yes",
            **dict(self.config.options or {}),
        }
        return URL.create(
            self.driver_name,
            username=self.config.username,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            query=options,
        )

    def connect_args(self) -> dict[str, Any]:
        return {"timeout": self.config.connect_timeout_seconds}

    def server_version(self, connection: Connection) -> str:
        statement = "SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(128))"
        return str(connection.execute(text(statement)).scalar_one())

    def character_set(self, connection: Connection) -> str:
        return "UTF-16/Unicode"

    def collation(self, connection: Connection) -> str:
        return str(
            connection.execute(
                text("SELECT CAST(DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS NVARCHAR(128))")
            ).scalar_one()
        )
