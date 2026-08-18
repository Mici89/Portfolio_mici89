from datetime import UTC, datetime

import pytest

from app.adapters.database import DatabaseSelectResult, DatabaseWriteResult
from app.adapters.database.sqlalchemy_adapter import (
    SQLAlchemyDatabaseAdapter,
)
from app.agents.database_action import ActionSQLBuilder
from app.core.exceptions import UnsafeDatabaseActionError
from app.models import (
    ActionAssignment,
    ActionCondition,
    ActionLookupCondition,
    ActionLookupReference,
    ActionValueLookup,
    ColumnSchema,
    DatabaseActionDraft,
    DeclaredRelationship,
    LLMTokenUsage,
    QueryFieldMapping,
    QuerySemanticSource,
    QuerySession,
    ScanStatistics,
    TableSchema,
    UserPrincipal,
)
from app.repositories.database_action import FileDatabaseActionRepository
from app.repositories.database_snapshot import FileDatabaseSnapshotRepository
from app.repositories.query_session import FileQuerySessionRepository
from app.services.database_action import DatabaseActionService
from app.services.effective_semantics import EffectiveSemanticContext
from tests.unit.test_semantic_review import make_snapshot


class FakePlanningAgent:
    async def plan(
        self,
        snapshot,
        message,
        semantic_payload,
        conversation_context=None,
        planning_context=None,
    ):
        return (
            DatabaseActionDraft(
                summary="更新指定员工工资",
                action_type="UPDATE",
                table_name="rs_gzff",
                assignments=[ActionAssignment(column_name="gz", value=12000)],
                conditions=[
                    ActionCondition(
                        column_name="ygbh",
                        operator="=",
                        value="E00001' OR 1=1",
                    )
                ],
                expected_effect="只更新匹配员工的工资",
            ),
            "fake",
            "fake-model",
            LLMTokenUsage(),
        )


class FakeSemanticResolver:
    async def resolve(self, snapshot):
        return EffectiveSemanticContext(
            payload={"database": snapshot.database.name, "tables": []},
            sources=[
                QuerySemanticSource(
                    table_name="rs_gzff",
                    source="schema_only",
                )
            ],
            field_sources={
                ("rs_gzff", "ygbh"): "schema_only",
                ("rs_gzff", "gz"): "schema_only",
            },
            field_meanings={
                ("rs_gzff", "ygbh"): "员工编号",
                ("rs_gzff", "gz"): "工资金额",
            },
        )


class FakeReadAdapter:
    def execute_select(self, sql, max_rows, parameters=()):
        if "COUNT(*)" in sql:
            return DatabaseSelectResult(
                columns=["matched_row_count"],
                rows=[{"matched_row_count": 1}],
                truncated=False,
            )
        return DatabaseSelectResult(
            columns=["ygbh", "gz"],
            rows=[{"ygbh": "E00001' OR 1=1", "gz": "10000.00"}],
            truncated=False,
        )


class FakeWriteAdapter:
    def __init__(self) -> None:
        self.requests = []

    def execute_write_transaction(self, request):
        self.requests.append(request)
        return DatabaseWriteResult(
            affected_row_count=1,
            before_rows=[{"ygbh": "E00001' OR 1=1", "gz": "10000.00"}],
            after_rows=[{"ygbh": "E00001' OR 1=1", "gz": "12000.00"}],
            verification_passed=True,
        )


