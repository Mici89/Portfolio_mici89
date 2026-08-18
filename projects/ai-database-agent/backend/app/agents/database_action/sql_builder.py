from dataclasses import dataclass
from typing import Any

from app.adapters.database.dialect import SqlDialect, get_dialect
from app.core.exceptions import UnsafeDatabaseActionError
from app.models import (
    ActionCondition,
    ActionLookupCondition,
    ActionLookupReference,
    ActionPrimitiveValue,
    ActionValueLookup,
    DatabaseActionDraft,
)


@dataclass(frozen=True, slots=True)
class ActionSQL:
    statement: str
    parameters: dict[str, ActionPrimitiveValue]
    display_statement: str
    count_statement: str
    count_parameters: dict[str, ActionPrimitiveValue]
    preview_statement: str
    preview_parameters: dict[str, ActionPrimitiveValue]
    lock_statement: str
    insert_lookup_statement: str | None
    insert_lookup_parameters: dict[str, ActionPrimitiveValue]


@dataclass(frozen=True, slots=True)
class ActionLookupSQL:
    statement: str
    parameters: dict[str, ActionPrimitiveValue]
    display_statement: str


class ActionSQLBuilder:
    def __init__(self, dialect: SqlDialect | None = None) -> None:
        self.dialect = dialect or get_dialect("mysql")

    def build_lookup(self, lookup: ActionValueLookup) -> ActionLookupSQL:
        table = self._identifier(lookup.source_table)
        selected_columns = list(
            dict.fromkeys(
                [
                    lookup.source_value_column,
                    *(condition.column_name for condition in lookup.conditions),
                ]
            )
        )
        select_sql = ", ".join(self._identifier(column) for column in selected_columns)
        where_sql, parameters = self._where(lookup.conditions, prefix="lookup")
        statement = self.dialect.limit_select(
            f"SELECT {select_sql} FROM {table}{where_sql}",
            11,
        )
        return ActionLookupSQL(
            statement=statement,
            parameters=parameters,
            display_statement=self._display(statement, parameters),
        )

    def build(self, draft: DatabaseActionDraft, *, max_rows: int) -> ActionSQL:
        table = self._identifier(draft.table_name)
        if draft.action_type == "INSERT":
            return self._insert(draft, table)
        if not draft.conditions:
            raise UnsafeDatabaseActionError("UPDATE和DELETE必须包含WHERE条件")

        where_sql, where_parameters = self._where(draft.conditions, prefix="where")
        matched_alias = self._identifier("matched_row_count")
        count_statement = f"SELECT COUNT(*) AS {matched_alias} FROM {table}{where_sql}"
        preview_statement = self.dialect.limit_select(
            f"SELECT * FROM {table}{where_sql}",
            max_rows,
        )
        lock_statement = self.dialect.lock_select(
            f"SELECT * FROM {table}{where_sql}",
            max_rows + 1,
        )
        if draft.action_type == "UPDATE":
            if not draft.assignments:
                raise UnsafeDatabaseActionError("UPDATE必须至少修改一个字段")
            assignment_parameters = {
                f"set_{index}": self._resolved_value(item.value)
                for index, item in enumerate(draft.assignments)
            }
            assignments = ", ".join(
                f"{self._identifier(item.column_name)} = :set_{index}"
                for index, item in enumerate(draft.assignments)
            )
            statement = f"UPDATE {table} SET {assignments}{where_sql}"
            parameters = {**assignment_parameters, **where_parameters}
        else:
            if draft.assignments:
                raise UnsafeDatabaseActionError("DELETE不能包含字段赋值")
            statement = f"DELETE FROM {table}{where_sql}"
            parameters = where_parameters
        return ActionSQL(
            statement=statement,
            parameters=parameters,
            display_statement=self._display(statement, parameters),
            count_statement=count_statement,
            count_parameters=where_parameters,
            preview_statement=preview_statement,
            preview_parameters=where_parameters,
            lock_statement=lock_statement,
            insert_lookup_statement=None,
            insert_lookup_parameters={},
        )

    def _insert(self, draft: DatabaseActionDraft, table: str) -> ActionSQL:
        if not draft.assignments:
            raise UnsafeDatabaseActionError("INSERT必须至少提供一个字段")
        if draft.conditions:
            raise UnsafeDatabaseActionError("INSERT不能包含筛选条件")
        columns = ", ".join(self._identifier(item.column_name) for item in draft.assignments)
        parameters = {
            f"insert_{index}": self._resolved_value(item.value)
            for index, item in enumerate(draft.assignments)
        }
        placeholders = ", ".join(f":insert_{index}" for index in range(len(draft.assignments)))
        statement = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        lookup_where = " AND ".join(
            (
                f"({self._identifier(item.column_name)} = :insert_{index} OR "
                f"({self._identifier(item.column_name)} IS NULL AND "
                f":insert_{index} IS NULL))"
            )
            for index, item in enumerate(draft.assignments)
        )
        lookup_statement = self.dialect.limit_select(
            f"SELECT * FROM {table} WHERE {lookup_where}",
            2,
        )
        matched_alias = self._identifier("matched_row_count")
        empty_select = f"SELECT * FROM {table} WHERE 1 = 0"
        return ActionSQL(
            statement=statement,
            parameters=parameters,
            display_statement=self._display(statement, parameters),
            count_statement=f"SELECT 0 AS {matched_alias}",
            count_parameters={},
            preview_statement=empty_select,
            preview_parameters={},
            lock_statement=self.dialect.lock_select(empty_select, 1),
            insert_lookup_statement=lookup_statement,
            insert_lookup_parameters=parameters,
        )

    def _where(
        self,
        conditions: list[ActionCondition] | list[ActionLookupCondition],
        *,
        prefix: str,
    ) -> tuple[str, dict[str, ActionPrimitiveValue]]:
        fragments: list[str] = []
        parameters: dict[str, ActionPrimitiveValue] = {}
        parameter_index = 0
        for condition in conditions:
            column = self._identifier(condition.column_name)
            operator = condition.operator
            if operator in {"IS NULL", "IS NOT NULL"}:
                fragments.append(f"{column} {operator}")
                continue
            if operator == "IN":
                if not isinstance(condition.value, list) or not condition.value:
                    raise UnsafeDatabaseActionError("IN条件必须包含至少一个值")
                binds = []
                for value in condition.value:
                    bind = f"{prefix}_{parameter_index}"
                    parameter_index += 1
                    binds.append(f":{bind}")
                    parameters[bind] = value
                fragments.append(f"{column} IN ({', '.join(binds)})")
                continue
            if isinstance(condition.value, list):
                raise UnsafeDatabaseActionError(f"{operator}条件不能使用数组值")
            bind = f"{prefix}_{parameter_index}"
            parameter_index += 1
            fragments.append(f"{column} {operator} :{bind}")
            parameters[bind] = self._resolved_value(condition.value)
        return f" WHERE {' AND '.join(fragments)}", parameters

    @staticmethod
    def _resolved_value(value: object) -> ActionPrimitiveValue:
        if isinstance(value, ActionLookupReference):
            raise UnsafeDatabaseActionError(f"跨表取值 {value.lookup_id} 尚未解析，禁止生成写入SQL")
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise UnsafeDatabaseActionError("数据库操作包含无法参数化的字段值")

    def _identifier(self, value: str) -> str:
        return self.dialect.quote_identifier(value)

    @classmethod
    def _display(
        cls,
        statement: str,
        parameters: dict[str, Any],
    ) -> str:
        rendered = statement
        for name in sorted(parameters, key=len, reverse=True):
            rendered = rendered.replace(f":{name}", cls._literal(parameters[name]))
        return rendered

    @staticmethod
    def _literal(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"
