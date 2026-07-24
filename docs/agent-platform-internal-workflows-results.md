# Agent Platform Internal Workflows Results

## Summary

Planning, Coding, and Verification now execute through independently compiled LangGraph state
machines. The cross-agent orchestrator still sees only the common request/result lifecycle and does
not contain agent-specific nodes or state.

This is an internal extraction. Agent request models, result models, factory registration, API
contracts, durable flow transitions, and high-level routing remain unchanged.

## Graph Boundaries

Planning graph:

```text
extract_requirements
  -> request_clarification -> finalize
  -> resolve_plan -> validate_plan -> finalize
```

Coding graph:

```text
load_task_context
  -> execute_coding_attempt -> finalize
  -> finalize when required execution input is unavailable
```

Verification graph:

```text
load_evidence
  -> inspect_result
  -> inspect_quality_commands
  -> evaluate_acceptance_criteria
  -> review_risk
  -> return_verdict
```

Each graph has its own Pydantic workflow state and compiles to a distinct
`CompiledStateGraph`. No graph contains another agent or calls another agent.

## Dependency Boundary

Nodes receive an `AgentWorkflowRuntime` through LangGraph's typed runtime-context facility. It
contains:

- The concrete agent configuration.
- The protocol-oriented `AgentDependencyContainer`.
- The immutable `AgentExecutionContext`.

Dependencies and execution metadata are not copied into workflow state. Persisted graph state
contains only the agent-specific Pydantic state.

## Checkpoints

Every meaningful node persists the current `PlanningAgentState`, `CodingAgentState`, or
`VerificationAgentState` through the shared `CheckpointStore` interface. Checkpoint identity
continues to include project, workflow, agent type, agent instance, execution, thread, and
checkpoint ID.

The state models now include `workflow_trace`, which records graph node names separately from the
business `phase`. Planning, coding, and verification therefore cannot overwrite one another's
checkpoint namespaces.

If graph execution raises, the orchestrator's structured failure checkpoint includes
`last_workflow_state`. This preserves the most recent completed node instead of replacing all
partial progress with a generic error object.

These are platform application checkpoints. The existing PostgreSQL LangGraph checkpointer remains
available for a future migration to native graph snapshots, interrupts, and node-level replay where
that provides additional value.

## Compatibility

- Agent builders and registry entries are unchanged.
- `Agent.execute()` now validates the specialized request and delegates to its internal workflow.
- Planning still uses requirement extraction, optional legacy plan drafting, and plan validation.
- Coding still delegates the bounded write/test operation to `CodingService`.
- Verification verdict and route semantics remain unchanged.
- Existing synchronous and background durable-flow entry points require no changes.

## Validation

Coverage includes:

- Distinct graph names, graph objects, and node sets for all three agents.
- Planning clarification conditional routing.
- Coding execution and evidence handoff.
- Verification evidence, acceptance-criteria, risk, and verdict phases.
- Independent checkpoint namespaces and persisted node traces.
- Preservation of the last completed workflow state after an exception.
- Existing agent contract, orchestration, durable-flow, and worker behavior.

Commands run:

```powershell
.venv/Scripts/python.exe -m ruff check <changed Python files>
.venv/Scripts/python.exe -m pytest -q tests/test_agent_internal_workflows.py tests/test_agent_platform.py tests/test_agent_platform_flow.py tests/test_agent_flow_persistence.py tests/test_agent_flow_worker.py
.venv/Scripts/python.exe -m pytest -q
```

Results:

- Changed-file Ruff: passed.
- Focused internal-workflow, agent, flow, persistence, and worker tests: 46 passed.
- Full suite with PostgreSQL integrations enabled: 197 passed, 2 skipped, 4 existing warnings.
