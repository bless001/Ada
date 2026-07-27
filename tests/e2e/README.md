# End-to-End Tests

The tests in this directory exercise live infrastructure and are excluded from normal test runs
unless their explicit enable flag is set.

## Phase 9 Sample Project Flow

`test_sample_project_openproject_flow.py` runs the production Coding Agent and Verification Agent
through the orchestrator. It uses:

- A temporary Git copy of `sample_project`.
- A real PostgreSQL application database.
- A provisioned OpenProject project and bot API token.
- The registered production agent factory, transition resolver, flow store, repository binding
  store, outbound operation store, and OpenProject adapter.

The test creates a unique approved task and OpenProject work package. The Coding Agent adds
percentage-discount behavior and a pytest test, and the Verification Agent independently evaluates
the diff, command evidence, and acceptance criterion. The test then verifies the persisted flow,
outbound operations, artifact mapping, OpenProject evidence comment, and final work-package status.

The LLM is intentionally not used in this E2E. The approved coding attempt is supplied explicitly,
which makes the infrastructure and agent-runtime validation deterministic.

## Required Environment

```text
PHASE9_E2E_ENABLED=1
PHASE9_E2E_DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/<database>
PHASE9_OPENPROJECT_BASE_URL=http://localhost:8081
PHASE9_OPENPROJECT_PROJECT_ID=<test-project-id>
```

Supply the bot credential through one of:

```text
PHASE9_OPENPROJECT_API_TOKEN=<token>
PHASE9_OPENPROJECT_API_TOKEN_FILE=<host-readable-token-file>
```

If the OpenProject instance does not define a `Verified` status, the test discovers `Closed` or
`Done` and passes that name through Verification Agent configuration. Set
`PHASE9_OPENPROJECT_VERIFIED_STATUS_NAME` to require a specific available status.

## Compose Setup

From the repository root:

```powershell
docker compose up -d agent-secrets-init openproject agent-webhook
docker compose run --rm openproject-provision
```

The provisioning report at `/agent-secrets/openproject_provisioning.json` contains the starter
project ID and confirms that the `Task` type is enabled for that project. The token at
`/agent-secrets/openproject_api_token` is secret and must not be logged or committed.

Run the test after exporting the required values:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/e2e/test_sample_project_openproject_flow.py
```

Without `PHASE9_E2E_ENABLED=1`, the test is collected and reported as skipped.
