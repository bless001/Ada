from __future__ import annotations

from uuid import uuid4

import pytest

from planning_agent_core.agent_platform.agents.base import (
    AgentNextAction,
    AgentRequest,
    AgentResult,
    AgentRunStatus,
)
from planning_agent_core.agent_platform.agents.base.errors import AgentValidationError
from planning_agent_core.agent_platform.config import AgentConfig
from planning_agent_core.agent_platform.orchestration import (
    AgentExecutionRequest,
    AgentFlowApproval,
    AgentFlowPersistenceError,
    AgentFlowResult,
    AgentFlowStatus,
    AgentFlowStep,
    AgentFlowVersionConflictError,
    AgentOrchestrationResult,
    AgentRouteDecision,
    InMemoryAgentFlowStore,
    PersistedAgentResult,
)
from planning_agent_core.agent_platform.runtime import AgentDependencyContainer
from planning_agent_core.domain.enums import ApprovalDecision
from planning_agent_core.services.agent_platform_service import AgentPlatformService


class ScriptedStepOrchestrator:
    def __init__(
        self,
        outcomes: list[AgentOrchestrationResult | Exception],
    ) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[AgentExecutionRequest] = []

    async def run_once(
        self,
        execution: AgentExecutionRequest,
    ) -> AgentOrchestrationResult:
        self.calls.append(execution)
        if not self.outcomes:
            raise AssertionError("No scripted outcome remains")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _execution(
    agent_type: str = "planning",
    *,
    workflow_id: str = "durable-workflow",
    project_id: str = "demo",
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_id=workflow_id,
        agent_type=agent_type,
        request=AgentRequest(
            project_id=project_id,
            task_id="task-1",
            agent_type=agent_type,
            objective=f"Run {agent_type}.",
        ),
        config=AgentConfig(
            agent_type=agent_type,
            checkpoint_namespace=agent_type,
        ),
        correlation_id="durable-correlation",
    )


def _outcome(
    execution: AgentExecutionRequest,
    *,
    next_action: AgentNextAction,
    next_agent_type: str | None,
    requires_approval: bool = False,
) -> AgentOrchestrationResult:
    result = AgentResult(
        execution_id=execution.request.execution_id,
        project_id=execution.request.project_id,
        task_id=execution.request.task_id,
        agent_type=execution.agent_type,
        status=AgentRunStatus.SUCCEEDED,
        summary=f"{execution.agent_type} completed.",
        next_action=next_action,
    )
    return AgentOrchestrationResult(
        result=result,
        persisted=PersistedAgentResult(result_id=uuid4(), result=result),
        route=AgentRouteDecision(
            next_action=next_action,
            next_agent_type=next_agent_type,
            requires_approval=requires_approval,
            escalate=False,
            reason=f"Route after {execution.agent_type}.",
        ),
    )


def _flow_result(
    execution: AgentExecutionRequest,
    outcome: AgentOrchestrationResult,
    *,
    status: AgentFlowStatus,
) -> AgentFlowResult:
    return AgentFlowResult(
        workflow_id=execution.workflow_id,
        status=status,
        steps=[
            AgentFlowStep(
                sequence=1,
                execution=execution,
                outcome=outcome,
            )
        ],
        final_outcome=outcome,
        pending_route=outcome.route,
        reason=outcome.route.reason,
    )


def _approval(
    decision: ApprovalDecision = ApprovalDecision.APPROVED,
) -> AgentFlowApproval:
    return AgentFlowApproval(
        decision=decision,
        approval_reference="approval-1",
        actor="reviewer@example.test",
        reason="Reviewed durable flow.",
    )


@pytest.mark.asyncio
async def test_in_memory_store_reserves_before_appending_completed_step():
    store = InMemoryAgentFlowStore()
    execution = _execution()

    reserved = await store.reserve(execution)

    assert reserved.status == AgentFlowStatus.RUNNING
    assert reserved.version == 1
    assert reserved.step_count == 0
    assert reserved.pending_execution_payload["request"]["execution_id"] == str(
        execution.request.execution_id
    )

    outcome = _outcome(
        execution,
        next_action=AgentNextAction.REQUEST_APPROVAL,
        next_agent_type=None,
        requires_approval=True,
    )
    completed = await store.complete_run(
        flow_id=reserved.flow_id,
        result=_flow_result(
            execution,
            outcome,
            status=AgentFlowStatus.WAITING_FOR_APPROVAL,
        ),
        expected_version=reserved.version,
    )

    assert completed.status == AgentFlowStatus.WAITING_FOR_APPROVAL
    assert completed.version == 2
    assert completed.step_count == 1
    assert completed.pending_execution_payload is None
    assert completed.steps[0].request_payload["agent_type"] == "planning"
    assert completed.steps[0].result_payload["summary"] == "planning completed."


