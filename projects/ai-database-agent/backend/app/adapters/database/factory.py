from app.adapters.database.base import BaseDatabaseAdapter, DatabaseConnectionConfig
from app.adapters.database.mysql import MySQLDatabaseAdapter
from app.adapters.database.oracle import OracleDatabaseAdapter
from app.adapters.database.postgresql import PostgreSQLDatabaseAdapter
from app.adapters.database.sqlserver import SQLServerDatabaseAdapter


class DatabaseAdapterFactory:
    @staticmethod
    def create(config: DatabaseConnectionConfig) -> BaseDatabaseAdapter:
        adapters = {
            "mysql": MySQLDatabaseAdapter,
            "postgresql": PostgreSQLDatabaseAdapter,
            "sqlserver": SQLServerDatabaseAdapter,
            "oracle": OracleDatabaseAdapter,
        }
        adapter_class = adapters.get(config.database_type)
        if adapter_class is None:
            raise ValueError(f"Unsupported database type: {config.database_type}")
        return adapter_class(config)
