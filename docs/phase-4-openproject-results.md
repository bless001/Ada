# Phase 4 OpenProject Adapter Results

Baseline date: 2026-07-21

## Scope Completed

- Added `openproject_outbound_operations` as the durable idempotency table for OpenProject mutations.
- Added Alembic migration `0005_op_outbound_ops`.
- Added `OpenProjectOperationType`, `OpenProjectOperationStatus`, `OpenProjectOperationClaim`, and `OpenProjectOutboundStorePort`.
- Added `SqlAlchemyOpenProjectOutboundStore` with PostgreSQL `ON CONFLICT DO NOTHING` claim behavior.
- Expanded the async `OpenProjectClient` adapter with normalized work-package read, activity read, create/update work-package, and add-comment methods.
- Changed OpenProject token resolution so a mounted token file wins over placeholder environment values.
- Added comment idempotency markers in the form `<!-- ada:openproject-idempotency: ... -->`.
- Added OpenProject feedback classification for agent echo, human comments, approvals, requirement changes, plan feedback, rework, pause, resume, and cancellation.
- Updated planning resume decisions to ignore self-generated OpenProject echo webhooks.
- Updated the opt-in live PostgreSQL integration test to expect Alembic head `0005_op_outbound_ops`.

## Runtime Compatibility Notes

- Mutating OpenProject adapter methods require an `OpenProjectOutboundStorePort`; without it they raise instead of performing unsafe direct writes.
- Repeated outbound idempotency keys return the prior successful response and do not issue another OpenProject HTTP request.
- Failed or pending outbound operation records are not automatically retried in this slice; retry policy for external mutations should be explicit because network failures can happen after OpenProject accepted a write.
- The trigger-side legacy OpenProject client remains as reference code, but the active event worker delegates orchestration to planning core.
- Feedback classification is deterministic and marker-based; detailed OpenProject type/status/custom-field mapping remains future Phase 4 work.

## Verification

Focused Phase 4 command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q tests/test_phase4_openproject_adapter.py tests/test_phase3_project_orchestrator.py
```

Result:

```text
18 passed in 0.40s
```

Full suite command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
60 passed, 3 skipped, 4 warnings in 1.30s
```

Live PostgreSQL command:

```powershell
docker run --rm -d --name ada-phase4-pg-$PID -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ada_phase4 -p 127.0.0.1::5432 postgres:17-alpine
$env:PHASE3_POSTGRES_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:<port>/ada_phase4"
$env:LANGGRAPH_PERSISTENCE_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:<port>/ada_phase4"
.venv\Scripts\python.exe -m pytest -q tests/test_phase3_postgres_integration.py tests/test_phase3_langgraph_persistence.py::test_langgraph_postgres_checkpoint_survives_recreated_checkpointer
docker rm -f ada-phase4-pg-$PID
```

Result:

```text
3 passed in 1.86s
```

Alembic history:

```text
0004_agent_executions -> 0005_op_outbound_ops (head), add OpenProject outbound operation idempotency
0003_agent_job_leases -> 0004_agent_executions, add agent execution tracking
0002_webhook_event_idempotency -> 0003_agent_job_leases, add agent job leases and retry scheduling
0001_current_baseline -> 0002_webhook_event_idempotency, add webhook event idempotency key
<base> -> 0001_current_baseline, current baseline schema
```

## Remaining Phase 4 Work

- Add semantic mapping for OpenProject work-package types, statuses, priorities, approvals, and verification states.
- Persist reconciliation snapshots that preserve human edits before agent updates.
- Upsert `ExternalArtifact` mappings as projection workflows create or discover OpenProject work packages.
- Add approval records and explicit resume logic for planning and task-completion approvals.
- Update OpenProject provisioning for idempotent discovery of types, statuses, custom fields, webhooks, permissions, and sample binding.
