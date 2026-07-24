# Phase 8 Verification Override Results

## Summary

The Verification Agent now supports a configuration-driven human override gate for failed
verification outcomes. Overrides are disabled by default. When enabled for an eligible verdict,
the agent returns its original failed or blocked result with `request_approval` and the durable
flow pauses at `waiting_for_approval`.

A dedicated command can then complete the flow while appending a typed audit record. The command
does not mutate the Verification result, verdict, findings, acceptance matrix, or evidence.

## Policy

`VerificationAgentConfig` adds:

| Setting | Default | Purpose |
| --- | --- | --- |
| `human_override_enabled` | `false` | Enables the override gate for this Verification execution. |
| `human_override_allowed_verdicts` | `["changes_requested"]` | Restricts the negative verdicts that may be overridden. |

Only `changes_requested` and `blocked` can be configured as eligible. Enabling the policy with an
empty verdict list is rejected.

When a verdict is eligible:

- The original `VerificationAgentResult.status` remains `failed` or `blocked`.
- The original verdict and findings remain unchanged.
- `human_override_eligible` is set on the result and checkpoint state.
- `next_action` becomes `request_approval`.
- The flow stops before automatic coding rework or escalation.

When override is disabled, existing rework and escalation routing is unchanged.

## Command

The typed `VerificationOverrideCommand` requires:

- `actor`
- `reason`
- `override_reference`
- Optional JSON metadata

The API endpoint is:

```http
POST /v1/agents/flows/{flow_id}/verification-override
```

Example:

```json
{
  "expected_version": 2,
  "actor": "reviewer@example.test",
  "reason": "Approved by change control for this controlled release.",
  "override_reference": "change-control-417",
  "metadata": {
    "ticket": "CC-417"
  }
}
```

The service reconstructs policy from the persisted Verification step. Callers cannot enable the
policy, broaden eligible verdicts, select another source result, or supply the original outcome.
Stale flow versions and non-Verification approval gates are rejected.

## Audit Record

`AgentFlowOverrideRecord` is stored in the durable flow aggregate and contains:

- Override ID and type
- Source step sequence
- Source agent, execution, and result IDs
- Original agent status, next action, and verdict
- Finding codes and affected acceptance-criterion keys
- Actor, reason, external reference, metadata, and server timestamp

The flow status changes to `completed`, but its persisted source step still contains the original
failed Verification result. PostgreSQL persistence stores the appended override record in the
flow's JSONB snapshot under optimistic version control. Recreating the SQLAlchemy store preserves
the complete audit.

## Security Boundary

This repository intentionally does not add user management. The API records the caller-supplied
actor but does not authenticate that identity. Production deployment must protect the override
endpoint through the external gateway or identity layer and propagate a trusted actor value.

## Validation

Coverage includes:

- Command and configuration validation.
- Default rework behavior when override is disabled.
- Eligible Verification failure routing to a durable approval gate.
- Completion by override without mutation of the failed source result.
- Source execution/result identity, finding, criterion, actor, reason, and reference capture.
- Optimistic version conflicts.
- Typed API command forwarding.
- PostgreSQL persistence and store recreation.

Results:

- Changed-file Ruff and example JSON validation: passed.
- Focused override, verification, flow, API, and transition tests: 71 passed.
- Dedicated live PostgreSQL override recreation test: passed.
- Full suite with live PostgreSQL integration gates enabled: 210 passed, 1 skipped, and 4
  pre-existing warnings.

## Follow-On Completion

- Verification status, evidence summary, and override history projection to OpenProject is
  complete; see `docs/phase-8-openproject-verification-results.md`.
