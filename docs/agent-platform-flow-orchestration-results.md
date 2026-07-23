# Agent Platform Flow Orchestration Results

## Summary

The platform now supports bounded multi-agent execution on top of the existing one-agent
`run_once` path. A flow can advance from planning to coding to verification, route verification
rework back to coding, retry the current agent, and stop safely at approval, clarification,
escalation, missing transition input, or a configured step limit.

## Implemented

- Added typed `AgentFlowStep`, `AgentFlowResult`, `AgentFlowStatus`, and
  `AgentTransitionRequestResolver` contracts.
- Added `AgentFlowOrchestrator`, which delegates each agent run to `AgentOrchestrator` and never
  creates agent-specific requests itself.
- Added `InMemoryTransitionRequestResolver` for deterministic tests and explicitly assembled local
  flows.
- Added `AgentPlatformService.execute_flow` as the application-facing multi-step entry point.
- Preserved `AgentPlatformService.execute` and `AgentOrchestrator.run_once` for one-agent and
  compatibility callers.
- Added the original `next_action` to `AgentRouteDecision` so flow consumers do not need to infer
  clarification, completion, or retry semantics from loosely related fields.
- Corrected retry routing so `retry` targets the current agent.
- Added validation that execution, request, and configuration agent types match.
- Added handoff validation that preserves workflow and project identity across agents.

## Transition Boundary

Agents continue to return typed results and never call each other. The flow orchestrator determines
whether execution may continue, but an injected transition resolver builds the next specialized
request from persisted artifacts and prior results. This keeps planning, coding, and verification
payload knowledge in the application composition layer.

If a resolver is absent or cannot yet provide the request, the flow returns `transition_pending`
with the pending route. Approval and clarification produce their own waiting statuses. The caller
can resume by starting a new flow with the approved or clarified typed request and the same
`workflow_id`.

Database-backed platform construction now supplies `ApplicationAgentTransitionResolver` by
default. Its implementation and persisted context contract are recorded in
`docs/agent-platform-transition-resolver-results.md`.

## Validation

Commands run:

```powershell
.venv/Scripts/python.exe -m ruff check planning_agent_core/planning_agent_core/agent_platform/orchestration planning_agent_core/planning_agent_core/services/agent_platform_service.py tests/test_agent_platform_flow.py
.venv/Scripts/python.exe -m pytest -q tests/test_agent_platform_flow.py tests/test_agent_platform.py tests/test_agent_platform_api.py tests/test_import_smoke.py
.venv/Scripts/python.exe -m pytest -q
```

Results:

- Ruff: passed.
- Focused platform and flow tests: 28 passed.
- Full test suite: 143 passed, 11 skipped, 4 existing warnings.
