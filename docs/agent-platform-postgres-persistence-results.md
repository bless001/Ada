# Agent Platform PostgreSQL Persistence Results

## Summary

Added PostgreSQL-backed persistence for agent-platform checkpoints and result payloads. This keeps agent state and cross-agent outputs durable without coupling platform execution to the existing `agent_executions` metadata table or requiring a project UUID foreign key.

## Implemented

- `agent_platform_checkpoints` table for agent-scoped checkpoint state.
- `agent_platform_results` table for typed agent result payloads.
- Alembic migration `0011_agent_platform_persistence`.
- SQLAlchemy checkpoint store implementing the platform `CheckpointStore` protocol.
- SQLAlchemy result store implementing the platform `AgentResultStore` protocol.
- Common `AgentResult` now carries typed `project_id` and `task_id` fields for durable indexing.
- Planning, Coding, Verification, and orchestrator failure results populate `project_id` and `task_id`.
- `AgentOrchestrator` uses `dependencies.result_store` when no explicit result store is passed.
- Local contract tests for persistence model registration and dependency-injected result storage.
- Live Postgres integration coverage for checkpoint upsert/load and result persistence.

## Tables

`agent_platform_checkpoints` identity columns:

- `project_key`
- `workflow_id`
- `agent_type`
- `agent_instance_id`
- `execution_id`
- `thread_id`
- `checkpoint_id`

`agent_platform_results` indexing columns:

- `execution_id`
- `project_key`
- `task_key`
- `agent_type`
- `status`
- `next_action`

## Validation

Commands run:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_agent_platform.py tests/test_import_smoke.py
.venv/Scripts/python.exe -m ruff check planning_agent_core/planning_agent_core/agent_platform planning_agent_core/planning_agent_core/persistence/agent_platform.py planning_agent_core/planning_agent_core/services/agent_platform_service.py tests/test_agent_platform.py tests/test_phase3_postgres_integration.py
..\\.venv\\Scripts\\python.exe -m alembic -c alembic.ini heads
.venv/Scripts/python.exe -m pytest -q
```

Results:

- Platform/import/Postgres-gated focused tests: 15 passed, 9 skipped.
- Ruff: passed.
- Alembic heads: `0011_agent_platform_persistence (head)`.
- Full test suite: 128 passed, 11 skipped, 4 existing warnings.

Live Postgres validation remains behind `PHASE3_POSTGRES_DATABASE_URL`, consistent with the existing integration test strategy.
