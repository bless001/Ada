from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from planning_agent_core.agent_platform.agents.base.contracts import (
    AgentNextAction,
    AgentRunStatus,
)
from planning_agent_core.agent_platform.orchestration.contracts import (
    AgentExecutionRequest,
)
from planning_agent_core.agent_platform.orchestration.flow import (
    AgentFlowResult,
    AgentFlowStatus,
)
from planning_agent_core.agent_platform.orchestration.routing import AgentRouteDecision
from planning_agent_core.domain.enums import ApprovalDecision


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentFlowPersistenceError(RuntimeError):
    pass


class AgentFlowNotFoundError(AgentFlowPersistenceError):
    pass


class AgentFlowVersionConflictError(AgentFlowPersistenceError):
    pass


class AgentFlowApproval(BaseModel):
    decision: ApprovalDecision
    approval_reference: str = Field(min_length=1)
    actor: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=_utc_now)


class AgentFlowStepRecord(BaseModel):
    sequence: int = Field(ge=1)
    agent_type: str
    execution_id: UUID
    result_id: UUID
    status: AgentRunStatus
    next_action: AgentNextAction
    request_payload: dict[str, Any]
    result_payload: dict[str, Any]
    route: AgentRouteDecision


class PersistedAgentFlow(BaseModel):
    flow_id: UUID
    workflow_id: str
    project_id: str
    task_id: str | None = None
    status: AgentFlowStatus
    version: int = Field(ge=1)
    step_count: int = Field(default=0, ge=0)
    steps: list[AgentFlowStepRecord] = Field(default_factory=list)
    pending_route: AgentRouteDecision | None = None
    pending_execution_payload: dict[str, Any] | None = None
    reason: str
    correlation_id: str
    resume_count: int = Field(default=0, ge=0)
    approvals: list[AgentFlowApproval] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


@runtime_checkable
class AgentFlowStore(Protocol):
    async def reserve(
        self,
        execution: AgentExecutionRequest,
    ) -> PersistedAgentFlow: ...

    async def begin_resume(
        self,
        *,
        flow_id: UUID,
        execution: AgentExecutionRequest,
        expected_version: int,
        approval: AgentFlowApproval | None = None,
    ) -> PersistedAgentFlow: ...

    async def complete_run(
        self,
        *,
        flow_id: UUID,
        result: AgentFlowResult,
        expected_version: int,
    ) -> PersistedAgentFlow: ...

    async def close(
        self,
        *,
        flow_id: UUID,
        status: AgentFlowStatus,
        reason: str,
        expected_version: int,
        approval: AgentFlowApproval,
    ) -> PersistedAgentFlow: ...

    async def get(self, flow_id: UUID) -> PersistedAgentFlow | None: ...


class InMemoryAgentFlowStore:
    def __init__(self) -> None:
        self.flows: dict[UUID, PersistedAgentFlow] = {}
        self.workflow_index: dict[tuple[str, str], UUID] = {}

    async def reserve(
        self,
        execution: AgentExecutionRequest,
    ) -> PersistedAgentFlow:
        identity = (
            execution.request.project_id,
            execution.workflow_id,
        )
        if identity in self.workflow_index:
            raise AgentFlowVersionConflictError(
                f"Agent flow already exists for workflow: {execution.workflow_id}"
            )
        snapshot = reserve_flow_snapshot(execution)
        self.flows[snapshot.flow_id] = snapshot
        self.workflow_index[identity] = snapshot.flow_id
        return snapshot.model_copy(deep=True)

    async def begin_resume(
        self,
        *,
        flow_id: UUID,
        execution: AgentExecutionRequest,
        expected_version: int,
        approval: AgentFlowApproval | None = None,
    ) -> PersistedAgentFlow:
        current = self._require(flow_id)
        _check_version(current, expected_version)
        snapshot = begin_resume_snapshot(
            current,
            execution,
            approval=approval,
        )
        self.flows[flow_id] = snapshot
        return snapshot.model_copy(deep=True)

    async def complete_run(
        self,
        *,
        flow_id: UUID,
        result: AgentFlowResult,
        expected_version: int,
    ) -> PersistedAgentFlow:
        current = self._require(flow_id)
        _check_version(current, expected_version)
        snapshot = complete_run_snapshot(current, result)
        self.flows[flow_id] = snapshot
        return snapshot.model_copy(deep=True)

    async def close(
        self,
        *,
        flow_id: UUID,
        status: AgentFlowStatus,
        reason: str,
        expected_version: int,
        approval: AgentFlowApproval,
    ) -> PersistedAgentFlow:
        current = self._require(flow_id)
        _check_version(current, expected_version)
        snapshot = close_flow_snapshot(
            current,
            status=status,
            reason=reason,
            approval=approval,
        )
        self.flows[flow_id] = snapshot
        return snapshot.model_copy(deep=True)

    async def get(self, flow_id: UUID) -> PersistedAgentFlow | None:
        snapshot = self.flows.get(flow_id)
        return snapshot.model_copy(deep=True) if snapshot is not None else None

    def _require(self, flow_id: UUID) -> PersistedAgentFlow:
        snapshot = self.flows.get(flow_id)
        if snapshot is None:
            raise AgentFlowNotFoundError(f"Agent flow not found: {flow_id}")
        return snapshot


def reserve_flow_snapshot(
    execution: AgentExecutionRequest,
    *,
    flow_id: UUID | None = None,
) -> PersistedAgentFlow:
    return PersistedAgentFlow(
        flow_id=flow_id or uuid4(),
        workflow_id=execution.workflow_id,
        project_id=execution.request.project_id,
        task_id=execution.request.task_id,
        status=AgentFlowStatus.RUNNING,
        version=1,
        pending_execution_payload=execution.model_dump(mode="json"),
        reason="Flow execution reserved.",
        correlation_id=execution.correlation_id,
    )


