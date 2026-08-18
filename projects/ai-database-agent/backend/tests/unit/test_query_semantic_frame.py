from datetime import UTC, datetime

import pytest

from app.agents.database_query import DatabaseQueryAgent
from app.core.exceptions import LLMResponseValidationError
from app.models import (
    ColumnSchema,
    DatabaseMetadata,
    DatabaseSnapshot,
    DatabaseSource,
    DeclaredRelationship,
    QueryIntent,
    QueryPlan,
    ScanStatistics,
    TableSchema,
)


def column(name: str, position: int, data_type: str = "bigint") -> ColumnSchema:
    return ColumnSchema(
        name=name,
        ordinal_position=position,
        data_type=data_type,
        column_type=data_type,
        nullable=False,
    )


def commerce_snapshot() -> DatabaseSnapshot:
    tables = [
        TableSchema(
            name="crm_customer",
            table_type="BASE TABLE",
            primary_key=["customer_id"],
            columns=[
                column("customer_id", 1),
                column("customer_name", 2, "varchar"),
                column("created_at", 3, "datetime"),
            ],
        ),
        TableSchema(
            name="sale_order",
            table_type="BASE TABLE",
            primary_key=["sales_order_id"],
            columns=[
                column("sales_order_id", 1),
                column("customer_id", 2),
                column("order_date", 3, "date"),
            ],
        ),
        TableSchema(
            name="scm_supplier",
            table_type="BASE TABLE",
            primary_key=["supplier_id"],
            columns=[
                column("supplier_id", 1),
                column("supplier_name", 2, "varchar"),
                column("created_at", 3, "datetime"),
            ],
        ),
        TableSchema(
            name="scm_purchase_order",
            table_type="BASE TABLE",
            primary_key=["purchase_order_id"],
            columns=[
                column("purchase_order_id", 1),
                column("supplier_id", 2),
                column("order_date", 3, "date"),
            ],
        ),
    ]
    relationships = [
        DeclaredRelationship(
            constraint_name="fk_sale_customer",
            source_table="sale_order",
            source_columns=["customer_id"],
            target_table="crm_customer",
            target_columns=["customer_id"],
            on_update="RESTRICT",
            on_delete="RESTRICT",
        ),
        DeclaredRelationship(
            constraint_name="fk_purchase_supplier",
            source_table="scm_purchase_order",
            source_columns=["supplier_id"],
            target_table="scm_supplier",
            target_columns=["supplier_id"],
            on_update="RESTRICT",
            on_delete="RESTRICT",
        ),
    ]
    return DatabaseSnapshot(
        snapshot_id="snap_commerce",
        captured_at=datetime(2026, 7, 29, tzinfo=UTC),
        source=DatabaseSource(
            database_type="mysql",
            host="127.0.0.1",
            port=3307,
            database="legacy_enterprise",
        ),
        database=DatabaseMetadata(
            name="legacy_enterprise",
            server_version="8.4",
            current_user="ai_reader@%",
            character_set="utf8mb4",
            collation="utf8mb4_0900_ai_ci",
        ),
        tables=tables,
        declared_relationships=relationships,
        scan_statistics=ScanStatistics(
            table_count=4,
            view_count=0,
            column_count=12,
            foreign_key_count=2,
            index_count=4,
        ),
    )


def query_plan(
    *,
    tables: list[str],
    sql: str,
    semantic_frame: dict[str, object],
) -> QueryPlan:
    return QueryPlan(
        intent=QueryIntent(
            summary="测试查询",
            tables=tables,
            semantic_frame=semantic_frame,
        ),
        sql=sql,
        sql_purpose="测试语义帧",
    )


def validate(
    question: str,
    plan: QueryPlan,
    *,
    context: dict[str, object] | None = None,
) -> None:
    DatabaseQueryAgent._validate_semantic_frame(
        commerce_snapshot(),
        plan,
        question,
        {
            ("crm_customer", "created_at"): "创建时间",
            ("sale_order", "order_date"): "下单日期",
            ("scm_supplier", "created_at"): "创建时间",
            ("scm_purchase_order", "order_date"): "采购订单日期",
        },
        context,
    )


