# Coding Agent MVP Technical Specification

## 1. MVP Vision

The MVP is a **headless coding agent** that uses:

- **OpenProject** for project management context
- **Neo4j** for code graph and dependency relationships
- **Weaviate** for semantic code and document retrieval
- **PostgreSQL** for operational data
- **llama.cpp** as the local LLM provider
- **Python + FastAPI** for backend/API/agent orchestration
- **CLI-first workflow** instead of building a frontend in the MVP

The core concept must not be compromised:

> The agent should not rely only on LLM context. It should use project-management context, code graph relationships, vector search, keyword search, and repository inspection to build the right context before editing code.

The MVP goal is:

> Given an OpenProject work package and a repository, the agent should build a high-quality context package, identify relevant code, make a patch, run tests, and produce a human-reviewable diff.

---

## 2. Non-Goals for MVP

The following are intentionally excluded from MVP:

- Custom user management
- Full frontend application
- Multi-agent orchestration
- GitLab merge request automation
- Full LSP integration
- Advanced cross-language variable data flow
- Complex approval workflow
- Enterprise permissions
- Evaluation dashboard
- Multi-repository editing in one agent run

These can be added later without changing the core architecture.

---

## 3. MVP Tech Stack

### 3.1 LLM Provider

Use **llama.cpp** as the local model runtime.

Recommended access mode:

- Run llama.cpp server locally
- Expose an OpenAI-compatible endpoint if available
- Backend talks to llama.cpp through an `LLMProvider` abstraction

Example configuration:

```env
LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
LLAMA_CPP_MODEL_NAME=local-coding-model
LLM_CONTEXT_WINDOW=32768
LLM_TEMPERATURE=0.1
LLM_MAX_OUTPUT_TOKENS=4096
```

The codebase must not directly depend on a specific provider implementation. All model calls go through:

```text
llm/provider.py
llm/llama_cpp_provider.py
```

---

### 3.2 Project Management

Use **OpenProject** as the source of truth for:

- Epic
- Feature
- Story
- Task
- Bug
- Acceptance criteria
- Status
- Priority
- Assignee, if available

The coding-agent system should not recreate a full project-management module.

Instead, it should use an integration layer:

```text
integrations/openproject/
```

The agent should read OpenProject work packages and map them into an internal lightweight structure called `WorkItemContext`.

Example:

```python
@dataclass
class WorkItemContext:
    external_id: str
    type: str
    title: str
    description: str
    status: str | None
    priority: str | None
    parent_id: str | None
    acceptance_criteria: list[str]
    links: list[str]
```

For MVP, the agent only needs read access to OpenProject and optional comment/update access.

Required MVP OpenProject tools:

```text
get_work_package(work_package_id)
get_related_work_packages(work_package_id)
add_agent_comment(work_package_id, comment)
```

Do not implement full epic/story/task creation inside the agent database in MVP.

---

### 3.3 Code Graph

Use **Neo4j** for graph storage and traversal.

Neo4j stores relationships between:

- Repository
- File
- Class
- Function
- Method
- Variable summary
- Test
- API endpoint
- Work package

Neo4j should answer questions like:

```text
Which functions call this function?
Which functions are called by this function?
Which files import this file?
Which tests are related to this function?
Which work package previously touched this file?
```

The graph is a retrieval and impact-analysis layer, not a replacement for reading files.

---

### 3.4 Vector Database

Use **Weaviate** for semantic search over:

- Code chunks
- File summaries
- Function summaries
- Test summaries
- OpenProject work package descriptions
- Previous agent run summaries

Weaviate should answer:

```text
Which code chunks are semantically related to this task?
Which previous work item is similar?
Which files mention a similar concept even if exact words differ?
```

For MVP, store embeddings for:

```text
CodeChunk
FunctionSummary
FileSummary
WorkPackageSummary
AgentRunSummary
```

The embedding model can be local. The design should allow replacement later.

---

### 3.5 PostgreSQL

Use **PostgreSQL** only for operational data that does not belong in Neo4j or Weaviate.

