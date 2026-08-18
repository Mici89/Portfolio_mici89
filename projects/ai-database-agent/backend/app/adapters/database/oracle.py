from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, Connection

from app.adapters.database.sqlalchemy_adapter import SQLAlchemyDatabaseAdapter


class OracleDatabaseAdapter(SQLAlchemyDatabaseAdapter):
    driver_name = "oracle+oracledb"

    def build_url(self) -> URL:
        query = {"service_name": self.config.database, **dict(self.config.options or {})}
        return URL.create(
            self.driver_name,
            username=self.config.username,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            query=query,
        )

    def connect_args(self) -> dict[str, Any]:
        return {"tcp_connect_timeout": self.config.connect_timeout_seconds}

    def current_user_sql(self) -> str:
        return "SELECT USER FROM DUAL"

    def server_version(self, connection: Connection) -> str:
        return str(
            connection.execute(
                text(
                    "SELECT version_full FROM product_component_version "
                    "WHERE product LIKE 'Oracle%Database%' FETCH FIRST 1 ROWS ONLY"
                )
            ).scalar_one()
        )

    def character_set(self, connection: Connection) -> str:
        value = connection.execute(
            text(
                "SELECT value FROM nls_database_parameters "
                "WHERE parameter = 'NLS_CHARACTERSET'"
            )
        ).scalar_one_or_none()
        return str(value or "")

    def collation(self, connection: Connection) -> str:
        value = connection.execute(
            text(
                "SELECT value FROM nls_database_parameters "
                "WHERE parameter = 'NLS_COMP'"
            )
        ).scalar_one_or_none()
        return str(value or "")