def test_original_customer_case_rejects_master_created_at() -> None:
    plan = query_plan(
        tables=["crm_customer"],
        sql=(
            "SELECT COUNT(DISTINCT `customer_id`) FROM `crm_customer` "
            "WHERE `created_at` >= '2026-06-01'"
        ),
        semantic_frame={
            "fact_table": "crm_customer",
            "metric_entity": "客户公司",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "crm_customer",
                "column_name": "customer_id",
            },
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": "crm_customer",
                "column_name": "created_at",
            },
        },
    )

    with pytest.raises(LLMResponseValidationError, match="审计时间"):
        validate("6月份有几家客户公司名称中含有四川", plan)


def test_original_customer_case_accepts_fact_date_and_distinct_customer() -> None:
    plan = query_plan(
        tables=["sale_order", "crm_customer"],
        sql=(
            "SELECT COUNT(DISTINCT c.`customer_id`) FROM `sale_order` so "
            "JOIN `crm_customer` c ON so.`customer_id` = c.`customer_id` "
            "WHERE so.`order_date` >= '2026-06-01' "
            "AND so.`order_date` < '2026-07-01' "
            "AND c.`customer_name` LIKE '%四川%'"
        ),
        semantic_frame={
            "fact_table": "sale_order",
            "metric_entity": "客户公司",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "crm_customer",
                "column_name": "customer_id",
            },
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": "sale_order",
                "column_name": "order_date",
            },
            "predicate_bindings": [
                {
                    "source_text": "名称中含有四川",
                    "field": {
                        "table_name": "crm_customer",
                        "column_name": "customer_name",
                    },
                    "predicate_type": "contains",
                }
            ],
        },
    )

    validate("6月份有几家客户公司名称中含有四川", plan)


def test_explicit_name_contains_cannot_be_rewritten_as_region_filter() -> None:
    plan = query_plan(
        tables=["sale_order", "crm_customer"],
        sql=(
            "SELECT COUNT(DISTINCT c.`customer_id`) FROM `sale_order` so "
            "JOIN `crm_customer` c ON so.`customer_id` = c.`customer_id` "
            "WHERE so.`order_date` >= '2026-06-01' "
            "AND c.`province` = '四川'"
        ),
        semantic_frame={
            "fact_table": "sale_order",
            "metric_entity": "客户公司",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "crm_customer",
                "column_name": "customer_id",
            },
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": "sale_order",
                "column_name": "order_date",
            },
            "predicate_bindings": [
                {
                    "source_text": "四川",
                    "field": {
                        "table_name": "crm_customer",
                        "column_name": "customer_name",
                    },
                    "predicate_type": "equals",
                }
            ],
        },
    )

    with pytest.raises(LLMResponseValidationError, match="名称字段"):
        validate("6月份有几家客户公司名称中含有四川", plan)


def test_entity_substitution_uses_purchase_fact_for_supplier_count() -> None:
    plan = query_plan(
        tables=["scm_purchase_order", "scm_supplier"],
        sql=(
            "SELECT COUNT(DISTINCT s.`supplier_id`) FROM `scm_purchase_order` po "
            "JOIN `scm_supplier` s ON po.`supplier_id` = s.`supplier_id` "
            "WHERE po.`order_date` >= '2026-06-01' "
            "AND po.`order_date` < '2026-07-01'"
        ),
        semantic_frame={
            "fact_table": "scm_purchase_order",
            "metric_entity": "供应商",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "scm_supplier",
                "column_name": "supplier_id",
            },
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": "scm_purchase_order",
                "column_name": "order_date",
            },
        },
    )

    validate("六月有多少家供应商发生采购", plan)


def test_paraphrase_still_requires_distinct_entity_count() -> None:
    plan = query_plan(
        tables=["sale_order", "crm_customer"],
        sql=(
            "SELECT COUNT(*) FROM `sale_order` so "
            "JOIN `crm_customer` c ON so.`customer_id` = c.`customer_id` "
            "WHERE so.`order_date` >= '2026-06-01'"
        ),
        semantic_frame={
            "fact_table": "sale_order",
            "metric_entity": "客户公司",
            "aggregation": "count",
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": "sale_order",
                "column_name": "order_date",
            },
        },
    )

    with pytest.raises(LLMResponseValidationError, match="count_distinct"):
        validate("今年6月共有几家客户下过单", plan)