PostgreSQL stores:

- Registered repositories
- Agent runs
- Tool calls
- Patches
- Test runs
- Workspace metadata
- OpenProject mapping metadata
- Indexing jobs

Do not store full project-management hierarchy in PostgreSQL in MVP. OpenProject already owns that.

---

### 3.6 Backend Runtime

Use:

```text
Python 3.11+
FastAPI
SQLAlchemy
Alembic
Pydantic
Neo4j Python driver
Weaviate Python client
httpx
GitPython or subprocess git wrapper
```

FastAPI is mainly used for:

- CLI/backend API access
- Webhook support later
- Agent run management
- Repository indexing endpoints
- Context package inspection

A frontend is optional and not part of MVP.

---

## 4. MVP Architecture

```text
OpenProject
   ↓
WorkItemContext
   ↓
Repository Indexer ───→ Neo4j Code Graph
   ↓                     ↑
Code Chunks ─────────→ Weaviate Vector DB
   ↓
Context Builder
   ↓
llama.cpp Coding Agent
   ↓
Patch + Test Run + Diff
   ↓
PostgreSQL Agent Run Records
   ↓
Optional OpenProject Comment
```

Core rule:

> OpenProject owns project context. Neo4j owns structural code relationships. Weaviate owns semantic retrieval. PostgreSQL owns operational state.

---

## 5. Folder Structure

```text
coding-agent-mvp/
├── README.md
├── AGENTS.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── architecture.md
│   ├── mvp-scope.md
│   ├── context-builder.md
│   ├── code-graph.md
│   ├── weaviate-schema.md
│   ├── openproject-integration.md
│   └── agent-loop.md
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── tests/
│   └── src/
│       └── coding_agent/
│           ├── main.py
│           ├── config.py
│           ├── cli.py
│           │
│           ├── api/
│           │   └── routes/
│           │       ├── health.py
│           │       ├── repositories.py
│           │       ├── indexing.py
│           │       ├── context.py
│           │       └── agent_runs.py
│           │
│           ├── integrations/
│           │   └── openproject/
│           │       ├── client.py
│           │       ├── schemas.py
│           │       ├── mapper.py
│           │       └── service.py
│           │
│           ├── repositories/
│           │   ├── models.py
│           │   ├── repository_store.py
│           │   ├── git_service.py
│           │   └── workspace_service.py
│           │
│           ├── indexer/
│           │   ├── repository_indexer.py
│           │   ├── language_detector.py
│           │   ├── chunker.py
│           │   └── python/
│           │       ├── ast_parser.py
│           │       ├── symbol_extractor.py
│           │       ├── call_graph_extractor.py
│           │       ├── import_graph_extractor.py
│           │       └── test_extractor.py
│           │
│           ├── graph/
│           │   ├── neo4j_client.py
│           │   ├── schema.py
│           │   ├── writer.py
│           │   ├── queries.py
│           │   └── traversal.py
│           │
│           ├── vector/
│           │   ├── weaviate_client.py
│           │   ├── schema.py
│           │   ├── writer.py
│           │   ├── search.py
│           │   └── embeddings.py
│           │
│           ├── retrieval/
│           │   ├── keyword_search.py
│           │   ├── graph_retriever.py
│           │   ├── vector_retriever.py
│           │   ├── hybrid_retriever.py
│           │   └── reranker.py
│           │
│           ├── context/
│           │   ├── models.py
│           │   ├── context_builder.py
│           │   ├── token_budget.py
│           │   └── formatter.py
│           │
│           ├── agent/
│           │   ├── loop.py
│           │   ├── state.py
│           │   ├── planner.py
│           │   ├── coder.py
│           │   ├── reviewer.py
│           │   └── run_service.py
│           │
│           ├── tools/
│           │   ├── base.py
│           │   ├── registry.py
│           │   ├── file_tools.py
│           │   ├── graph_tools.py
│           │   ├── vector_tools.py
│           │   ├── openproject_tools.py
│           │   ├── edit_tools.py
│           │   └── test_tools.py
│           │
│           ├── execution/
│           │   ├── command_runner.py
│           │   ├── test_runner.py
│           │   ├── patch_service.py
│           │   └── diff_service.py
│           │
│           ├── llm/
│           │   ├── provider.py
│           │   ├── llama_cpp_provider.py
│           │   ├── prompts.py
│           │   └── structured_output.py
│           │
│           └── storage/
│               ├── db.py
│               ├── base.py
│               └── models.py
│
├── prompts/
│   ├── system.md
│   ├── planner.md
│   ├── coder.md
│   ├── reviewer.md
│   └── context_summary.md
│
├── scripts/
│   ├── register_repo.py
│   ├── index_repo.py
│   ├── build_context.py
│   ├── run_agent.py
│   └── inspect_graph.py
│
└── sandbox/
    ├── Dockerfile.python
    └── run.sh
```

