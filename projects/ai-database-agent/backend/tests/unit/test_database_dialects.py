from app.adapters.database import DatabaseAdapterFactory, DatabaseConnectionConfig, get_dialect
from app.adapters.database.mysql import MySQLDatabaseAdapter
from app.adapters.database.oracle import OracleDatabaseAdapter
from app.adapters.database.postgresql import PostgreSQLDatabaseAdapter
from app.adapters.database.sqlserver import SQLServerDatabaseAdapter
from app.agents.database_action import ActionSQLBuilder
from app.models import ActionAssignment, ActionCondition, DatabaseActionDraft


def config(database_type):
    ports = {
        "mysql": 3306,
        "postgresql": 5432,
        "sqlserver": 1433,
        "oracle": 1521,
    }
    return DatabaseConnectionConfig(
        database_type=database_type,
        host="db.internal",
        port=ports[database_type],
        database="enterprise",
        username="agent",
        password="secret",
    )


def update_draft() -> DatabaseActionDraft:
    return DatabaseActionDraft(
        summary="更新状态",
        action_type="UPDATE",
        table_name="employee",
        assignments=[ActionAssignment(column_name="status", value="active")],
        conditions=[ActionCondition(column_name="employee_id", operator="=", value=7)],
        expected_effect="更新一行",
    )


def test_factory_creates_all_supported_adapters() -> None:
    factory = DatabaseAdapterFactory()
    assert isinstance(factory.create(config("mysql")), MySQLDatabaseAdapter)
    assert isinstance(factory.create(config("postgresql")), PostgreSQLDatabaseAdapter)
    assert isinstance(factory.create(config("sqlserver")), SQLServerDatabaseAdapter)
    assert isinstance(factory.create(config("oracle")), OracleDatabaseAdapter)


def test_write_builder_uses_database_specific_identifier_and_pagination() -> None:
    postgres = ActionSQLBuilder(get_dialect("postgresql")).build(update_draft(), max_rows=5)
    assert postgres.statement.startswith('UPDATE "employee" SET "status" = :set_0')
    assert postgres.preview_statement.endswith("LIMIT 5")
    assert postgres.lock_statement.endswith("LIMIT 6 FOR UPDATE")

    sqlserver = ActionSQLBuilder(get_dialect("sqlserver")).build(update_draft(), max_rows=5)
    assert sqlserver.statement.startswith("UPDATE [employee] SET [status] = :set_0")
    assert sqlserver.preview_statement.startswith("SELECT TOP (5) *")
    assert "WITH (UPDLOCK, ROWLOCK)" in sqlserver.lock_statement
    assert "LIMIT" not in sqlserver.lock_statement

    oracle = ActionSQLBuilder(get_dialect("oracle")).build(update_draft(), max_rows=5)
    assert oracle.statement.startswith('UPDATE "employee" SET "status" = :set_0')
    assert oracle.preview_statement.endswith("FETCH FIRST 5 ROWS ONLY")
    assert oracle.lock_statement.endswith("AND ROWNUM <= 6 FOR UPDATE")
