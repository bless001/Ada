# Agent Platform Flow Recovery Results

## Summary

Running agent flows now use expiring lease tokens and can be recovered explicitly after process
interruption. Recovery preserves the original execution scope, invalidates stale workers through
optimistic versioning, and records an append-only takeover audit.

## Safety Contract

- Every start and resume reservation receives a unique lease token.
- Completion requires the current aggregate version, lease token, and an unexpired lease.
- Heartbeat requires the current version and token.
- Heartbeat extends expiry without changing the aggregate version or token.
- An active or mismatched lease returns a conflict.
- Recovery is allowed only for a `running` aggregate whose lease has expired.
- Recovery must exactly match the persisted typed `AgentExecutionRequest`.
- Recovery replaces the lease, increments the aggregate version, and records old and new leases.
- A stale worker cannot complete because its version and lease token are no longer current.
- Recovery can be disabled through platform configuration.

## API

```text
GET  /v1/agents/flows/by-workflow?project_id=...&workflow_id=...
POST /v1/agents/flows/{flow_id}/heartbeat
POST /v1/agents/flows/{flow_id}/recover
```

Workflow lookup allows callers to find a reserved flow when the original synchronous start request
failed before returning its `flow_id`. Callers that require this recovery path must supply a stable
`workflow_id` when starting the flow rather than relying on the server-generated default.

Heartbeat payload:

```json
{
  "expected_version": 1,
  "lease_id": "00000000-0000-0000-0000-000000000000"
}
```

Recovery requires `expected_version`, `recovered_by`, the original typed agent request, and
optionally the original agent configuration. When configuration is omitted, the endpoint reloads
it from the pending aggregate payload.

## Configuration

```json
{
  "flow_runtime": {
    "lease_seconds": 300,
    "recovery_enabled": true
  }
}
```

Synchronous API execution does not run a concurrent database heartbeat. Configure
`lease_seconds` above the longest expected synchronous flow duration. External workers that own
longer claims should call heartbeat before expiry.

## Persistence

Migration `0013_agent_flow_recovery_leases` adds:

- `recovery_count`
- `lease_id`
- `lease_owner`
- `lease_acquired_at`
- `lease_expires_at`
- A recoverable-flow index on status and lease expiry.

Legacy rows left `running` by migration `0012` are backfilled with an already-expired migration
lease. They are immediately discoverable and recoverable. Paused and terminal rows remain
unleased.

## Validation

Coverage includes:

- Active-lease takeover rejection.
- Heartbeat extension without version churn.
- Mismatched token rejection.
- Exact-request replay enforcement.
- Recovery audit history.
- Stale worker completion rejection.
- Recovery-disable configuration.
- Workflow-based discovery.
- API `409` mapping for lease conflicts.
- Live PostgreSQL lease persistence, recovery, cleanup, and Alembic migration validation.

Commands run:

```powershell
.venv/Scripts/python.exe -m ruff check <changed Python files>
.venv/Scripts/python.exe -m pytest -q tests/test_agent_flow_persistence.py tests/test_agent_platform_api.py tests/test_agent_platform_flow.py tests/test_agent_platform.py
.venv/Scripts/python.exe -m pytest -q tests/test_agent_flow_postgres_integration.py tests/test_phase3_postgres_integration.py::test_phase3_alembic_upgrade_creates_expected_tables
..\.venv\Scripts\python.exe -m alembic -c alembic.ini heads
.venv/Scripts/python.exe -m pytest -q
```

Results:

- Ruff: passed.
- Focused flow, API, and platform tests: 47 passed.
- Live PostgreSQL recovery and migration tests: 2 passed.
- Alembic head: `0013_agent_flow_recovery_leases`.
- Full suite with PostgreSQL integrations enabled: 183 passed, 2 skipped, 4 existing warnings.