class LookupPlanningAgent:
    def __init__(self) -> None:
        self.planning_contexts: list[dict[str, object] | None] = []

    async def plan(
        self,
        snapshot,
        message,
        semantic_payload,
        conversation_context=None,
        planning_context=None,
    ):
        self.planning_contexts.append(planning_context)
        return (
            DatabaseActionDraft(
                summary="将吴凯的岗位改为研发工程师",
                action_type="UPDATE",
                table_name="org_employee",
                assignments=[
                    ActionAssignment(
                        column_name="position_id",
                        value=ActionLookupReference(lookup_id="target_position"),
                    )
                ],
                conditions=[
                    ActionCondition(
                        column_name="employee_no",
                        operator="=",
                        value="E00007",
                    )
                ],
                value_lookups=[
                    ActionValueLookup(
                        lookup_id="target_position",
                        purpose="查询研发工程师对应的岗位ID",
                        target_kind="assignment",
                        target_column_name="position_id",
                        source_table="hr_position",
                        source_value_column="position_id",
                        conditions=[
                            ActionLookupCondition(
                                column_name="position_name",
                                operator="=",
                                value="研发工程师",
                            )
                        ],
                    )
                ],
                field_mappings=[
                    QueryFieldMapping(
                        user_term="吴凯",
                        table_name="org_employee",
                        column_name="employee_no",
                        semantic_meaning="员工工号",
                        source="schema_only",
                    ),
                    QueryFieldMapping(
                        user_term="研发工程师",
                        table_name="hr_position",
                        column_name="position_name",
                        semantic_meaning="岗位名称",
                        source="schema_only",
                    ),
                ],
                expected_effect="只修改吴凯的岗位外键",
            ),
            "fake",
            "fake-model",
            LLMTokenUsage(total_tokens=10),
        )


class LookupSemanticResolver:
    async def resolve(self, snapshot):
        meanings = {
            ("org_employee", "employee_id"): "员工主键",
            ("org_employee", "employee_no"): "员工工号",
            ("org_employee", "position_id"): "岗位ID",
            ("hr_position", "position_id"): "岗位主键",
            ("hr_position", "position_name"): "岗位名称",
        }
        return EffectiveSemanticContext(
            payload={"database": snapshot.database.name, "tables": []},
            sources=[
                QuerySemanticSource(table_name=table, source="schema_only")
                for table in ("org_employee", "hr_position")
            ],
            field_sources={key: "schema_only" for key in meanings},
            field_meanings=meanings,
        )


class LookupReadAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute_select(self, sql, max_rows, parameters=()):
        self.calls.append((sql, parameters))
        if "FROM `hr_position`" in sql:
            return DatabaseSelectResult(
                columns=["position_id", "position_name"],
                rows=[{"position_id": 7, "position_name": "研发工程师"}],
                truncated=False,
            )
        if "COUNT(*)" in sql:
            return DatabaseSelectResult(
                columns=["matched_row_count"],
                rows=[{"matched_row_count": 1}],
                truncated=False,
            )
        return DatabaseSelectResult(
            columns=["employee_id", "employee_no", "position_id"],
            rows=[{"employee_id": 7, "employee_no": "E00007", "position_id": 2}],
            truncated=False,
        )


class AmbiguousLookupReadAdapter(LookupReadAdapter):
    def execute_select(self, sql, max_rows, parameters=()):
        self.calls.append((sql, parameters))
        if "FROM `hr_position`" in sql:
            return DatabaseSelectResult(
                columns=["position_id", "position_name"],
                rows=[
                    {"position_id": 7, "position_name": "研发工程师"},
                    {"position_id": 17, "position_name": "研发工程师"},
                ],
                truncated=False,
            )
        return super().execute_select(sql, max_rows, parameters)


def make_employee_position_snapshot():
    base = make_snapshot()
    return base.model_copy(
        update={
            "tables": [
                TableSchema(
                    name="org_employee",
                    table_type="BASE TABLE",
                    primary_key=["employee_id"],
                    columns=[
                        ColumnSchema(
                            name="employee_id",
                            ordinal_position=1,
                            data_type="bigint",
                            column_type="bigint unsigned",
                            nullable=False,
                            is_primary_key=True,
                        ),
                        ColumnSchema(
                            name="employee_no",
                            ordinal_position=2,
                            data_type="varchar",
                            column_type="varchar(20)",
                            nullable=False,
                            is_unique=True,
                        ),
                        ColumnSchema(
                            name="position_id",
                            ordinal_position=3,
                            data_type="bigint",
                            column_type="bigint unsigned",
                            nullable=False,
                        ),
                    ],
                ),
                TableSchema(
                    name="hr_position",
                    table_type="BASE TABLE",
                    primary_key=["position_id"],
                    columns=[
                        ColumnSchema(
                            name="position_id",
                            ordinal_position=1,
                            data_type="bigint",
                            column_type="bigint unsigned",
                            nullable=False,
                            is_primary_key=True,
                        ),
                        ColumnSchema(
                            name="position_name",
                            ordinal_position=2,
                            data_type="varchar",
                            column_type="varchar(100)",
                            nullable=False,
                        ),
                    ],
                ),
            ],
            "declared_relationships": [
                DeclaredRelationship(
                    constraint_name="fk_employee_position",
                    source_table="org_employee",
                    source_columns=["position_id"],
                    target_table="hr_position",
                    target_columns=["position_id"],
                    on_update="NO ACTION",
                    on_delete="NO ACTION",
                )
            ],
            "scan_statistics": ScanStatistics(
                table_count=2,
                view_count=0,
                column_count=5,
                foreign_key_count=1,
                index_count=2,
            ),
        }
    )


