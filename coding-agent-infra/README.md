# Coding Agent Full Infrastructure

This is a complete MVP infrastructure for your coding-agent idea.

It includes:

| Service | Purpose | Host URL / Port |
|---|---|---|
| OpenProject | Human-agent project planning and approval UI | http://localhost:8081 |
| PostgreSQL | Agent app state + OpenProject database | localhost:5432 |
| Redis | Webhook/job queue | localhost:6379 |
| Neo4j | Code graph + project graph + memory graph | http://localhost:7474 |
| Weaviate | Vector database | http://localhost:8080 |
| llama.cpp | Optional local LLM server | http://localhost:8082 |
| agent-webhook | Receives OpenProject webhooks | http://localhost:8090 |
| agent-worker | Processes events and triggers agent placeholder | internal |
| openproject-provision | One-time zero-manual OpenProject provisioning | internal |

## What is zero-manual here?

When you run Docker Compose, the provisioner automatically creates:

```text
coding-agent-bot user
admin permissions for the bot
OpenProject API token for the bot
OpenProject webhook pointing to agent-webhook
optional starter OpenProject project
```

The API token is saved in a Docker volume and mounted read-only into the agent worker:

```text
/agent-secrets/openproject_api_token
```

So you do **not** need to manually create a bot user, API token, or webhook in the OpenProject UI.

## Start

```bash
cp .env.example .env
mkdir -p models workspace
docker compose up -d --build
```

Or with Make:

```bash
make setup
make up
```

Watch the important logs:

```bash
docker compose logs -f openproject-provision agent-webhook agent-worker
```

OpenProject:

```text
http://localhost:8081
```

Neo4j:

```text
http://localhost:7474
```

Weaviate:

```text
http://localhost:8080
```

## Start llama.cpp

Put a GGUF model in:

```text
./models/
```

Edit `.env`:

```env
LLAMA_MODEL_FILE=your-model.gguf
```

Start with the LLM profile:

```bash
docker compose --profile llm up -d --build
```

## OpenProject workflow idea

Use OpenProject work packages as the human-agent control surface:

```text
Epic / Feature / Task
        ↓
User reviews plan and comments
        ↓
User moves work package to In Development
        ↓
Webhook fires
        ↓
agent-worker fetches full context
        ↓
agent starts implementation
```

The worker starts the coding-agent placeholder only when the work package status matches:

```env
AGENT_TRIGGER_STATUS_NAMES=In Development,Agent Development
```

## Where to plug in the real coding agent

Edit:

```text
agent_trigger/app/agent_bridge.py
```

Replace:

```python
run_coding_agent_placeholder(...)
```

with your real coding-agent runner.

That runner should eventually:

```text
sync OpenProject work package/comments into Neo4j
embed descriptions/comments/decisions into Weaviate
create a git branch
use Tree-sitter/LSP/code graph context
implement the task
run tests
post progress/results back to OpenProject
```

## Webhook flow

```text
OpenProject comment/status update
        ↓
agent-webhook FastAPI service
        ↓
PostgreSQL pm_webhook_events table
        ↓
Redis queue
        ↓
agent-worker
        ↓
OpenProject API fetches full work package + activities
        ↓
context snapshot stored in PostgreSQL
        ↓
agent placeholder runs if status allows
```

## Test webhook receiver manually

This only tests the receiver/queue path. It does not fetch a real work package unless ID 1 exists.

```bash
make test-webhook
```

## Show generated bot API token

```bash
make show-token
```

## Important security notes

For MVP, the bot is created as admin:

```env
OP_AGENT_ADMIN=true
```

This gives the agent broad control so it can create and maintain projects.

For production, change this design later:

```text
OP_AGENT_ADMIN=false
create a dedicated global/project role
grant only required permissions
store secrets in Vault/Kubernetes secrets/Docker secrets
use HTTPS
restrict webhook network access
```

## Reset everything

```bash
docker compose down -v
```

This deletes all persistent data.


## Fix included in this version

This fixed package uses `SECRET_KEY_BASE` for the OpenProject Docker container and generates a real random value during setup.

OpenProject 17.3.2+ refuses to boot with a missing/default/weak `SECRET_KEY_BASE`, so do not only copy `.env.example`.
Run:

```bash
make setup
```

or:

```bash
python scripts/generate_env.py
```

If the provisioner fails, it now prints the real Rails error and stops after 5 minutes instead of waiting forever.


## Troubleshooting: bot password validation

OpenProject requires generated user passwords to contain lowercase, uppercase, numeric, and special characters.

This package generates the `coding-agent-bot` password using:

```ruby
generate_policy_compliant_password(64)
```

If you still see this error:

```text
Validation failed: Password Must include characters of the following types...
```

run a clean retry:

```bash
docker compose down -v --remove-orphans
make setup
make up
make logs
```
