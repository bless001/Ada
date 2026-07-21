# Migration Map

This map records where existing code should land as the repository moves toward the target architecture. It is intentionally incremental: wrap first, migrate callers second, remove old paths only after production code no longer references them.

## Target Root

- Keep the distribution and import root `planning_agent_core` for the initial migration.
- Treat `src/` as legacy/reference code until repository analysis and coding-agent capabilities are safely wrapped.
- Keep `infra/agent_trigger` running until webhook intake and worker behavior are proven behind new ports.

## Current To Target Mapping

| Current path | Target location | Migration action |
|---|---|---|
| `planning_agent_core/planning_agent_core/config.py` | `planning_agent_core/planning_agent_core/config/settings.py` | Split settings, add aliases, keep compatibility import while callers migrate. |
| `planning_agent_core/planning_agent_core/db.py` | `planning_agent_core/planning_agent_core/persistence/` | Add unit-of-work and repositories; replace `create_all()` with Alembic. |
| `planning_agent_core/planning_agent_core/models.py` | `planning_agent_core/planning_agent_core/persistence/sqlalchemy_models.py` | Keep current models until migrations exist; then move or re-export. |
| `planning_agent_core/planning_agent_core/schemas.py` | `planning_agent_core/planning_agent_core/api/schemas/` plus `domain/` | Move API schemas separately from domain contracts. |
| `planning_agent_core/planning_agent_core/enums.py` | `planning_agent_core/planning_agent_core/domain/enums.py` | Move with compatibility re-export. |
| `planning_agent_core/planning_agent_core/services/planning_service.py` | `application/services/` and workflows | Keep public behavior; move direct LLM calls behind skills. |
| `planning_agent_core/planning_agent_core/skills/base.py` | `skills/contracts.py` | Add manifest, input/output validation, and side-effect metadata. |
| `planning_agent_core/planning_agent_core/skills/registry.py` | `skills/registry.py` | Extend to manifest loading and duplicate/incompatible manifest checks. |
| `planning_agent_core/planning_agent_core/workflow/` | `workflow/planning/`, `workflow/coding/`, `workflow/verification/` | Keep current planning graph while adding explicit graphs per agent. |
| `planning_agent_core/planning_agent_core/adapters/openproject.py` | `adapters/openproject/` | Merge with trigger client behind an OpenProject port. |
| `planning_agent_core/planning_agent_core/adapters/neo4j_store.py` | `adapters/graph_store/neo4j.py` | Wrap behind graph-store port. |
| `planning_agent_core/planning_agent_core/adapters/weaviate_store.py` | `adapters/vector_store/weaviate.py` | Wrap behind vector-store port. |
| `planning_agent_core/planning_agent_core/llm.py` | `adapters/llm/openai_compatible.py` | Wrap behind a structured-generation port. |
| `infra/agent_trigger/app/storage.py` | `adapters/persistence/webhook_inbox.py` | Wrap first, then migrate to async SQLAlchemy and Alembic. |
| `infra/agent_trigger/app/event_parser.py` | `domain/events.py` plus `application/event_classification.py` | Convert to typed event envelopes and deterministic classification. |
| `infra/agent_trigger/app/openproject_client.py` | `adapters/openproject/` | Merge with async OpenProject adapter. |
| `infra/agent_trigger/app/worker.py` | `workers/event_worker.py` | Queue/lease compatibility remains here; event orchestration now delegates to `planning_agent_core`. |
| `infra/postgres/init/01-agent-schema.sql` | Alembic migrations | Convert schema to migrations; stop relying on init SQL for app-owned tables. |
| `src/parser/` | `adapters/repository_analysis/` | Wrap behind repository-analysis port after path containment policy exists. |
| `src/execution/code_executor.py` | `adapters/command_runner/` | Do not reuse until command allowlist, timeout, output limit, and secret redaction exist. |
| `src/generation/code_generator.py` | Coding skills | Treat as legacy placeholder; replace with typed skill contracts. |
| `src/analysis/code_analyzer.py` | Repository inspection and coding skills | Reuse only through safe repository adapters. |
| `test_ada.py` | `tests/legacy/` or smoke script | Keep as baseline script until pytest suite supersedes it. |

## Removal Rules

- Do not delete legacy code while it is still the only implementation of a capability.
- Do not remove `infra/agent_trigger` until OpenProject webhook persistence, queueing, and worker behavior are covered by tests.
- Do not remove direct service planning paths until the workflow path has parity tests and the API behavior is stable.
- Do not enable coding-agent write behavior until repository write policy and command policy tests pass.
