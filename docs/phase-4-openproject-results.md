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
- Added semantic mapping for OpenProject work-package types, statuses, priorities, approvals, feedback intents, and verification outcomes.
- Added `OpenProjectSemanticMapper` and `OpenProjectResourceCatalog` so provisioning can resolve names to HAL links without hard-coded numeric IDs.
- Added OpenProject adapter discovery methods for types, statuses, priorities, and resource-catalog loading.
- Added `openproject_reconciliation_snapshots` for preserving OpenProject state before agent updates.
- Added Alembic migration `0006_op_reconciliation`.
- Added `OpenProjectReconciliationStorePort` and `SqlAlchemyOpenProjectReconciliationStore`.
- Added deterministic reconciliation summaries for changed subject, description, status, type, and priority fields.
- Updated the OpenProject adapter to capture work-package payloads and activities before PATCH updates, and work-package payloads before idempotent comments.
- Added `OpenProjectArtifactMapping`, `OpenProjectArtifactStorePort`, and `SqlAlchemyOpenProjectArtifactStore` for durable OpenProject-to-local mapping upserts.
- Updated the OpenProject adapter to upsert `ExternalArtifact` rows after project creation, work-package creation, work-package update, comment-time discovery, and duplicate-success replay.
- Added `approval_records` as the durable audit table for plan and task-completion approval decisions.
- Added Alembic migration `0007_approval_records`.
- Added `ApprovalScope`, `ApprovalDecision`, `ApprovalRecordStorePort`, and `SqlAlchemyApprovalRecordStore`.
- Added OpenProject approval classification that maps approvals to `approved`, plan feedback/rework/requirement changes to `changes_requested`, and cancellations to `cancelled`.
- Updated OpenProject event orchestration to record approval decisions, resume plan approvals from `plan_drafted` and `awaiting_review` sessions, and record task-completion approvals without starting a planning workflow.
- Added source-decision idempotency for approval records so retried webhook jobs do not duplicate approval audit rows.
- Updated the opt-in live PostgreSQL integration test to expect Alembic head `0007_approval_records`.
- Added an opt-in live PostgreSQL integration assertion for idempotent OpenProject artifact upserts.
- Added an opt-in live PostgreSQL integration assertion for idempotent approval source decisions.
- Hardened `infra/openproject/provision/ensure_agent_bot_token_webhook.rb` so provisioning discovers required work-package types, semantic statuses, priorities, and recommended agent custom fields by name before projection depends on them.
- Added a non-secret OpenProject provisioning report at `/agent-secrets/openproject_provisioning.json` containing discovered IDs, webhook configuration, starter project metadata, project modules, bot role/permission setup, sample repository binding, and warnings.
- Added idempotent starter project module setup, non-admin bot role setup, and sample project repository binding metadata.
- Kept custom field creation opt-in through `OP_ENSURE_AGENT_CUSTOM_FIELDS=false` by default because OpenProject custom-field assignment behavior is version-sensitive.
- Added Docker Compose defaults for provisioning discovery inputs and mounted the provisioning report path into planning-agent-core.
- Added static regression tests for the OpenProject provisioning contract.

## Runtime Compatibility Notes

- Mutating OpenProject adapter methods require an `OpenProjectOutboundStorePort`; without it they raise instead of performing unsafe direct writes.
- Repeated outbound idempotency keys return the prior successful response and do not issue another OpenProject HTTP request.
- Failed or pending outbound operation records are not automatically retried in this slice; retry policy for external mutations should be explicit because network failures can happen after OpenProject accepted a write.
- The trigger-side legacy OpenProject client remains as reference code, but the active event worker delegates orchestration to planning core.
- Feedback classification is deterministic and marker-based.
- Semantic mapping is name-based and fails clearly when provisioning has not supplied a required OpenProject type, status, or priority link.
- Vision and Capability plan nodes are not projected as work packages by default; the default OpenProject hierarchy starts at Epic, then Story, then Task.
- Reconciliation capture is opt-in through `OpenProjectReconciliationStorePort`; adapter writes remain a no-op for snapshots unless a store is supplied.
- Snapshot capture happens after an outbound idempotency claim is accepted and before the OpenProject mutation is issued.
- Reconciliation summaries are metadata only; the complete pre-update OpenProject payload remains the source of truth for preserving human edits.
- Artifact mapping capture is opt-in through `OpenProjectArtifactStorePort`; callers must provide a local project ID so OpenProject IDs can route future webhooks back to local projects.
- Work-package update paths first record the discovered pre-update work package mapping, then refresh the mapping again after the PATCH succeeds.
- Approval records are immutable audit rows keyed by source event context rather than mutable workflow state.
- Repeated approval source decisions return the existing approval record ID.
- Planning approval events can resume review-state planning sessions; task-completion approvals are recorded as context-only until coding and verification workflows exist.
- The provisioner does not create work-package types, statuses, or priorities. It discovers and reports them because OpenProject workflows are version- and permission-sensitive, and the adapter already fails clearly when a semantic mapping is absent.
- Recommended custom fields are discovered and reported by default. Set `OP_ENSURE_AGENT_CUSTOM_FIELDS=true` only when the target OpenProject version supports the desired work-package custom-field format and assignment model.
- The provisioning report records only the API token file path, not the token value.

## Verification

Focused Phase 4 command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q tests/test_phase4_openproject_provisioning.py tests/test_phase4_openproject_approvals.py tests/test_phase4_openproject_mapping.py tests/test_phase4_openproject_adapter.py tests/test_phase3_project_orchestrator.py
```

Result:

```text
46 passed in 0.43s
```

Full suite command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
88 passed, 5 skipped, 4 warnings in 1.24s
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
5 passed in 2.56s
```

OpenProject provisioning Ruby syntax command:

```powershell
docker compose run --rm --no-deps openproject-provision ruby -c /provision/ensure_agent_bot_token_webhook.rb
```

Result:

```text
Syntax OK
```

Compose validation command:

```powershell
docker compose config --quiet
```

Result:

```text
passed
```

Whitespace validation command:

```powershell
git diff --check -- ':!.venv'
```

Result:

```text
passed with CRLF normalization warnings only
```

Alembic history:

```text
0006_op_reconciliation -> 0007_approval_records (head), add approval records
0005_op_outbound_ops -> 0006_op_reconciliation, add OpenProject reconciliation snapshots
0004_agent_executions -> 0005_op_outbound_ops, add OpenProject outbound operation idempotency
0003_agent_job_leases -> 0004_agent_executions, add agent execution tracking
0002_webhook_event_idempotency -> 0003_agent_job_leases, add agent job leases and retry scheduling
0001_current_baseline -> 0002_webhook_event_idempotency, add webhook event idempotency key
<base> -> 0001_current_baseline, current baseline schema
```

## Phase 4 Status

- Phase 4 planned tasks are complete.
