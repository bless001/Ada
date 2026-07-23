# Agent Platform Migration Notes

The platform refactor is additive. The current APIs, service classes, workflow modules, persistence models, adapters, and tests remain available while callers migrate to `planning_agent_core.agent_platform`.

## Migration Map

Current planning runtime:

- Keep `planning_agent_core/workflow/*` as the existing LangGraph planning workflow.
- Wrap it through `PlanningAgent` where a session-based plan is needed via the injected `planning_service`.
- Keep planning skills in `planning_agent_core/skills/*`; agent-specific planning modules compose them rather than copying logic.

Current coding runtime:

- Keep `planning_agent_core/services/coding_service.py` as the bounded write and quality-command executor.
- Use `CodingAgent` as the lifecycle wrapper around one approved `CodingAttemptRequest`.
- Continue persisting attempts through the existing coding-attempt repository and migration.

Current verification behavior:

- Add `VerificationAgent` as an independent contract-first verifier.
- It initially evaluates coding result status, diff presence, command evidence, acceptance criteria support, and warning terms.
- Future work can move richer verification skills behind the same request/result/state contracts.

Current repository analysis:

- Keep concrete Tree-sitter and LSP adapters in `planning_agent_core/adapters/*`.
- Expose platform-facing interfaces through `agent_platform/adapters/git`.
- Continue repository binding and indexing through existing repository services until orchestration endpoints are migrated.

Current infrastructure ports:

- Reuse `planning_agent_core/ports/*` as the source of truth for dependency inversion.
- Re-export platform-facing adapter interfaces under `agent_platform/adapters/*` for discoverability.
- Do not import concrete clients in agent business logic.

## Files Added

- `planning_agent_core/planning_agent_core/agent_platform/agents/base/*`
- `planning_agent_core/planning_agent_core/agent_platform/agents/planning/*`
- `planning_agent_core/planning_agent_core/agent_platform/agents/coding/*`
- `planning_agent_core/planning_agent_core/agent_platform/agents/verification/*`
- `planning_agent_core/planning_agent_core/agent_platform/factory/*`
- `planning_agent_core/planning_agent_core/agent_platform/orchestration/*`
- `planning_agent_core/planning_agent_core/agent_platform/runtime/*`
- `planning_agent_core/planning_agent_core/agent_platform/config/*`
- `planning_agent_core/planning_agent_core/agent_platform/adapters/*`
- `planning_agent_core/planning_agent_core/api/agents.py`
- `planning_agent_core/planning_agent_core/services/agent_platform_service.py`
- `planning_agent_core/planning_agent_core/persistence/agent_platform.py`
- `planning_agent_core/planning_agent_core/persistence/agent_flows.py`
- `planning_agent_core/agent-platform.example.json`
- `planning_agent_core/alembic/versions/0011_agent_platform_persistence.py`
- `planning_agent_core/alembic/versions/0012_agent_platform_flows.py`
- `tests/test_agent_platform.py`
- `tests/test_agent_flow_persistence.py`
- `tests/test_agent_flow_postgres_integration.py`
- `docs/agent-platform-architecture.md`
- `docs/agent-platform-migration-notes.md`

## Files Modified

- `planning_agent_core/planning_agent_core/skills/__init__.py` now lazy-loads skill implementations to avoid environment-dependent imports when individual skill submodules are imported.
- `tests/test_import_smoke.py` now covers the new agent-platform package.
- `docs/refactoring-implementation-plan.md` references this platform milestone.
- `planning_agent_core/planning_agent_core/models.py` now includes platform checkpoint, result, and
  aggregate flow records.
- `planning_agent_core/planning_agent_core/main.py` now includes the agents router.
- `planning_agent_core/planning_agent_core/application/project_orchestrator.py` can route resumable planning events through `AgentPlatformService`.

## Compatibility Risks