def test_sql_builder_keeps_user_values_out_of_sql() -> None:
    draft = DatabaseActionDraft(
        summary="更新工资",
        action_type="UPDATE",
        table_name="rs_gzff",
        assignments=[ActionAssignment(column_name="gz", value=12000)],
        conditions=[
            ActionCondition(
                column_name="ygbh",
                operator="=",
                value="E00001' OR 1=1",
            )
        ],
        expected_effect="更新一行",
    )

    built = ActionSQLBuilder().build(draft, max_rows=100)

    assert built.statement == (
        "UPDATE `rs_gzff` SET `gz` = :set_0 WHERE `ygbh` = :where_0"
    )
    assert built.parameters == {
        "set_0": 12000,
        "where_0": "E00001' OR 1=1",
    }
    assert "OR 1=1" not in built.statement
    assert "E00001'' OR 1=1" in built.display_statement


def test_update_without_conditions_is_rejected() -> None:
    draft = DatabaseActionDraft(
        summary="错误的全表更新",
        action_type="UPDATE",
        table_name="rs_gzff",
        assignments=[ActionAssignment(column_name="gz", value=12000)],
        expected_effect="更新所有行",
    )

    with pytest.raises(UnsafeDatabaseActionError):
        ActionSQLBuilder().build(draft, max_rows=100)


def test_action_confirmation_compares_complete_preview_rows() -> None:
    expected = (
        {"employee_id": 7, "employee_no": "E00007", "position_id": 2},
    )

    assert SQLAlchemyDatabaseAdapter._same_target_rows(
        [
            {
                "employee_id": 7,
                "employee_no": "E00007",
                "position_id": 2,
            }
        ],
        expected,
        ("employee_id",),
    )
    assert not SQLAlchemyDatabaseAdapter._same_target_rows(
        [
            {
                "employee_id": 7,
                "employee_no": "E00007",
                "position_id": 3,
            }
        ],
        expected,
        ("employee_id",),
    )


