# Agent Platform API Integration Results

## Summary

Added an application API entry point for executing registered platform agents through the orchestrator. The route preserves the existing FastAPI application style and uses typed request models at the HTTP boundary.

## Implemented

- Added `planning_agent_core/api/agents.py` with `POST /v1/agents/execute`.
- Registered the agents router in `planning_agent_core/main.py`.
- Added `AgentExecutePayload` with a discriminated union over `PlanningAgentRequest`, `CodingAgentRequest`, and `VerificationAgentRequest`.
- Added `AgentExecutionResponse` containing the persisted result ID, typed agent result, and route decision.
- The endpoint loads default agent configuration when no explicit config is supplied.
- The endpoint rejects mismatched `config.agent_type` and `request.agent_type`.
- The endpoint builds `AgentPlatformService` with request-scoped SQLAlchemy-backed checkpoint and result stores.
- Request/result models now use literal agent types for strong API discrimination.
- Agent validation wraps Pydantic validation failures in `AgentValidationError` to preserve the platform error contract.

## Endpoint

```http
POST /v1/agents/execute
```

Example planning payload:

```json
{
  "request": {
    "agent_type": "planning",
    "project_id": "demo",
    "objective": "Create an implementation plan for the agent platform"
  },
  "workflow_id": "workflow-demo",
  "correlation_id": "request-123"
}
```

Example response shape:

```json
{
  "persisted_result_id": "00000000-0000-0000-0000-000000000000",
  "result": {
    "execution_id": "00000000-0000-0000-0000-000000000000",
    "project_id": "demo",
    "agent_type": "planning",
    "status": "waiting",
    "summary": "Requirements were extracted, but no plan was provided or generated.",
    "next_action": "request_clarification"
  },
  "route": {
    "next_agent_type": null,
    "requires_approval": false,
    "escalate": true,
    "reason": "Agent requested explicit next action."
  }
}
```

## Validation

Commands run:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_agent_platform_api.py tests/test_agent_platform.py tests/test_import_smoke.py
.venv/Scripts/python.exe -m ruff check planning_agent_core/planning_agent_core/api/agents.py planning_agent_core/planning_agent_core/main.py planning_agent_core/planning_agent_core/agent_platform planning_agent_core/planning_agent_core/services/agent_platform_service.py planning_agent_core/planning_agent_core/persistence/agent_platform.py tests/test_agent_platform_api.py tests/test_agent_platform.py tests/test_import_smoke.py
.venv/Scripts/python.exe -m pytest -q
```

Results:

- API/platform/import tests: 18 passed.
- Ruff: passed.
- Full test suite: 131 passed, 11 skipped, 4 existing warnings.

## Remaining Follow-Up

- Add authenticated/authorized production usage once user-management or gateway policy exists outside this project.
- Wire OpenProject worker transitions to call `AgentPlatformService` instead of direct planning-only orchestration.
- Add production composition for external adapters such as Neo4j, Weaviate, OpenProject, repository filesystem, and command runner secrets.