---

## 6. Core Data Ownership

| Data | System of Record | Reason |
|---|---|---|
| Epic / story / task | OpenProject | Avoid rebuilding project management |
| Code relationships | Neo4j | Best fit for traversal |
| Semantic code chunks | Weaviate | Best fit for vector retrieval |
| Agent run history | PostgreSQL | Operational transactional data |
| Patches and diffs | PostgreSQL or filesystem/object storage | Generated artifacts |
| Repository files | Git workspace | Source of truth |
| Test results | PostgreSQL | Agent execution evidence |

---

## 7. OpenProject Integration

### 7.1 MVP Responsibility

The agent should read work packages from OpenProject and convert them into context.

MVP tools:

```python
get_work_package(work_package_id: str) -> WorkItemContext
get_related_work_packages(work_package_id: str) -> list[WorkItemContext]
add_agent_comment(work_package_id: str, comment: str) -> None
```

### 7.2 Work Package Mapping

OpenProject work packages should be mapped like this:

```text
OpenProject Epic      → WorkItemContext(type="epic")
OpenProject Feature   → WorkItemContext(type="feature")
OpenProject UserStory → WorkItemContext(type="story")
OpenProject Task      → WorkItemContext(type="task")
OpenProject Bug       → WorkItemContext(type="bug")
```

Acceptance criteria may come from:

- Work package description
- Custom field
- Checklist text
- Linked child work packages

For MVP, simple parsing from description is acceptable.

---

## 8. Neo4j Code Graph

### 8.1 MVP Node Types

```text
Repository
File
Class
Function
Method
Test
APIEndpoint
WorkPackage
```

Optional lightweight node:

```text
VariableSummary
```

Do not build full variable-level data flow in MVP.

---

### 8.2 MVP Edge Types

```text
(:Repository)-[:CONTAINS]->(:File)
(:File)-[:DEFINES]->(:Class)
(:File)-[:DEFINES]->(:Function)
(:Class)-[:DEFINES]->(:Method)
(:Function)-[:CALLS]->(:Function)
(:Method)-[:CALLS]->(:Function)
(:File)-[:IMPORTS]->(:File)
(:Test)-[:TESTS]->(:Function)
(:WorkPackage)-[:RELATED_TO]->(:File)
(:WorkPackage)-[:RELATED_TO]->(:Function)
```

Later edge types:

```text
READS
WRITES
PASSES_AS_ARGUMENT
RETURNS
VALIDATES
PERSISTS_TO
```

---

### 8.3 Neo4j Constraints

Create constraints:

```cypher
CREATE CONSTRAINT repository_id_unique IF NOT EXISTS
FOR (r:Repository) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT file_unique IF NOT EXISTS
FOR (f:File) REQUIRE (f.repository_id, f.path, f.commit_sha) IS UNIQUE;

CREATE CONSTRAINT function_unique IF NOT EXISTS
FOR (fn:Function) REQUIRE (fn.repository_id, fn.qualified_name, fn.file_path, fn.start_line, fn.commit_sha) IS UNIQUE;

CREATE CONSTRAINT work_package_unique IF NOT EXISTS
FOR (wp:WorkPackage) REQUIRE wp.external_id IS UNIQUE;
```

