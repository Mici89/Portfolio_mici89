from collections.abc import AsyncIterator
from typing import Any

from app.core.exceptions import WorkflowCheckpointNotFoundError
from app.models.workflow import WorkflowKind, WorkflowStatus


def workflow_config(
    workflow_id: str,
    *,
    recursion_limit: int | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "configurable": {"thread_id": workflow_id},
    }
    if recursion_limit is not None:
        config["recursion_limit"] = recursion_limit
    return config


async def inspect_workflow(
    graph: Any,
    *,
    workflow_id: str,
    workflow_kind: WorkflowKind,
) -> WorkflowStatus:
    config = workflow_config(workflow_id)
    snapshot = await graph.aget_state(config)
    if not snapshot.values and not snapshot.next and not snapshot.tasks:
        raise WorkflowCheckpointNotFoundError(workflow_id)

    completed_nodes: list[str] = []
    async for historical in _history(graph, config):
        for task in historical.tasks:
            if (
                task.name != "__start__"
                and task.error is None
                and not task.interrupts
                and task.result is not None
                and task.name not in completed_nodes
            ):
                completed_nodes.append(task.name)
    completed_nodes.reverse()

    task_error = next(
        (task.error for task in snapshot.tasks if task.error),
        None,
    )
    if snapshot.interrupts:
        status = "interrupted"
    elif task_error:
        status = "failed"
    elif not snapshot.next:
        status = "completed"
    else:
        status = "running"

    values = snapshot.values if isinstance(snapshot.values, dict) else {}
    retry_count = max(
        int(values.get("attempt_number", 1)) - 1,
        int(values.get("evidence_round_count", 0)),
        int(values.get("planning_round", 1)) - 1,
        0,
    )
    interrupt_payload = (
        snapshot.interrupts[0].value if snapshot.interrupts else None
    )
    return WorkflowStatus(
        workflow_id=workflow_id,
        workflow_kind=workflow_kind,
        status=status,
        current_node=snapshot.next[0] if snapshot.next else None,
        completed_nodes=completed_nodes,
        retry_count=retry_count,
        can_resume=status == "failed",
        awaiting_input=status == "interrupted",
        interrupt_payload=interrupt_payload,
        error=str(task_error)[:2000] if task_error else None,
    )


async def _history(
    graph: Any,
    config: dict[str, Any],
) -> AsyncIterator[Any]:
    async for snapshot in graph.aget_state_history(config):
        yield snapshot
