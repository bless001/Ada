# Phase 9 End-to-End Results

## Summary

The first Phase 9 task is complete. An opt-in E2E test now proves the production Coding Agent to
Verification Agent flow using `sample_project`, PostgreSQL, and a live provisioned OpenProject
project.

The test is deterministic: it starts from an approved persisted task and explicit coding attempt
rather than depending on LLM output. This keeps the test focused on repository safety, agent
composition, orchestration, checkpoint/result persistence, verification, and infrastructure
projection.

## Covered Flow

The E2E test performs these steps:

1. Copies `sample_project` into a temporary isolated Git repository.
2. Adds the missing baseline payment service and commits the fixture state.
3. Persists a local project, approved plan version, task identity, acceptance criterion, and
   read-write repository binding.
4. Creates a unique Task work package in the configured OpenProject test project.
5. Creates the production agent platform service with real SQLAlchemy stores and an injected live
   OpenProject gateway.
6. Runs the Coding Agent for one approved task, modifying `main.py` and `test_main.py`.
7. Runs targeted pytest through the command policy and records its result.
8. Routes the Coding result to the independently executed Verification Agent.
9. Validates the acceptance-coverage and test-evidence contracts.
10. Projects the Verification evidence and final status to OpenProject.
11. Reads the work package and activities back through the OpenProject API.
12. Verifies the three durable outbound operations and external-artifact mapping in PostgreSQL.

## Supporting Hardening

The live run identified and fixed two production integration defects:

- The OpenProject provisioner discovered global work-package types but did not enable them for the
  starter project. It now idempotently enables every available required type and records
  `project_work_package_types` in the non-secret provisioning report.
- Work-package updates fetched the current OpenProject representation but did not include its
  optimistic-concurrency `lockVersion` in PATCH requests. The adapter now derives that transport
  field from the server snapshot while preserving the original agent payload in reconciliation
  history.

Verification-to-OpenProject status names are now configuration-driven:

- `openproject_verified_status_name`
- `openproject_changes_required_status_name`
- `openproject_blocked_status_name`
- `openproject_override_status_name`

This allows a stock OpenProject installation to use an existing completion status such as `Closed`
without hard-coding a numeric status ID or weakening semantic mapping.

Production database composition also accepts an explicit platform configuration and work-package
gateway. Existing API callers retain the previous defaults; the injectable seam allows isolated
integration testing without module-level clients.

## Safety And Isolation

- The source `sample_project` is never modified.
- Every run uses a new temporary Git working tree and unique local/OpenProject records.
- Repository writes are limited to `main.py` and `test_main.py`.
- Commands are restricted to the active Python executable and the explicit pytest invocation.
- Database and API-token fields are excluded from pytest fixture representations.
- No secret value is written to the repository or E2E documentation.
- The OpenProject project is expected to be disposable test infrastructure; unique E2E work
  packages are retained as audit evidence.

## Validation

Focused validation:

```powershell
.venv\Scripts\python.exe -m ruff check <changed Python files>
.venv\Scripts\python.exe -m pytest -q tests/test_phase4_openproject_provisioning.py tests/test_agent_platform_api.py tests/test_verification_openproject_projection.py
docker compose run --rm --no-deps openproject-provision ruby -c /provision/ensure_agent_bot_token_webhook.rb
```

Results:

- Ruff: passed.
- Provisioner, composition, and projection tests: `30 passed`.
- OpenProject adapter and projection regression tests: `31 passed`.
- Provisioner Ruby syntax: passed.
- Live Phase 9 E2E: `1 passed in 18.30s`.
- Full suite with live PostgreSQL integration gates: `223 passed, 2 skipped, 4 warnings`.

The default full suite still collects the E2E test but skips it unless
`PHASE9_E2E_ENABLED=1` is set. Setup and environment details are in `tests/e2e/README.md`.

## Remaining Phase 9 Work

- Add the infrastructure smoke-test script.
- Complete operations, troubleshooting, testing, data-model, integration, and architecture docs.
- Reconcile Compose service naming and optional services with the README.
- Clarify external llama.cpp deployment paths.
- Expand structured metrics/logging fields.
- Add golden datasets for deterministic planning and verification behaviors.
