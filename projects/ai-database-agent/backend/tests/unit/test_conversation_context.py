import pytest

from app.agents.database_query import DatabaseQueryAgent
from app.core.exceptions import LLMResponseValidationError
from app.models import (
    ConversationRoutingDecision,
    QueryIntent,
    QueryPlan,
    QueryResultAssessment,
)
from app.services.conversation_context import ConversationContextMerger


def active_intent(
    *,
    metric: str = "报销总额",
    time_filter: str = "2026年6月",
    table: str = "fin_expense_claim",
) -> QueryIntent:
    return QueryIntent(
        summary=f"查询{time_filter}{metric}",
        metrics=[metric],
        filters=[time_filter],
        tables=[table],
    )


def routing(
    *,
    mode: str,
    complete: bool,
    filters: list[str] | None = None,
    details: list[str] | None = None,
    omitted: list[str] | None = None,
) -> ConversationRoutingDecision:
    return ConversationRoutingDecision(
        kind="query",
        context_mode=mode,
        standalone_intent_complete=complete,
        confidence=0.95,
        reason="测试路由判断",
        added_filters=filters or [],
        detail_requests=details or [],
        omitted_references=omitted or [],
    )


def test_elliptical_department_follow_up_cannot_drop_previous_fact() -> None:
    resolution = ConversationContextMerger().resolve(
        routing(
            mode="switch",
            complete=False,
            filters=["部门=总经理办公室"],
            details=["报销明细"],
            omitted=["指标", "事实对象"],
        ),
        active_intent(),
    )

    assert resolution.mode == "refine"
    assert resolution.required_metrics == ["报销总额"]
    assert resolution.required_filters == ["2026年6月"]
    assert resolution.added_filters == ["部门=总经理办公室"]
    assert resolution.required_tables == ["fin_expense_claim"]
    assert resolution.detail_requests == ["报销明细"]


def test_equivalent_salary_follow_up_preserves_metric_and_time() -> None:
    resolution = ConversationContextMerger().resolve(
        routing(
            mode="refine",
            complete=False,
            filters=["部门=人力资源部"],
            details=["工资发放明细"],
            omitted=["指标"],
        ),
        active_intent(
            metric="工资总额",
            time_filter="本季度",
            table="hr_payroll",
        ),
    )

    assert resolution.required_metrics == ["工资总额"]
    assert resolution.required_filters == ["本季度"]
    assert resolution.added_filters == ["部门=人力资源部"]
    assert resolution.required_tables == ["hr_payroll"]


def test_complete_new_employee_subject_switches_topic() -> None:
    resolution = ConversationContextMerger().resolve(
        routing(mode="switch", complete=True),
        active_intent(),
    )

    assert resolution.mode == "switch"
    assert resolution.required_metrics == []
    assert resolution.required_filters == []
    assert resolution.required_tables == []


def test_without_active_intent_message_is_standalone() -> None:
    resolution = ConversationContextMerger().resolve(
        routing(mode="refine", complete=False, omitted=["指标"]),
        None,
    )

    assert resolution.mode == "standalone"
    assert resolution.required_metrics == []


def test_standalone_router_labels_are_not_promoted_to_schema_grounded_goal() -> None:
    decision = ConversationRoutingDecision(
        kind="query",
        context_mode="standalone",
        standalone_intent_complete=True,
        confidence=0.95,
        reason="测试Router自然语言增量",
        added_metrics=["COUNT(customer)"],
        added_filters=["time=6月", "region=四川"],
    )

    resolution = ConversationContextMerger().resolve(decision, None)

    assert resolution.added_metrics == ["COUNT(customer)"]
    assert resolution.added_filters == ["time=6月", "region=四川"]
    assert resolution.required_metrics == []
    assert resolution.required_filters == []


def test_answer_plan_that_drops_merged_goal_is_rejected_before_execution() -> None:
    plan = QueryPlan(
        intent=QueryIntent(
            summary="查询部门员工",
            metrics=["员工人数"],
            dimensions=["员工姓名"],
            filters=["部门=总经理办公室"],
            tables=["org_employee"],
        ),
        sql="SELECT COUNT(*) FROM `org_employee`",
        sql_purpose="查询员工人数",
    )
    context = {
        "resolved_goal": {
            "metrics": ["报销总额"],
            "dimensions": [],
            "filters": ["2026年6月", "部门=总经理办公室"],
            "detail_requests": ["报销明细"],
            "tables": ["fin_expense_claim"],
        }
    }

    with pytest.raises(LLMResponseValidationError, match="偏离合并后的对话目标"):
        DatabaseQueryAgent._validate_goal_alignment(plan, context)


def test_inconsistent_sufficient_assessment_is_normalized_to_replan() -> None:
    assessment = QueryResultAssessment(
        verdict="sufficient",
        confidence=0.8,
        reason="仍然缺少明细",
        issues=["缺少明细"],
        next_action="查询明细",
    )

    assert assessment.verdict == "replan"
    assert assessment.next_action == "查询明细"
