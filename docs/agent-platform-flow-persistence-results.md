# Agent Platform Flow Persistence Results

## Summary

Multi-agent flows now have a durable aggregate around the existing per-agent checkpoints and
results. The aggregate is reserved before agent execution, records append-only step and approval
history, uses optimistic versions for resume claims, and preserves pending typed input when a
process fails after reservation.

## Implemented

- Added `PersistedAgentFlow`, `AgentFlowStepRecord`, and `AgentFlowApproval` contracts.
- Added the `AgentFlowStore` protocol and deterministic `InMemoryAgentFlowStore`.
- Added `SqlAlchemyAgentFlowStore` with row locking and expected-version validation.
- Added SQLAlchemy model `AgentPlatformFlowRecord`.
- Added Alembic migration `0012_agent_platform_flows`.
- Added durable `start_flow`, `get_flow`, and `resume_flow` service methods.
- Added `POST /v1/agents/flows`, `GET /v1/agents/flows/{flow_id}`, and
  `POST /v1/agents/flows/{flow_id}/resume`.
- Preserved `POST /v1/agents/execute` and persistence-free `AgentFlowOrchestrator` behavior.

## Aggregate Lifecycle

New flow:

1. `reserve` inserts a running aggregate at version 1 with the pending execution payload.
2. The orchestrator runs the bounded agent flow.
3. `complete_run` appends every step and commits the resulting status at version 2.

Resumed flow:

1. The caller reads the current `flow_id` and `version`.
2. `begin_resume` locks the row, validates the expected version, records approval evidence when
   supplied, and commits a running claim at the next version.
3. The orchestrator runs the typed continuation request.
4. `complete_run` appends new steps after the existing sequence and increments the version again.

Approval decisions:

- `approved` requires a typed continuation request.
- `changes_requested` closes the current aggregate without agent execution.
- `cancelled` closes the current aggregate without agent execution.

Resume requests must preserve `workflow_id` and `project_id`. When a pending route identifies the
next agent, the request must target that agent. A stale expected version returns a conflict instead
of running duplicate work.

## Storage

`agent_platform_flows.flow_json` contains the complete aggregate:

- Stable flow, workflow, project, task, and correlation identity.
- Current status and optimistic version.
- Append-only raw request/result audit payloads and typed route records.
- Pending execution payload while work is reserved.
- Approval references, actor, reason, metadata, and timestamp.
- Resume count and timestamps.

Relational columns index operational queries by project/status, current execution, pending action,
pending agent, approval requirement, and last approval decision. A unique
`(project_key, workflow_id)` constraint rejects duplicate aggregate creation.

The raw JSON payload is persistence and recovery data, not an untyped cross-agent communication
contract. Agents continue to receive typed Pydantic requests through the orchestrator. Production
retention and redaction policies must cover request metadata and artifact payloads stored here.

## Failure Semantics

Reservation commits before agent execution. If execution raises, the aggregate remains `running`
with the pending execution payload and unchanged step history. This prevents loss of execution
identity and supports diagnosis. Automatic recovery of interrupted running claims is intentionally
not enabled yet because it requires an explicit lease/timeout and idempotency policy to avoid
duplicating repository or external side effects.

## Compatibility

- Existing one-step callers continue using `AgentPlatformService.execute`.
- Existing non-durable flow callers can continue using `execute_flow` without a configured store.
- Database-backed API composition automatically injects `SqlAlchemyAgentFlowStore`.
- Existing agent-specific checkpoints and result records are unchanged.
- No agent calls another agent directly, and no aggregate persistence logic was added to the
  generic orchestrator.

## Validation

Coverage includes:

- Reserve-before-execute and pending-input persistence.
- Append-only step numbering across resume.
- Approval audit and close-without-execution behavior.
- Duplicate workflow and stale version rejection.
- Failure preservation.
- API request construction and HTTP `409` conflict mapping.
- Live PostgreSQL JSONB reload, indexed columns, row-version transitions, and Alembic head.

Commands run:

```powershell
.venv/Scripts/python.exe -m ruff check <changed Python files>
.venv/Scripts/python.exe -m pytest -q tests/test_agent_flow_persistence.py tests/test_agent_platform_api.py tests/test_agent_platform_flow.py
.venv/Scripts/python.exe -m pytest -q tests/test_agent_flow_postgres_integration.py
..\.venv\Scripts\python.exe -m alembic -c alembic.ini heads
.venv/Scripts/python.exe -m pytest -q
```

Results:

- Ruff: passed.
- Focused persistence, API, and flow tests: 23 passed.
- Live PostgreSQL flow-store test: 1 passed.
- Alembic head: `0012_agent_platform_flows`.
- Full suite with PostgreSQL integrations enabled: 173 passed, 2 skipped, 4 existing warnings.