@pytest.mark.asyncio
async def test_action_plan_requires_confirmation_then_executes(tmp_path) -> None:
    snapshot = make_snapshot()
    primary_column = snapshot.tables[0].columns[0].model_copy(update={"is_primary_key": True})
    snapshot = snapshot.model_copy(
        update={
            "tables": [
                snapshot.tables[0].model_copy(
                    update={
                        "primary_key": ["ygbh"],
                        "columns": [
                            primary_column,
                            snapshot.tables[0].columns[1],
                        ],
                    }
                )
            ]
        }
    )
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    sessions = FileQuerySessionRepository(tmp_path / "sessions")
    sessions.save(
        QuerySession(
            session_id="session_action",
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            title="数据库操作测试",
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
            updated_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
    )
    writer = FakeWriteAdapter()
    service = DatabaseActionService(
        FileDatabaseActionRepository(tmp_path / "actions"),
        sessions,
        snapshots,
        FakeSemanticResolver(),  # type: ignore[arg-type]
        FakePlanningAgent(),  # type: ignore[arg-type]
        FakeReadAdapter(),  # type: ignore[arg-type]
        writer,  # type: ignore[arg-type]
        max_affected_rows=100,
    )

    principal = UserPrincipal(
        username="operator",
        role="database_operator",
        authenticated=True,
        permissions=["database_action:execute"],
    )
    planned = await service.plan("session_action", "修改员工工资", principal)

    assert planned.status == "pending_confirmation"
    assert planned.preview.matched_row_count == 1
    assert writer.requests == []
    zero_scope_checks = service._safety_checks(snapshot, planned.draft, 0)
    assert (
        next(check for check in zero_scope_checks if check.code == "target_exists").passed is False
    )

    executed = await service.confirm(planned.action_id, principal)

    assert executed.status == "executed"
    assert executed.execution is not None
    assert executed.execution.verification_passed is True
    assert executed.requested_by == "operator"
    assert executed.confirmed_by == "operator"
    assert writer.requests[0].parameters == {
        "set_0": 12000,
        "where_0": "E00001' OR 1=1",
    }


@pytest.mark.asyncio
async def test_action_plan_resolves_foreign_key_business_value_before_preview(
    tmp_path,
) -> None:
    snapshot = make_employee_position_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    sessions = FileQuerySessionRepository(tmp_path / "sessions")
    sessions.save(
        QuerySession(
            session_id="session_lookup",
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            title="岗位修改",
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
            updated_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
    )
    reader = LookupReadAdapter()
    service = DatabaseActionService(
        FileDatabaseActionRepository(tmp_path / "actions"),
        sessions,
        snapshots,
        LookupSemanticResolver(),  # type: ignore[arg-type]
        LookupPlanningAgent(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        FakeWriteAdapter(),  # type: ignore[arg-type]
        max_planning_rounds=3,
    )
    principal = UserPrincipal(
        username="operator",
        role="database_operator",
        authenticated=True,
        permissions=["database_action:execute"],
    )

    planned = await service.plan(
        "session_lookup",
        "吴凯降职为研发工程师",
        principal,
    )

    assert planned.status == "pending_confirmation"
    assert planned.draft.assignments[0].value == 7
    assert planned.lookup_resolutions[0].status == "resolved"
    assert planned.lookup_resolutions[0].rows == [{"position_id": 7, "position_name": "研发工程师"}]
    assert planned.display_sql == (
        "UPDATE `org_employee` SET `position_id` = 7 WHERE `employee_no` = 'E00007'"
    )
    assert planned.semantic_sources[0].table_name in {
        "org_employee",
        "hr_position",
    }
    assert any("FROM `hr_position`" in sql for sql, _ in reader.calls)


@pytest.mark.asyncio
async def test_action_plan_blocks_ambiguous_cross_table_value_after_three_rounds(
    tmp_path,
) -> None:
    snapshot = make_employee_position_snapshot()
    snapshots = FileDatabaseSnapshotRepository(tmp_path / "snapshots")
    snapshots.save(snapshot)
    sessions = FileQuerySessionRepository(tmp_path / "sessions")
    sessions.save(
        QuerySession(
            session_id="session_ambiguous_lookup",
            snapshot_id=snapshot.snapshot_id,
            database_name=snapshot.database.name,
            title="岗位修改",
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
            updated_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
    )
    planner = LookupPlanningAgent()
    service = DatabaseActionService(
        FileDatabaseActionRepository(tmp_path / "actions"),
        sessions,
        snapshots,
        LookupSemanticResolver(),  # type: ignore[arg-type]
        planner,  # type: ignore[arg-type]
        AmbiguousLookupReadAdapter(),  # type: ignore[arg-type]
        FakeWriteAdapter(),  # type: ignore[arg-type]
        max_planning_rounds=3,
    )
    principal = UserPrincipal(
        username="operator",
        role="database_operator",
        authenticated=True,
        permissions=["database_action:execute"],
    )

    planned = await service.plan(
        "session_ambiguous_lookup",
        "吴凯降职为研发工程师",
        principal,
    )

    assert planned.status == "blocked"
    assert len(planner.planning_contexts) == 3
    assert len(planned.planning_steps) == 3
    assert planned.lookup_resolutions[0].status == "ambiguous"
    assert planned.parameterized_sql.startswith("-- 未生成写入SQL")
    assert all(not check.passed for check in planned.safety_checks)