def begin_resume_snapshot(
    current: PersistedAgentFlow,
    execution: AgentExecutionRequest,
    *,
    approval: AgentFlowApproval | None = None,
) -> PersistedAgentFlow:
    resumable = {
        AgentFlowStatus.WAITING_FOR_APPROVAL,
        AgentFlowStatus.WAITING_FOR_CLARIFICATION,
        AgentFlowStatus.TRANSITION_PENDING,
        AgentFlowStatus.ESCALATED,
        AgentFlowStatus.MAX_STEPS_EXCEEDED,
    }
    if current.status not in resumable:
        raise AgentFlowPersistenceError(
            f"Agent flow cannot resume from status: {current.status.value}"
        )
    if current.status == AgentFlowStatus.WAITING_FOR_APPROVAL:
        if approval is None or approval.decision != ApprovalDecision.APPROVED:
            raise AgentFlowPersistenceError(
                "An approved decision is required to claim an approval-gated flow"
            )
    elif approval is not None:
        raise AgentFlowPersistenceError(
            "Approval evidence is only valid for a flow waiting for approval"
        )
    _validate_execution_identity(current, execution)
    approvals = [*current.approvals]
    if approval is not None:
        approvals.append(approval)
    return current.model_copy(
        deep=True,
        update={
            "task_id": execution.request.task_id or current.task_id,
            "status": AgentFlowStatus.RUNNING,
            "version": current.version + 1,
            "pending_route": None,
            "pending_execution_payload": execution.model_dump(mode="json"),
            "reason": "Flow resume reserved.",
            "resume_count": current.resume_count + 1,
            "approvals": approvals,
            "updated_at": _utc_now(),
        },
    )


def complete_run_snapshot(
    current: PersistedAgentFlow,
    result: AgentFlowResult,
) -> PersistedAgentFlow:
    if current.status != AgentFlowStatus.RUNNING:
        raise AgentFlowPersistenceError("Only a running flow can complete an execution")
    if result.workflow_id != current.workflow_id:
        raise AgentFlowPersistenceError("Completed flow must preserve workflow_id")
    if not result.steps:
        raise AgentFlowPersistenceError("Cannot complete an agent flow without steps")
    project_id = result.steps[0].execution.request.project_id
    if project_id != current.project_id:
        raise AgentFlowPersistenceError("Completed flow must preserve project_id")

    new_steps = _step_records(result, sequence_offset=current.step_count)
    return current.model_copy(
        deep=True,
        update={
            "task_id": _latest_task_id(result) or current.task_id,
            "status": result.status,
            "version": current.version + 1,
            "step_count": current.step_count + len(new_steps),
            "steps": [*current.steps, *new_steps],
            "pending_route": result.pending_route,
            "pending_execution_payload": None,
            "reason": result.reason,
            "updated_at": _utc_now(),
        },
    )


def close_flow_snapshot(
    current: PersistedAgentFlow,
    *,
    status: AgentFlowStatus,
    reason: str,
    approval: AgentFlowApproval,
) -> PersistedAgentFlow:
    if current.status != AgentFlowStatus.WAITING_FOR_APPROVAL:
        raise AgentFlowPersistenceError(
            "Only a flow waiting for approval can be closed by approval decision"
        )
    if status not in {
        AgentFlowStatus.CHANGES_REQUESTED,
        AgentFlowStatus.CANCELLED,
    }:
        raise AgentFlowPersistenceError(f"Unsupported approval close status: {status}")
    expected_status = {
        ApprovalDecision.CHANGES_REQUESTED: AgentFlowStatus.CHANGES_REQUESTED,
        ApprovalDecision.CANCELLED: AgentFlowStatus.CANCELLED,
    }.get(approval.decision)
    if expected_status != status:
        raise AgentFlowPersistenceError(
            "Approval decision does not match the requested close status"
        )
    return current.model_copy(
        deep=True,
        update={
            "status": status,
            "version": current.version + 1,
            "pending_route": None,
            "pending_execution_payload": None,
            "reason": reason,
            "resume_count": current.resume_count + 1,
            "approvals": [*current.approvals, approval],
            "updated_at": _utc_now(),
        },
    )


def _step_records(
    result: AgentFlowResult,
    *,
    sequence_offset: int = 0,
) -> list[AgentFlowStepRecord]:
    return [
        AgentFlowStepRecord(
            sequence=sequence_offset + index,
            agent_type=step.execution.agent_type,
            execution_id=step.execution.request.execution_id,
            result_id=step.outcome.persisted.result_id,
            status=step.outcome.result.status,
            next_action=step.outcome.result.next_action,
            request_payload=step.execution.model_dump(mode="json"),
            result_payload=step.outcome.result.model_dump(mode="json"),
            route=step.outcome.route,
        )
        for index, step in enumerate(result.steps, start=1)
    ]


def _latest_task_id(result: AgentFlowResult) -> str | None:
    for step in reversed(result.steps):
        if step.outcome.result.task_id:
            return step.outcome.result.task_id
        if step.execution.request.task_id:
            return step.execution.request.task_id
    return None


def _validate_execution_identity(
    current: PersistedAgentFlow,
    execution: AgentExecutionRequest,
) -> None:
    if execution.workflow_id != current.workflow_id:
        raise AgentFlowPersistenceError("Resumed flow must preserve workflow_id")
    if execution.request.project_id != current.project_id:
        raise AgentFlowPersistenceError("Resumed flow must preserve project_id")


def _check_version(current: PersistedAgentFlow, expected_version: int) -> None:
    if current.version != expected_version:
        raise AgentFlowVersionConflictError(
            f"Agent flow version conflict: expected {expected_version}, found {current.version}"
        )
