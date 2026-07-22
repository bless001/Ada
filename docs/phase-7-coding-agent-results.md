# Phase 7 Coding Agent Results

Baseline date: 2026-07-22

## Scope Completed

- Added coding attempt domain contracts for file changes, quality commands, command execution records, rollback plans, and attempt results.
- Added `CodingAttemptStatus` to the domain enum set.
- Added a safe local command runner that executes argument arrays only, never uses a shell, enforces timeouts, truncates output, and redacts configured secret values from command evidence.
- Added repository write tracking so file writes must be pre-authorized through the repository write path policy before they are recorded as changed files.
- Added a bounded coding attempt runner that applies explicit file upserts, runs allowlisted quality commands, captures command evidence, captures repository diffs, and marks attempts as succeeded, failed, or blocked.
- Added rollback-plan capture using the final diff as an audited reverse-diff strategy rather than performing automatic destructive rollback.
- Added `coding_attempts` persistence with Alembic migration `0010_coding_attempts`.
- Added `SqlAlchemyCodingAttemptStore` with next-attempt-number allocation and idempotent result upsert by project, repository, task, and attempt number.
- Added `CodingService` to bind persisted repository policy, local repository access, safe command execution, and attempt persistence.
- Added focused tests for safe command redaction/truncation, allowlisted writes, blocked writes, failed quality commands, shell-string rejection, ORM contract, import smoke, and live PostgreSQL persistence.

## Runtime Compatibility Notes

- This phase does not add autonomous patch generation. The runner accepts explicit file changes only.
- File deletion is intentionally not supported in this slice; only `upsert` changes are accepted.
- Rollback is captured as an audited reverse-diff plan and is not automatically executed.
- Repository command execution is allowed only when the executable name appears in the repository binding command allowlist.
- Failed quality commands cannot produce a succeeded attempt result.
- The coding workflow graph, coding skill manifests, OpenProject progress comments, and verification handoff remain future Phase 7 work.

## Verification

Focused Phase 7 command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q tests/test_phase7_coding_agent.py tests/test_phase1_boundaries.py tests/test_import_smoke.py
```

Result:

```text
9 passed in 10.85s
```

Full suite command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
114 passed, 10 skipped, 4 warnings in 10.68s
```

Live PostgreSQL command:

```powershell
docker run --rm -d --name ada-phase7-pg-<id> -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ada_phase7 -p 127.0.0.1::5432 postgres:17-alpine
$env:PHASE3_POSTGRES_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:<port>/ada_phase7"
$env:LANGGRAPH_PERSISTENCE_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:<port>/ada_phase7"
.venv\Scripts\python.exe -m pytest -q tests/test_phase3_postgres_integration.py tests/test_phase3_langgraph_persistence.py::test_langgraph_postgres_checkpoint_survives_recreated_checkpointer
docker rm -f ada-phase7-pg-<id>
```

Result:

```text
9 passed in 3.67s
```

## Remaining Phase 7 Work

- Add coding workflow graph nodes for task selection, context capsule loading, policy checks, implementation attempt, quality checks, evidence capture, retry decision, and verification handoff.
- Add coding skill manifests and runnable skills for context interpretation, patch proposal, patch application, failure interpretation, and progress summarization.
- Add branch creation/selection policy and explicit diff finalization rules.
- Add approved rollback execution path that applies the recorded reverse diff only after policy and approval checks.
- Add OpenProject task progress projection with bounded, idempotent comments.
- Add integration tests for approved sample tasks that change only allowlisted paths and fail closed on quality-check failures.
