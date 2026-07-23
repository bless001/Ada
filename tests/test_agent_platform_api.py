from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from planning_agent_core.agent_platform.agents.base import (
    AgentNextAction,
    AgentResult,
    AgentRunStatus,
)
from planning_agent_core.agent_platform.agents.coding import CodingAgentRequest
from planning_agent_core.agent_platform.agents.planning import PlanningAgentRequest
from planning_agent_core.agent_platform.config import AgentConfig
from planning_agent_core.agent_platform.orchestration import (
    AgentFlowApproval,
    AgentFlowVersionConflictError,
    AgentOrchestrationResult,
    AgentRouteDecision,
    PersistedAgentResult,
)
from planning_agent_core.api.agents import (
    AgentExecutePayload,
    AgentFlowResumePayload,
    AgentFlowStartPayload,
    create_agent_platform_service_for_db,
    execute_agent,
    resume_agent_flow,
    start_agent_flow,
)
from planning_agent_core.domain.coding import CodingAttemptRequest, FileChange
from planning_agent_core.domain.enums import ApprovalDecision
from planning_agent_core.persistence.agent_flows import SqlAlchemyAgentFlowStore
from planning_agent_core.services.agent_transition_resolver import (
    ApplicationAgentTransitionResolver,
)


class FakeAgentPlatformService:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, request):
        self.calls.append(request)
        result = AgentResult(
            execution_id=request.request.execution_id,
            project_id=request.request.project_id,
            task_id=request.request.task_id,
            agent_type=request.agent_type,
            status=AgentRunStatus.SUCCEEDED,
            summary="Agent execution completed.",
            next_action=AgentNextAction.COMPLETE,
        )
        return AgentOrchestrationResult(
            result=result,
            persisted=PersistedAgentResult(result_id=uuid4(), result=result),
            route=AgentRouteDecision(
                next_agent_type=None,
                requires_approval=False,
                escalate=False,
                reason="Agent completed.",
            ),
        )


class FakeFlowService:
    def __init__(self) -> None:
        self.calls = []
        self.current = SimpleNamespace(
            workflow_id="stored-workflow",
            correlation_id="stored-correlation",
        )

    async def start_flow(self, execution, **kwargs):
        self.calls.append(("start", execution, kwargs))
        return "started"

    async def get_flow(self, flow_id):
        self.calls.append(("get", flow_id))
        return self.current

    async def resume_flow(self, **kwargs):
        self.calls.append(("resume", kwargs))
        return "resumed"


def test_agent_execute_payload_discriminates_coding_request():
    payload = AgentExecutePayload.model_validate(
        {
            "request": {
                "agent_type": "coding",
                "project_id": "demo",
                "task_id": "task.sample",
                "objective": "Change one file.",
                "approved": True,
                "coding_attempt": {
                    "task_key": "task.sample",
                    "repository_key": "sample-project",
                    "file_changes": [
                        {
                            "relative_path": "src/app.py",
                            "content": "VALUE = 'new'\n",
                        }
                    ],
                },
            }
        }
    )

    assert isinstance(payload.request, CodingAgentRequest)
    assert payload.request.coding_attempt is not None
    assert payload.request.coding_attempt.repository_key == "sample-project"


def test_database_platform_service_includes_production_transition_resolver():
    db = object()

    service = create_agent_platform_service_for_db(db)

    assert isinstance(
        service.transition_resolver,
        ApplicationAgentTransitionResolver,
    )
    assert service.transition_resolver.context_store.db is db
    assert isinstance(service.flow_store, SqlAlchemyAgentFlowStore)
    assert service.flow_store.db is db


@pytest.mark.asyncio
async def test_execute_agent_uses_default_config_and_service(monkeypatch):
    fake_service = FakeAgentPlatformService()
    monkeypatch.setattr(
        "planning_agent_core.api.agents.create_agent_platform_service_for_db",
        lambda db: fake_service,
    )
    payload = AgentExecutePayload(
        request=PlanningAgentRequest(
            project_id="demo",
            objective="Plan the modular agent platform.",
        ),
        workflow_id="workflow-api-test",
        correlation_id="correlation-api-test",
    )

    response = await execute_agent(payload, db=object())

    assert response.result.project_id == "demo"
    assert response.result.agent_type == "planning"
    assert response.persisted_result_id is not None
    assert fake_service.calls[0].workflow_id == "workflow-api-test"
    assert fake_service.calls[0].correlation_id == "correlation-api-test"
    assert fake_service.calls[0].config.agent_type == "planning"