- Some callers may have relied on importing skill classes directly from `planning_agent_core.skills`. Current repository tests only import `build_skill_registry` from that package root. If external callers require root-level skill class imports, add explicit lazy accessors or compatibility exports.
- `PlanningAgent` can wrap the legacy planning service, but the existing planning workflow remains the richer production path until all planning skills are wired into the agent workflow.
- `VerificationAgent` is intentionally conservative. Missing diffs or blocked coding attempts route to escalation rather than guessing.
- In-memory checkpointing, results, and flow stores remain available for tests. Database-backed API
  composition injects PostgreSQL implementations for all three.
- `agent_platform_flows` stores serialized typed requests and results for audit/recovery. Deployments
  must apply their normal secret-redaction and retention policy to request metadata and artifacts.
- Agent config currently uses JSON loading. YAML can be added later if a dependency is acceptable.

## Migration Steps

1. Keep existing API routes and services stable.
2. Introduce platform construction in application composition using `create_default_agent_factory(dependencies)`.
3. Wrap current planning requests in `PlanningAgentRequest` and invoke through `AgentOrchestrator.run_once` for new flows.
4. Route persisted OpenProject planning feedback through `ProjectEventOrchestrator` with `agent_platform_service`.
5. Wrap approved coding attempts in `CodingAgentRequest` and invoke through the same orchestrator.
6. Feed coding results and original acceptance criteria into `VerificationAgentRequest`.
7. Persist explicit initial or rework `CodingAttemptRequest` payloads in task context capsules when
   automatic coding transitions are required.
8. Use `AgentPlatformService.start_flow` or `POST /v1/agents/flows` for new durable flows; keep
   `execute` for event-driven single-step compatibility.
9. Resume the same `flow_id` with its current `version`, explicit approval evidence where required,
   and a typed request matching the stored workflow and pending agent.
10. Apply Alembic migration `0012_agent_platform_flows` before enabling the durable endpoints.
11. Move OpenProject, Neo4j, Weaviate, and repository indexing triggers behind orchestrator-driven events.
12. Add richer agent workflows internally without changing factory or orchestrator code.
13. Retire legacy direct workflow entry points only after API and integration tests prove parity.

## Example Flow

```python
from planning_agent_core.agent_platform import AgentDependencyContainer
from planning_agent_core.agent_platform.factory import create_default_agent_factory
from planning_agent_core.agent_platform.orchestration import AgentExecutionRequest
from planning_agent_core.services.agent_platform_service import AgentPlatformService

config = load_agent_platform_config("planning_agent_core/agent-platform.example.json")
dependencies = AgentDependencyContainer(
    coding_service=coding_service,
    planning_service=planning_service,
    graph_repository=neo4j_repository,
    context_store=weaviate_store,
    work_package_gateway=openproject_gateway,
)
factory = create_default_agent_factory(dependencies)
service = AgentPlatformService(
    dependencies=dependencies,
    factory=factory,
    transition_resolver=application_transition_resolver,
    flow_store=flow_store,
)

flow = await service.start_flow(
    AgentExecutionRequest(
        workflow_id="project-demo-task-42",
        agent_type="planning",
        request=planning_request,
        config=config.agents["planning"],
    ),
    max_steps=10,
)
```

The resulting durable flow records every agent step and returns a typed status when it completes
or pauses. Call `resume_flow` with `flow.flow_id`, `flow.version`, approval evidence when required,
and the next typed execution request.
The application transition resolver converts persisted artifacts into the next agent's typed
request. The previous agent never calls the next agent directly.

Database-backed services created by `create_agent_platform_service_for_db` already inject the
production transition resolver. Initial coding uses the `prepared_coding_attempt` context-capsule
key; verification rework uses `prepared_rework_attempt`.

## Fourth-Agent Registration Example

```python
factory.register(
    "security_review",
    SecurityReviewAgentBuilder(dependencies),
)

agent = factory.create(
    agent_type="security_review",
    config=config.agents["security_review"],
)
```

The security review agent can add its own `SecurityReviewAgentRequest`, `SecurityReviewAgentResult`, state model, workflow, skills, and validation rules while preserving the common lifecycle contract.