---

### 8.4 Graph Traversal Examples

Find function callers:

```cypher
MATCH (caller)-[:CALLS]->(target:Function {qualified_name: $qualified_name})
RETURN caller, target
LIMIT 50;
```

Find function callees:

```cypher
MATCH (source:Function {qualified_name: $qualified_name})-[:CALLS]->(callee)
RETURN source, callee
LIMIT 50;
```

Find files related to a work package:

```cypher
MATCH (wp:WorkPackage {external_id: $work_package_id})-[:RELATED_TO]->(n)
RETURN n
LIMIT 100;
```

Find tests related to a function:

```cypher
MATCH (test:Test)-[:TESTS]->(fn:Function {qualified_name: $qualified_name})
RETURN test
LIMIT 50;
```

---

## 9. Weaviate Vector Schema

### 9.1 MVP Collections

Use these collections:

```text
CodeChunk
FunctionSummary
FileSummary
WorkPackageSummary
AgentRunSummary
```

---

### 9.2 CodeChunk Properties

```json
{
  "repository_id": "string",
  "commit_sha": "string",
  "file_path": "string",
  "language": "string",
  "symbol_name": "string",
  "node_type": "string",
  "start_line": "int",
  "end_line": "int",
  "content": "text",
  "summary": "text"
}
```

---

### 9.3 Vector Search Use Cases

The vector retriever should support:

```text
search_code_by_task_description(task_description)
search_similar_functions(function_summary)
search_similar_work_packages(work_package_description)
search_previous_agent_runs(task_description)
```

---

## 10. PostgreSQL MVP Tables

Only keep operational tables in PostgreSQL.

```text
repositories
agent_runs
tool_calls
patches
test_runs
indexing_jobs
workspace_sessions
openproject_mappings
```

### 10.1 repositories