@pytest.mark.asyncio
async def test_execute_agent_rejects_mismatched_config(monkeypatch):
    monkeypatch.setattr(
        "planning_agent_core.api.agents.create_agent_platform_service_for_db",
        lambda db: FakeAgentPlatformService(),
    )
    payload = AgentExecutePayload(
        request=CodingAgentRequest(
            project_id="demo",
            task_id="task.sample",
            objective="Change one file.",
            approved=True,
            coding_attempt=CodingAttemptRequest(
                task_key="task.sample",
                repository_key="sample-project",
                file_changes=[
                    FileChange(relative_path="src/app.py", content="VALUE = 'new'\n")
                ],
            ),
        ),
        config=AgentConfig(agent_type="planning", checkpoint_namespace="planning"),
    )

    with pytest.raises(HTTPException) as exc:
        await execute_agent(payload, db=object())

    assert exc.value.status_code == 422
    assert "config.agent_type" in exc.value.detail


@pytest.mark.asyncio
async def test_start_agent_flow_builds_typed_execution_request(monkeypatch):
    fake_service = FakeFlowService()
    monkeypatch.setattr(
        "planning_agent_core.api.agents.create_agent_platform_service_for_db",
        lambda db: fake_service,
    )
    payload = AgentFlowStartPayload(
        request=PlanningAgentRequest(
            project_id="demo",
            objective="Create a durable plan.",
        ),
        workflow_id="workflow-flow-api",
        correlation_id="correlation-flow-api",
        max_steps=4,
    )

    response = await start_agent_flow(payload, db=object())

    assert response == "started"
    _, execution, kwargs = fake_service.calls[0]
    assert execution.workflow_id == "workflow-flow-api"
    assert execution.correlation_id == "correlation-flow-api"
    assert execution.agent_type == "planning"
    assert kwargs == {"max_steps": 4}


@pytest.mark.asyncio
async def test_resume_agent_flow_uses_stored_workflow_identity(monkeypatch):
    fake_service = FakeFlowService()
    monkeypatch.setattr(
        "planning_agent_core.api.agents.create_agent_platform_service_for_db",
        lambda db: fake_service,
    )
    flow_id = uuid4()
    payload = AgentFlowResumePayload(
        expected_version=2,
        request=PlanningAgentRequest(
            project_id="demo",
            objective="Resume after approval.",
        ),
        correlation_id="resume-correlation",
        approval=AgentFlowApproval(
            decision=ApprovalDecision.APPROVED,
            approval_reference="approval-api-1",
        ),
        max_steps=3,
    )

    response = await resume_agent_flow(flow_id, payload, db=object())

    assert response == "resumed"
    _, resume_kwargs = fake_service.calls[-1]
    assert resume_kwargs["flow_id"] == flow_id
    assert resume_kwargs["expected_version"] == 2
    assert resume_kwargs["request"].workflow_id == "stored-workflow"
    assert resume_kwargs["request"].correlation_id == "resume-correlation"
    assert resume_kwargs["approval"].approval_reference == "approval-api-1"
    assert resume_kwargs["max_steps"] == 3


@pytest.mark.asyncio
async def test_start_agent_flow_maps_version_conflict_to_http_409(monkeypatch):
    class ConflictingFlowService:
        async def start_flow(self, execution, **kwargs):
            del execution, kwargs
            raise AgentFlowVersionConflictError("workflow already exists")

    monkeypatch.setattr(
        "planning_agent_core.api.agents.create_agent_platform_service_for_db",
        lambda db: ConflictingFlowService(),
    )
    payload = AgentFlowStartPayload(
        request=PlanningAgentRequest(
            project_id="demo",
            objective="Create a durable plan.",
        )
    )

    with pytest.raises(HTTPException) as exc:
        await start_agent_flow(payload, db=object())

    assert exc.value.status_code == 409
    assert exc.value.detail == "workflow already exists"


@pytest.mark.asyncio
async def test_event_orchestrate_endpoint_uses_agent_platform_service(monkeypatch):
    from planning_agent_core.api.events import orchestrate_event

    captured = {}
    fake_service = object()

    class FakeProjectEventOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def handle_persisted_event(self, event_id: str):
            captured["event_id"] = event_id
            return SimpleNamespace(as_dict=lambda: {"event_id": event_id, "ok": True})

    monkeypatch.setattr(
        "planning_agent_core.api.events.create_agent_platform_service_for_db",
        lambda db: fake_service,
    )
    monkeypatch.setattr(
        "planning_agent_core.api.events.SqlAlchemyEventInbox",
        lambda db: "inbox",
    )
    monkeypatch.setattr(
        "planning_agent_core.api.events.SqlAlchemyAgentExecutionRecorder",
        lambda db: "recorder",
    )
    monkeypatch.setattr(
        "planning_agent_core.api.events.ProjectEventOrchestrator",
        FakeProjectEventOrchestrator,
    )

    response = await orchestrate_event("event-1", db=object())

    assert response == {"event_id": "event-1", "ok": True}
    assert captured["event_inbox"] == "inbox"
    assert captured["execution_recorder"] == "recorder"
    assert captured["agent_platform_service"] is fake_service
    assert "planning_runner" not in captured
