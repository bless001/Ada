# Phase 5 Repository Analysis Results

Baseline date: 2026-07-22

## Scope Completed

- Added repository binding domain policy with repository key, mount path, access mode, write allowlist, denylist, and command allowlist.
- Added symlink-safe path resolution that rejects absolute paths, Windows drive-relative paths, NUL bytes, `..` traversal, denylisted paths, and resolved paths outside the configured mount.
- Added explicit write checks requiring `READ_WRITE` plus a non-empty matching write allowlist.
- Added executable-name command allowlist validation without shell-command strings.
- Added `LocalRepositoryFilesystem` behind the repository port for safe read path resolution, safe write path resolution, text reads, git snapshot, git diff, and git status.
- Added durable `repository_bindings` storage with Alembic migration `0008_repository_bindings`.
- Added `SqlAlchemyRepositoryBindingStore` with project-scoped idempotent upsert and lookup.
- Added repository code-analysis domain contracts for symbols, relationships, and repository indexes.
- Added `RepositoryAnalysisPort` and `RepositoryIndexStorePort`.
- Added deterministic Python AST fallback repository analyzer that indexes `.py` files through the repository path policy.
- Added optional Tree-sitter extraction wrapper that enriches repository indexing when `tree_sitter` and `tree_sitter_python` are available, while preserving deterministic fallback behavior when they are not installed.
- Added optional LSP definition/reference lookup wrapper around the legacy Python LSP client, guarded by `pyright-langserver` availability.
- Added file, function, class, and import symbols for repository indexing.
- Added defines, imports, resolved in-repository calls, and unresolved-call relationships.
- Added explicit LSP fallback warning when repository indexing runs without LSP.
- Added durable `repository_symbols` and `repository_relationships` tables with Alembic migration `0009_repository_index`.
- Added `SqlAlchemyRepositoryIndexStore` with replace-and-query behavior so repository projections are rebuildable.
- Added Neo4j repository projection for repositories, code symbols, symbol containment, code relationships, and unresolved references.
- Added Weaviate repository context collection support plus deterministic upsert and text search entry points.
- Added repository analysis service orchestration for binding, indexing, persisted index lookup, snapshot retrieval, graph projection, vector upsert, and vector search.
- Added FastAPI repository endpoints for binding repositories, triggering indexing, retrieving snapshots, listing symbols, listing relationships, and searching repository context.
- Added a planning-core repository volume mount in Compose under `/workspace/repositories`.
- Added tests for path traversal rejection, denylist enforcement, write allowlist behavior, command allowlist validation, symlink escape rejection, local repository reads, git fallback status, `sample_project` fixture indexing, ORM contracts, optional Tree-sitter/LSP wrapper fallback, projection ports, API route wiring, and live PostgreSQL persistence.

## Runtime Compatibility Notes

- Repository writes are not enabled in workflows. This phase only adds policy and resolution primitives for future coding-agent work.
- Empty write allowlists deny all writes even when a binding is `READ_WRITE`.
- Denylists apply to reads and writes.
- The Python AST analyzer remains the deterministic source of truth for persisted symbols and relationships.
- Tree-sitter and LSP integrations are optional wrappers. Missing dependencies or a missing `pyright-langserver` produce warnings instead of failing repository indexing.
- Neo4j and Weaviate projections are service-level operations over the persisted repository index and are designed to be rebuildable.

## Verification

Focused Phase 5 command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q tests/test_phase5_repository_analysis.py tests/test_phase1_boundaries.py tests/test_import_smoke.py
```

Result:

```text
18 passed, 1 skipped in 1.59s
```

Full suite command:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
103 passed, 9 skipped, 4 warnings in 1.86s
```

Live PostgreSQL command:

```powershell
docker run --rm -d --name ada-phase5-pg-$PID -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ada_phase5 -p 127.0.0.1::5432 postgres:17-alpine
$env:PHASE3_POSTGRES_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:<port>/ada_phase5"
$env:LANGGRAPH_PERSISTENCE_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:<port>/ada_phase5"
.venv\Scripts\python.exe -m pytest -q tests/test_phase3_postgres_integration.py tests/test_phase3_langgraph_persistence.py::test_langgraph_postgres_checkpoint_survives_recreated_checkpointer
docker rm -f ada-phase5-pg-$PID
```

Result:

```text
8 passed in 4.36s
```

## Phase 5 Status

Phase 5 planned work is complete.

Future hardening candidates:

- Add live Neo4j and Weaviate contract tests once those services are consistently available in CI.
- Add an integration test with real Tree-sitter packages installed.
- Add an integration test with a real `pyright-langserver` lifecycle.
