# Phase 8 OpenProject Verification Projection Results

## Summary

The final Phase 8 task is complete. Verification results now project to the task's mapped
OpenProject work package through the existing port, outbound idempotency store, artifact mapping,
and reconciliation infrastructure.

The projection is an application service outside the Verification Agent workflow. The agent still
owns verification logic and returns one immutable typed result. The orchestrator-facing service
derives the OpenProject representation after that result exists; no OpenProject client is imported
by Verification Agent business logic.

## Projection Contract

`VerificationOpenProjectProjectionService` accepts typed agent execution, result, flow, and
override contracts. It resolves the projection target from:

- An explicit OpenProject work-package ID in request metadata, or
- A `work_package` input artifact whose `system_name` is `openproject`.

Local project and plan-node identity IDs are carried in transition and artifact metadata. This
allows the existing adapter to preserve `ExternalArtifact` mappings and attach reconciliation
snapshots to local records. Multiple distinct mapped work packages are rejected rather than
guessed.

Projection is controlled by `VerificationAgentConfig.openproject_projection_enabled`, which
defaults to `true`. It is a no-op when disabled, when no gateway is injected, or when the
Verification request has no OpenProject mapping.

## Status Semantics

Verification verdicts map to provisioned semantic statuses by name:

| Verification verdict | OpenProject semantic status |
| --- | --- |
| `passed` | `Verified` |
| `passed_with_warnings` | `Verified` |
| `changes_requested` | `Changes required` |
| `blocked` | `Blocked` |
| Human completion override | `Done` |

The projection loads the target OpenProject resource catalog and resolves status HAL links through
`OpenProjectSemanticMapper`. Numeric OpenProject status IDs are not hard-coded. A missing or
ambiguous semantic status fails clearly and leaves a durable flow recoverable.

`Done` is used for a human completion override instead of `Verified` because the original
Verification Agent did not pass the task. The appended audit comment records that distinction.

## Evidence Comment

Each Verification execution adds one bounded Markdown comment containing:

- Verdict, task key, execution ID, and Verification summary
- Satisfied and total acceptance-criterion counts
- Test, quality-command, and external-evidence counts
- Regression risk, security issue count, and changed-file count
- Per-criterion outcomes and rationales
- Structured finding severity, code, criterion key, and message
- Typed evidence references when supplied

The actual repository diff and raw command output are not copied into OpenProject. They remain in
the durable Verification result and evidence stores.

## Override History

A successful human completion override adds a separate append-only comment containing:

- Workflow, task, and original Verification execution identities
- Original negative verdict
- Actor, reason, external override reference, and server timestamp
- Original finding codes and affected acceptance-criterion keys
- An explicit statement that the original Verification result was not changed

The override ID is deterministic from the flow, source result, and external override reference.
If projection fails before the override audit is committed, retrying the same command regenerates
the same outbound operation keys.

## Idempotency And Recovery

Normal Verification operations use keys derived from the immutable Verification execution ID.
Override operations use keys derived from the deterministic override ID. Evidence/audit comments
and status updates use separate keys.

The PostgreSQL outbound store now:

- Locks an existing operation before evaluating retry state.
- Rejects reuse of an idempotency key for another operation type.
- Reclaims failed operations as pending while preserving a single durable operation identity.
- Leaves already pending or successful operations non-executable.

For reclaimed comments, the OpenProject adapter first reads work-package activities and searches
for the embedded Ada idempotency marker. If OpenProject accepted the original comment but the HTTP
response was lost, the adapter records the discovered activity as successful instead of posting a
duplicate.

Projection runs before durable flow completion. A configured OpenProject failure therefore does
not falsely complete the flow; normal flow lease recovery can rerun the same Verification
execution and operation keys.

## Runtime Composition

Database-backed platform composition now injects a managed `WorkPackageGateway` built from:

- `OpenProjectClient`
- `SqlAlchemyOpenProjectArtifactStore`
- `SqlAlchemyOpenProjectOutboundStore`
- `SqlAlchemyOpenProjectReconciliationStore`

The managed gateway creates and closes a concrete HTTP client around each operation. Agent modules
depend only on the gateway abstraction; module-level infrastructure clients were not added.

The projection hook covers:

- Direct Verification execution
- Initial bounded flows
- Resumed flows
- Recovered flows
- Background-worker claimed flows
- Verification completion overrides

## Compatibility

- Existing requests without OpenProject mappings continue without network calls.
- Existing factory registration and agent lifecycle contracts are unchanged.
- Existing Verification result payloads remain valid.
- Work-package mapping upserts no longer clear a previously known plan-node identity when a caller
  omits that optional identity.
- OpenProject status names must exist in the provisioned resource catalog.

## Validation

Coverage includes:

- All four verdict-to-status mappings.
- Evidence comment rendering and stable operation keys.
- Disabled and unmapped no-op behavior.
- Ambiguous target rejection.
- Full persisted flow projection and override audit behavior.
- Original Verification result immutability.
- Deterministic override identity across failed projection retries.
- Managed OpenProject client closure.
- Failed outbound operation reclaim.
- Reclaimed comment activity reconciliation.
- Database composition of the managed gateway.
- Existing Phase 4 adapter, Verification, flow, API, and PostgreSQL contracts.

Results:

- Focused projection, override, adapter, and API tests: 49 passed.
- Changed-file Ruff and `git diff --check`: passed.
- Full suite with live PostgreSQL integration gates enabled: 220 passed, 2 skipped, and 4
  pre-existing warnings.

No live OpenProject mutation was executed for this slice. A real OpenProject project and the
`sample_project` planning-to-verification path remain part of Phase 9 E2E hardening.

## Phase Status

Phase 8 is complete.
