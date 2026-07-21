# ADR 0004: Enforce Mounted Repository Boundaries

## Status

Accepted

## Context

The target system will inspect repositories and eventually modify code. The README requires support for repositories mounted into agent containers and explicitly forbids arbitrary execution or unrestricted shell access.

## Decision

All repository reads, writes, diffs, and command execution must go through configured repository bindings and policy checks. The system must enforce path containment, write allowlists, denylists, command allowlists, timeouts, output limits, and secret redaction before coding-agent behavior is enabled.

## Consequences

- Planning and verification can remain read-only by default.
- Coding-agent implementation is blocked until repository safety tests exist.
- Legacy code in `src/execution` must not be used directly without a policy wrapper.
- Attempts to access paths outside the configured mount must fail deterministically and be audited.