def test_lexical_decoy_company_name_is_not_treated_as_time_scope() -> None:
    plan = query_plan(
        tables=["crm_customer"],
        sql=(
            "SELECT `customer_id`, `customer_name` FROM `crm_customer` "
            "WHERE `customer_name` LIKE '%六月科技%'"
        ),
        semantic_frame={
            "fact_table": "crm_customer",
            "metric_entity": "客户公司",
            "aggregation": "detail",
            "time_scope_kind": "none",
            "predicate_bindings": [
                {
                    "source_text": "名称包含六月科技",
                    "field": {
                        "table_name": "crm_customer",
                        "column_name": "customer_name",
                    },
                    "predicate_type": "contains",
                }
            ],
        },
    )

    validate("查找名称包含“六月科技”的客户", plan)


def test_semantic_bridge_inherits_time_scope_from_previous_goal() -> None:
    context = {
        "resolved_goal": {"filters": ["2026年6月"]},
        "active_intent": {"summary": "查看2026年6月的销售订单"},
    }
    plan = query_plan(
        tables=["sale_order", "crm_customer"],
        sql=(
            "SELECT COUNT(DISTINCT c.`customer_id`) FROM `sale_order` so "
            "JOIN `crm_customer` c ON so.`customer_id` = c.`customer_id` "
            "WHERE so.`order_date` >= '2026-06-01'"
        ),
        semantic_frame={
            "fact_table": "sale_order",
            "metric_entity": "客户公司",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "crm_customer",
                "column_name": "customer_id",
            },
            "time_scope_kind": "business_event",
            "time_field": {
                "table_name": "sale_order",
                "column_name": "order_date",
            },
        },
    )

    validate("其中有多少家客户", plan, context=context)


def test_inverse_lifecycle_question_allows_customer_created_at() -> None:
    plan = query_plan(
        tables=["crm_customer"],
        sql=(
            "SELECT COUNT(DISTINCT `customer_id`) FROM `crm_customer` "
            "WHERE `created_at` >= '2026-06-01' AND `created_at` < '2026-07-01'"
        ),
        semantic_frame={
            "fact_table": "crm_customer",
            "metric_entity": "新增客户",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "crm_customer",
                "column_name": "customer_id",
            },
            "time_scope_kind": "entity_lifecycle",
            "time_field": {
                "table_name": "crm_customer",
                "column_name": "created_at",
            },
        },
    )

    validate("6月份新增了几家客户", plan)


def test_boundary_without_time_can_query_customer_master_directly() -> None:
    plan = query_plan(
        tables=["crm_customer"],
        sql=(
            "SELECT COUNT(DISTINCT `customer_id`) FROM `crm_customer` "
            "WHERE `customer_name` LIKE '%四川%'"
        ),
        semantic_frame={
            "fact_table": "crm_customer",
            "metric_entity": "客户公司",
            "aggregation": "count_distinct",
            "distinct_key": {
                "table_name": "crm_customer",
                "column_name": "customer_id",
            },
            "time_scope_kind": "none",
            "predicate_bindings": [
                {
                    "source_text": "名称中含有四川",
                    "field": {
                        "table_name": "crm_customer",
                        "column_name": "customer_name",
                    },
                    "predicate_type": "contains",
                }
            ],
        },
    )

    validate("有几家客户公司名称中含有四川", plan)


def test_unrelated_aggregate_is_not_forced_into_entity_count_contract() -> None:
    plan = query_plan(
        tables=["sale_order"],
        sql="SELECT SUM(`sales_order_id`) FROM `sale_order`",
        semantic_frame={
            "fact_table": "sale_order",
            "metric_entity": "测试金额",
            "aggregation": "sum",
            "time_scope_kind": "none",
        },
    )

    validate("统计全部测试金额", plan)


def test_validation_candidates_become_deterministic_repair_constraint() -> None:
    constraint = DatabaseQueryAgent._required_frame_from_validation(
        "不能绑定主数据；Schema关系中的业务事件时间候选："
        "sale_order.order_date、sale_order.required_date"
    )

    assert constraint == {
        "fact_table": "sale_order",
        "time_scope_kind": "business_event",
        "time_field": {
            "table_name": "sale_order",
            "column_name": "order_date",
        },
        "source": "deterministic_schema_relationship_guard",
    }