```sql
CREATE TABLE repositories (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    remote_url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### 10.2 agent_runs

```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id),
    openproject_work_package_id TEXT NOT NULL,
    status TEXT NOT NULL,
    base_commit_sha TEXT,
    working_branch TEXT,
    context_package_json JSONB,
    final_summary TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    completed_at TIMESTAMP
);
```

### 10.3 tool_calls

```sql
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY,
    agent_run_id UUID NOT NULL REFERENCES agent_runs(id),
    tool_name TEXT NOT NULL,
    input_json JSONB NOT NULL,
    output_json JSONB,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    completed_at TIMESTAMP
);
```

### 10.4 patches

```sql
CREATE TABLE patches (
    id UUID PRIMARY KEY,
    agent_run_id UUID NOT NULL REFERENCES agent_runs(id),
    diff_text TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### 10.5 test_runs

```sql
CREATE TABLE test_runs (
    id UUID PRIMARY KEY,
    agent_run_id UUID NOT NULL REFERENCES agent_runs(id),
    command TEXT NOT NULL,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

---

## 11. Repository Indexing

### 11.1 MVP Indexing Flow

```text
1. Clone or open repository.
2. Detect language by file extension.
3. For Python files:
   - parse AST
   - extract classes
   - extract functions
   - extract methods
   - extract imports
   - extract simple call expressions
   - extract pytest test functions
4. Write graph nodes and edges to Neo4j.
5. Chunk code into function/file chunks.
6. Generate summaries if needed.
7. Store chunks in Weaviate.
8. Store indexing job result in PostgreSQL.
```

---

### 11.2 Python MVP Extraction

Extract:

```text
Module/file path
Class names
Function names
Method names
Function parameters
Docstrings
Imports
Function calls
Pytest test functions
FastAPI route decorators, if present
```

Do not try to perfectly resolve every dynamic call.

Each graph edge should have confidence:

```text
HIGH   - directly resolved local function/class/import
MEDIUM - likely resolved from imported symbol
LOW    - unresolved name or dynamic call
```

---

## 12. Context Builder

The `ContextBuilder` is the core of the MVP.

### 12.1 Input

```python
class ContextBuildRequest(BaseModel):
    repository_id: str
    openproject_work_package_id: str
    token_budget: int = 24000
```

---

### 12.2 Output

```python
class ContextPackage(BaseModel):
    work_item: WorkItemContext
    related_work_items: list[WorkItemContext]
    keyword_matches: list[CodeReference]
    vector_matches: list[CodeReference]
    graph_matches: list[CodeReference]
    selected_files: list[SelectedFileContext]
    selected_functions: list[SelectedFunctionContext]
    related_tests: list[TestReference]
    graph_summary: str
    implementation_hints: list[str]
    risks: list[str]
```

---

### 12.3 Algorithm

```text
1. Fetch OpenProject work package.
2. Fetch parent/child/related work packages.
3. Extract keywords from title, description, acceptance criteria.
4. Run keyword search over repository files.
5. Run vector search over Weaviate CodeChunk and FunctionSummary.
6. Convert top results into Neo4j node IDs where possible.
7. Expand graph around top functions/files:
   - callers depth 1
   - callees depth 1
   - imports depth 1
   - related tests
8. Merge and deduplicate candidates.
9. Rank by:
   - exact keyword match
   - vector similarity
   - graph distance
   - test relationship
   - work package relationship
10. Select files/functions under token budget.
11. Summarize graph neighborhood.
12. Return ContextPackage.
```

---

### 12.4 Token Budget

Default allocation:

```text
OpenProject work item context: 15%
Related work items: 5%
Relevant source code: 45%
Relevant tests: 15%
Graph summary: 10%
Implementation hints and risks: 10%
```

---

## 13. Agent Loop

### 13.1 MVP Agent Flow

```text
1. User runs agent from CLI with repository ID and OpenProject work package ID.
2. Agent builds context package.
3. Planner creates short implementation plan.
4. Coder generates patch.
5. Patch is applied to workspace.
6. Tests are run.
7. If tests fail, agent can attempt limited repair.
8. Final diff and summary are produced.
9. Agent run is stored in PostgreSQL.
10. Optional comment is posted to OpenProject.
```

---

### 13.2 Strict Limits

```text
Max planning attempts: 2
Max patch attempts: 3
Max test-fix loops: 3
Max tool calls: 50
Max files changed: 8
Max command timeout: 300 seconds
```

---

### 13.3 Final Output

Every run must produce:

```text
Task summary
Context used
Files changed
Patch/diff
Tests run
Test result
Known risks
Suggested next step
```

---

## 14. Agent Tools

### 14.1 OpenProject Tools

```text
get_work_package
get_related_work_packages
add_agent_comment
```

### 14.2 Repository Tools

```text
list_files
read_file
search_code
get_git_diff
```

### 14.3 Graph Tools

```text
get_callers
get_callees
get_import_neighbors
get_related_tests
get_work_package_code_links
```

### 14.4 Vector Tools

```text
semantic_code_search
semantic_work_package_search
semantic_previous_run_search
```

### 14.5 Edit Tools

```text
apply_patch
write_file
show_diff
```

### 14.6 Execution Tools

```text
run_tests
run_linter
run_command_limited
```

For MVP, all tools are backend-internal. The LLM does not get raw unrestricted shell access.

---

## 15. CLI-First Workflow

Since frontend is skipped, the CLI should support:

```bash
python -m coding_agent.cli register-repo \
  --name school-portal \
  --url git@gitlab.local:school/portal.git

python -m coding_agent.cli index-repo \
  --repo school-portal

python -m coding_agent.cli build-context \
  --repo school-portal \
  --work-package 1234

python -m coding_agent.cli run-agent \
  --repo school-portal \
  --work-package 1234

python -m coding_agent.cli show-run \
  --run-id <uuid>
```

This is enough for the MVP.

---

## 16. Environment Variables

```env
# Backend
DATABASE_URL=postgresql+psycopg://agent:agent@localhost:5432/coding_agent

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Weaviate
WEAVIATE_URL=http://localhost:8081
WEAVIATE_API_KEY=

# OpenProject
OPENPROJECT_BASE_URL=http://localhost:8082
OPENPROJECT_API_TOKEN=your-token

# llama.cpp
LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
LLAMA_CPP_MODEL_NAME=local-coding-model
LLM_CONTEXT_WINDOW=32768
LLM_MAX_OUTPUT_TOKENS=4096
LLM_TEMPERATURE=0.1

# Agent Limits
MAX_TOOL_CALLS=50
MAX_PATCH_ATTEMPTS=3
MAX_TEST_FIX_LOOPS=3
MAX_FILES_CHANGED=8
```

---

## 17. Docker Compose MVP Services

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: coding_agent
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: agent
    ports:
      - "5432:5432"

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/password
    ports:
      - "7474:7474"
      - "7687:7687"

  weaviate:
    image: semitechnologies/weaviate:latest
    ports:
      - "8081:8080"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"
      PERSISTENCE_DATA_PATH: /var/lib/weaviate
      DEFAULT_VECTORIZER_MODULE: none

  api:
    build: ./backend
    env_file: .env
    depends_on:
      - postgres
      - neo4j
      - weaviate
```

llama.cpp can be started separately, especially if GPU configuration is needed.

---

## 18. Minimal API Endpoints

Even without a frontend, expose simple APIs:

```text
POST /repositories/register
POST /repositories/{id}/index
POST /context/build
POST /agent-runs
GET  /agent-runs/{id}
GET  /agent-runs/{id}/diff
GET  /health
```

The CLI can call these APIs or call services directly.

---

## 19. Security Rules for MVP

Do not overbuild security, but keep the essential protections:

```text
1. Do not pass .env files or secrets to the LLM.
2. Redact secrets from command output and test logs.
3. Do not allow arbitrary destructive shell commands.
4. Run commands only inside repository workspace.
5. Store every tool call in PostgreSQL.
6. Never auto-push code in MVP.
7. Produce a diff for human review.
```

Blocked commands by default:

```text
rm -rf /
curl | sh
wget | sh
sudo
chmod -R 777
ssh private key access
Docker socket access
```

---

## 20. MVP Implementation Phases

### Phase 1: Infrastructure

- FastAPI backend
- PostgreSQL connection
- Neo4j connection
- Weaviate connection
- llama.cpp provider
- CLI skeleton

### Phase 2: OpenProject Context

- Read work package
- Read parent/child/related work packages
- Convert to `WorkItemContext`
- Optional comment update

### Phase 3: Repository Indexing

- Register repository
- Clone/open repository
- Parse Python files
- Extract files/classes/functions/imports/calls/tests
- Write graph to Neo4j
- Write chunks to Weaviate

### Phase 4: Context Builder

- Keyword search
- Vector search
- Graph expansion
- Candidate ranking
- Context package formatting

### Phase 5: Agent Loop

- Planner
- Patch generator
- Patch applier
- Test runner
- Repair loop
- Final summary

### Phase 6: Hardening

- Secret redaction
- Better command restrictions
- Better graph confidence
- Incremental indexing
- Better summaries

---

## 21. Success Criteria for MVP

The MVP is successful when:

```text
1. A work package can be read from OpenProject.
2. A repository can be indexed into Neo4j and Weaviate.
3. The context builder can produce useful context for a work package.
4. The agent can make a small code change using llama.cpp.
5. The agent can run tests and show the result.
6. The final diff is human-reviewable.
7. The run is stored in PostgreSQL.
```

---

## 22. Core Principle

Do not simplify the wrong thing.

It is okay to skip:

```text
Frontend
User management
Multi-agent workflow
MR automation
Complex permissions
```

Do not skip:

```text
OpenProject context
Neo4j graph retrieval
Weaviate semantic retrieval
Context builder
Patch-based editing
Test execution
Run history
```

The MVP should prove the core idea:

> A coding agent becomes more useful when it understands both product context and code dependency context before editing files.
