# Phase 3 Event Ingestion Results

Baseline date: 2026-07-21

## Scope Completed

- Added typed event processing and job statuses to the domain event layer.
- Added deterministic event idempotency key generation based on canonical event fields and payload.
- Added core OpenProject event normalization under `planning_agent_core.application.event_classification`.
- Added SQLAlchemy ORM models for the existing webhook tables: `pm_webhook_events`, `agent_jobs`, and `pm_context_snapshots`.
- Added `idempotency_key` and `retry_at` to `pm_webhook_events`.
- Added job lease, retry, attempt-count, and terminal error fields to `agent_jobs`: `attempt_count`, `retry_at`, `lease_owner`, `lease_expires_at`, and `last_error`.
- Added Alembic migration `0002_webhook_event_idempotency`.
- Added Alembic migration `0003_agent_job_leases`.
- Added async `SqlAlchemyEventInbox` adapter with PostgreSQL `ON CONFLICT DO NOTHING` duplicate handling.
- Changed the event inbox port to return `EventInboxPersistResult` with `created` status so callers can avoid enqueueing duplicate deliveries.
- Added event queue port and Redis queue adapter.
- Added deterministic retry classification helper in the core package.
- Migrated `infra/agent_trigger` webhook parsing to compute the same idempotency key as the core event classifier.
- Migrated `infra/agent_trigger` storage to persist duplicate-safe webhook events with `ON CONFLICT (idempotency_key) DO NOTHING`.
- Updated `infra/agent_trigger` webhook response behavior so duplicate deliveries return `status: duplicate` and do not enqueue another Redis item.
- Added trigger worker lease acquisition before event processing.
- Added bounded retry scheduling with durable `retry_at` and recoverable job re-enqueue scanning.
- Added terminal `dead_letter` recording for non-retryable failures or exhausted attempts.
- Added `ProjectEventOrchestrator` to load persisted inbox events, resolve local project mappings, and route resumable OpenProject feedback into the planning workflow runner.
- Added `POST /v1/events/{event_id}/orchestrate` as a manual core entry point for persisted-event orchestration.
- Updated the Docker-init PostgreSQL schema to match the new idempotency, lease, retry, and dead-letter columns.
- Added tests for event fingerprints, OpenProject normalization, ORM table registration, PostgreSQL conflict SQL, Redis queue behavior, retry classification, trigger duplicate handling, worker lease SQL, retry scheduling, dead-letter recording, recoverable job scanning, and persisted-event orchestrator routing.
- Installed `redis>=5.2` into the repaired `.venv`.

## Runtime Compatibility Notes

- `infra/agent_trigger` remains a standalone service because its Docker build context currently copies only `requirements.txt` and `app/`.
- The trigger parser intentionally mirrors the core classifier instead of importing `planning_agent_core`; this avoids breaking the current trigger container.
- The new async inbox adapter is ready for core worker integration, but the live trigger service still uses synchronous `psycopg` storage.
- Duplicate delivery safety is now enforced in both the core inbox adapter and the live trigger storage path.
- Worker lease and retry behavior is now durable in `agent_jobs`.
- The core orchestrator resumes planning with the existing `planning-session-{session_id}` LangGraph thread ID, so checkpoint resume can work once a durable checkpointer is configured.
- OpenProject event-to-project resolution currently depends on `ExternalArtifact` mappings for `project` or `work_package` artifacts.
- Feedback classification is intentionally coarse in this slice; detailed requirement-change, approval, pause, resume, and cancellation semantics remain Phase 4 work.
- `create_schema()` remains in planning-core startup, so Alembic is scaffolded but not yet enforced at service startup.

## Verification

Environment:

```text
C:\repo_gitlab\Ada\.venv
```

Command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
36 passed, 4 warnings in 2.04s
```

Warnings:

- `fastapi.testclient` emits a Starlette deprecation warning about `httpx`.
- `test_ada.py::test_imports` returns `bool` instead of using assertions.
- `test_ada.py::test_agent_functionality` returns `bool` instead of using assertions.
- `test_ada.py::test_config` returns `bool` instead of using assertions.

Alembic history sanity check:

```powershell
cd planning_agent_core
..\.venv\Scripts\python.exe -m alembic -c alembic.ini history
```

Result:

```text
0002_webhook_event_idempotency -> 0003_agent_job_leases (head), add agent job leases and retry scheduling
0001_current_baseline -> 0002_webhook_event_idempotency, add webhook event idempotency key
<base> -> 0001_current_baseline, current baseline schema
```

## Remaining Phase 3 Work

- Run migrations against a clean PostgreSQL database.
- Move `agent_jobs` into the final general event-processing or workflow-execution table shape from the README.
- Replace the trigger-local parser and retry policy copies with shared core imports after the Docker build/package boundary is changed.
- Add LangGraph Postgres setup under `infra/scripts/setup_langgraph_persistence.py`.
- Add process-restart resume tests with LangGraph Postgres.
- Add duplicate webhook integration tests against a live or containerized Postgres instance.
- Add visible OpenProject dead-letter comments once outbound OpenProject writes have idempotency markers.