@pytest.mark.asyncio
async def test_in_memory_store_rejects_duplicate_workflow_and_stale_version():
    store = InMemoryAgentFlowStore()
    execution = _execution()
    reserved = await store.reserve(execution)

    with pytest.raises(
        AgentFlowVersionConflictError,
        match="already exists",
    ):
        await store.reserve(execution)

    with pytest.raises(
        AgentFlowVersionConflictError,
        match="expected 2, found 1",
    ):
        await store.begin_resume(
            flow_id=reserved.flow_id,
            execution=execution,
            expected_version=2,
        )

    with pytest.raises(
        AgentFlowPersistenceError,
        match="cannot resume from status",
    ):
        await store.begin_resume(
            flow_id=reserved.flow_id,
            execution=execution,
            expected_version=reserved.version,
        )


@pytest.mark.asyncio
async def test_service_persists_approval_resume_and_append_only_history():
    store = InMemoryAgentFlowStore()
    planning_execution = _execution("planning")
    coding_execution = _execution("coding")
    orchestrator = ScriptedStepOrchestrator(
        [
            _outcome(
                planning_execution,
                next_action=AgentNextAction.REQUEST_APPROVAL,
                next_agent_type=None,
                requires_approval=True,
            ),
            _outcome(
                coding_execution,
                next_action=AgentNextAction.COMPLETE,
                next_agent_type=None,
            ),
        ]
    )
    service = AgentPlatformService(
        dependencies=AgentDependencyContainer(),
        orchestrator=orchestrator,
        flow_store=store,
    )

    waiting = await service.start_flow(planning_execution)
    completed = await service.resume_flow(
        flow_id=waiting.flow_id,
        expected_version=waiting.version,
        request=coding_execution,
        approval=_approval(),
    )

    assert completed.status == AgentFlowStatus.COMPLETED
    assert completed.version == 4
    assert completed.resume_count == 1
    assert completed.step_count == 2
    assert [step.sequence for step in completed.steps] == [1, 2]
    assert [step.agent_type for step in completed.steps] == ["planning", "coding"]
    assert completed.approvals[0].decision == ApprovalDecision.APPROVED


@pytest.mark.asyncio
async def test_service_closes_rejected_approval_without_running_an_agent():
    store = InMemoryAgentFlowStore()
    execution = _execution()
    orchestrator = ScriptedStepOrchestrator(
        [
            _outcome(
                execution,
                next_action=AgentNextAction.REQUEST_APPROVAL,
                next_agent_type=None,
                requires_approval=True,
            )
        ]
    )
    service = AgentPlatformService(
        dependencies=AgentDependencyContainer(),
        orchestrator=orchestrator,
        flow_store=store,
    )

    waiting = await service.start_flow(execution)
    closed = await service.resume_flow(
        flow_id=waiting.flow_id,
        expected_version=waiting.version,
        approval=_approval(ApprovalDecision.CHANGES_REQUESTED),
    )

    assert closed.status == AgentFlowStatus.CHANGES_REQUESTED
    assert closed.version == 3
    assert closed.resume_count == 1
    assert len(orchestrator.calls) == 1


@pytest.mark.asyncio
async def test_service_requires_approval_and_typed_resume_request():
    store = InMemoryAgentFlowStore()
    execution = _execution()
    service = AgentPlatformService(
        dependencies=AgentDependencyContainer(),
        orchestrator=ScriptedStepOrchestrator(
            [
                _outcome(
                    execution,
                    next_action=AgentNextAction.REQUEST_APPROVAL,
                    next_agent_type=None,
                    requires_approval=True,
                )
            ]
        ),
        flow_store=store,
    )
    waiting = await service.start_flow(execution)

    with pytest.raises(AgentValidationError, match="Approval evidence"):
        await service.resume_flow(
            flow_id=waiting.flow_id,
            expected_version=waiting.version,
            request=_execution("coding"),
        )

    with pytest.raises(AgentValidationError, match="typed execution request"):
        await service.resume_flow(
            flow_id=waiting.flow_id,
            expected_version=waiting.version,
            approval=_approval(),
        )


@pytest.mark.asyncio
async def test_service_preserves_reserved_execution_when_agent_raises():
    store = InMemoryAgentFlowStore()
    execution = _execution()
    service = AgentPlatformService(
        dependencies=AgentDependencyContainer(),
        orchestrator=ScriptedStepOrchestrator([RuntimeError("tool failed")]),
        flow_store=store,
    )

    with pytest.raises(RuntimeError, match="tool failed"):
        await service.start_flow(execution)

    assert len(store.flows) == 1
    reserved = next(iter(store.flows.values()))
    assert reserved.status == AgentFlowStatus.RUNNING
    assert reserved.version == 1
    assert reserved.pending_execution_payload["request"]["execution_id"] == str(
        execution.request.execution_id
    )
