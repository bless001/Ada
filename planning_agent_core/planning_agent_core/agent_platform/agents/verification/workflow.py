from __future__ import annotations

import re

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from planning_agent_core.agent_platform.agents.base.contracts import (
    AgentError,
    AgentErrorCategory,
    AgentNextAction,
    AgentRunStatus,
    ArtifactReference,
)
from planning_agent_core.agent_platform.agents.base.workflow import (
    AgentWorkflowRuntime,
    persist_workflow_state,
)
from planning_agent_core.agent_platform.agents.verification.config import (
    VerificationAgentConfig,
)
from planning_agent_core.agent_platform.agents.verification.state import (
    VerificationAgentRequest,
    VerificationAgentResult,
    VerificationAgentState,
    VerificationFinding,
    VerificationVerdict,
)
from planning_agent_core.agent_platform.runtime.dependency_container import (
    AgentDependencyContainer,
)
from planning_agent_core.agent_platform.runtime.execution_context import (
    AgentExecutionContext,
)
from planning_agent_core.domain.enums import CodingAttemptStatus


VERIFICATION_WORKFLOW_STEPS: tuple[str, ...] = (
    "load_task_acceptance_criteria",
    "load_coding_result",
    "inspect_repository_diff",
    "run_relevant_tests",
    "evaluate_acceptance_criteria",
    "review_regression_risk",
    "return_verdict",
)


class VerificationWorkflowState(BaseModel):
    request: VerificationAgentRequest
    agent_state: VerificationAgentState = Field(default_factory=VerificationAgentState)
    result: VerificationAgentResult | None = None


class VerificationAgentWorkflow:
    def __init__(
        self,
        *,
        config: VerificationAgentConfig,
        dependencies: AgentDependencyContainer,
    ) -> None:
        self.config = config
        self.dependencies = dependencies
        self.steps = VERIFICATION_WORKFLOW_STEPS
        self.graph = _compile_verification_graph()

    async def run(
        self,
        request: VerificationAgentRequest,
        context: AgentExecutionContext,
    ) -> VerificationAgentResult:
        output = await self.graph.ainvoke(
            VerificationWorkflowState(request=request),
            context=AgentWorkflowRuntime(
                config=self.config,
                dependencies=self.dependencies,
                execution_context=context,
            ),
        )
        state = VerificationWorkflowState.model_validate(output)
        if state.result is None:
            raise RuntimeError("Verification workflow completed without a result")
        return state.result


def build_verification_agent_workflow(
    config: VerificationAgentConfig,
    dependencies: AgentDependencyContainer,
) -> VerificationAgentWorkflow:
    return VerificationAgentWorkflow(config=config, dependencies=dependencies)


def _compile_verification_graph():
    graph = StateGraph(
        VerificationWorkflowState,
        context_schema=AgentWorkflowRuntime,
    )
    graph.add_node("load_evidence", _load_evidence)
    graph.add_node("inspect_result", _inspect_result)
    graph.add_node("inspect_quality_commands", _inspect_quality_commands)
    graph.add_node("evaluate_acceptance_criteria", _evaluate_acceptance_criteria)
    graph.add_node("review_risk", _review_risk)
    graph.add_node("return_verdict", _return_verdict)

    graph.add_edge(START, "load_evidence")
    graph.add_edge("load_evidence", "inspect_result")
    graph.add_edge("inspect_result", "inspect_quality_commands")
    graph.add_edge("inspect_quality_commands", "evaluate_acceptance_criteria")
    graph.add_edge("evaluate_acceptance_criteria", "review_risk")
    graph.add_edge("review_risk", "return_verdict")
    graph.add_edge("return_verdict", END)
    return graph.compile(name="verification-agent-workflow")


async def _load_evidence(
    state: VerificationWorkflowState,
    runtime: Runtime[AgentWorkflowRuntime[VerificationAgentConfig]],
) -> dict:
    agent_state = _advance(state.agent_state, "load_evidence")
    await persist_workflow_state(runtime.context, agent_state)
    return {"agent_state": agent_state}


async def _inspect_result(
    state: VerificationWorkflowState,
    runtime: Runtime[AgentWorkflowRuntime[VerificationAgentConfig]],
) -> dict:
    request = state.request
    coding_result = request.coding_result
    diff = request.repository_diff or (coding_result.final_diff if coding_result else "")
    findings: list[VerificationFinding] = []

    if coding_result is None:
        findings.append(
            VerificationFinding(
                severity="blocked",
                code="missing_coding_result",
                message=("Verification cannot independently inspect a missing coding result."),
            )
        )
    elif coding_result.status == CodingAttemptStatus.BLOCKED:
        findings.append(
            VerificationFinding(
                severity="blocked",
                code="coding_blocked",
                message="Coding result is blocked and cannot be verified as complete.",
            )
        )
    elif coding_result.status != CodingAttemptStatus.SUCCEEDED:
        findings.append(
            VerificationFinding(
                severity="error",
                code="coding_not_successful",
                message="Coding result did not succeed.",
            )
        )

    if runtime.context.config.require_diff_for_pass and not diff.strip():
        findings.append(
            VerificationFinding(
                severity="blocked",
                code="missing_diff",
                message="Verification requires an actual repository diff.",
            )
        )

    agent_state = _with_findings(
        state.agent_state,
        phase="inspect_result",
        findings=findings,
    )
    await persist_workflow_state(runtime.context, agent_state)
    return {"agent_state": agent_state}


async def _inspect_quality_commands(
    state: VerificationWorkflowState,
    runtime: Runtime[AgentWorkflowRuntime[VerificationAgentConfig]],
) -> dict:
    findings: list[VerificationFinding] = []
    coding_result = state.request.coding_result
    if coding_result is not None:
        for record in coding_result.command_results:
            if record.timed_out:
                findings.append(
                    VerificationFinding(
                        severity="error",
                        code="test_timeout",
                        message=(f"Quality command timed out: {' '.join(record.command)}"),
                    )
                )
            elif record.exit_code != 0:
                findings.append(
                    VerificationFinding(
                        severity="error",
                        code="test_failure",
                        message=(f"Quality command failed: {' '.join(record.command)}"),
                    )
                )
    agent_state = _with_findings(
        state.agent_state,
        phase="inspect_quality_commands",
        findings=findings,
    )
    await persist_workflow_state(runtime.context, agent_state)
    return {"agent_state": agent_state}


async def _evaluate_acceptance_criteria(
    state: VerificationWorkflowState,
    runtime: Runtime[AgentWorkflowRuntime[VerificationAgentConfig]],
) -> dict:
    evidence_text = _evidence_text(state.request)
    findings = [
        VerificationFinding(
            severity="error",
            code="acceptance_criterion_unmet",
            message=(
                f"Acceptance criterion is not supported by diff or evidence: {criterion.statement}"
            ),
            acceptance_criterion_key=criterion.key,
        )
        for criterion in state.request.acceptance_criteria
        if not _criterion_supported(criterion.statement, evidence_text)
    ]
    agent_state = _with_findings(
        state.agent_state,
        phase="evaluate_acceptance_criteria",
        findings=findings,
    )
    await persist_workflow_state(runtime.context, agent_state)
    return {"agent_state": agent_state}


async def _review_risk(
    state: VerificationWorkflowState,
    runtime: Runtime[AgentWorkflowRuntime[VerificationAgentConfig]],
) -> dict:
    request = state.request
    coding_result = request.coding_result
    diff = request.repository_diff or (coding_result.final_diff if coding_result else "")
    lowered = f"{diff}\n{_evidence_text(request)}".lower()
    findings = [
        VerificationFinding(
            severity="warning",
            code="warning_term_detected",
            message=f"Verification found warning term: {term}",
        )
        for term in runtime.context.config.warning_terms
        if term.lower() in lowered
    ]
    agent_state = _with_findings(
        state.agent_state,
        phase="review_risk",
        findings=findings,
    )
    await persist_workflow_state(runtime.context, agent_state)
    return {"agent_state": agent_state}


async def _return_verdict(
    state: VerificationWorkflowState,
    runtime: Runtime[AgentWorkflowRuntime[VerificationAgentConfig]],
) -> dict:
    request = state.request
    verdict = _verdict(state.agent_state.findings)
    status = AgentRunStatus.SUCCEEDED
    next_action = AgentNextAction.COMPLETE
    if verdict == VerificationVerdict.CHANGES_REQUESTED:
        status = AgentRunStatus.FAILED
        next_action = AgentNextAction.RUN_CODING
    elif verdict == VerificationVerdict.BLOCKED:
        status = AgentRunStatus.BLOCKED
        next_action = AgentNextAction.ESCALATE

    agent_state = _advance(
        state.agent_state,
        "completed",
        trace_step="return_verdict",
    )
    agent_state.verdict = verdict
    state_ref = await persist_workflow_state(runtime.context, agent_state)
    result = VerificationAgentResult(
        execution_id=request.execution_id,
        project_id=request.project_id,
        task_id=request.task_id,
        status=status,
        summary=f"Verification completed with verdict: {verdict.value}.",
        output_artifacts=[
            ArtifactReference(
                artifact_id=f"verification:{request.execution_id}",
                artifact_type="verification_result",
                uri=(f"agent-state://{state_ref.namespace}/{state_ref.key}#verification"),
                title=f"Verification verdict: {verdict.value}",
            )
        ],
        evidence=(request.coding_result.evidence if request.coding_result else []),
        state=state_ref,
        next_action=next_action,
        errors=[
            AgentError(
                category=(
                    AgentErrorCategory.BLOCKED_ERROR
                    if verdict == VerificationVerdict.BLOCKED
                    else AgentErrorCategory.VALIDATION_ERROR
                ),
                message=finding.message,
                code=finding.code,
            )
            for finding in agent_state.findings
            if finding.severity in {"error", "blocked"}
        ],
        verdict=verdict,
        findings=agent_state.findings,
    )
    return {"agent_state": agent_state, "result": result}


def _with_findings(
    state: VerificationAgentState,
    *,
    phase: str,
    findings: list[VerificationFinding],
) -> VerificationAgentState:
    advanced = _advance(state, phase)
    advanced.findings = [*state.findings, *findings]
    return advanced


def _advance(
    state: VerificationAgentState,
    phase: str,
    *,
    trace_step: str | None = None,
) -> VerificationAgentState:
    return state.model_copy(
        deep=True,
        update={
            "phase": phase,
            "workflow_trace": [
                *state.workflow_trace,
                trace_step or phase,
            ],
        },
    )


def _verdict(findings: list[VerificationFinding]) -> VerificationVerdict:
    severities = {finding.severity for finding in findings}
    if "blocked" in severities:
        return VerificationVerdict.BLOCKED
    if "error" in severities:
        return VerificationVerdict.CHANGES_REQUESTED
    if "warning" in severities:
        return VerificationVerdict.PASSED_WITH_WARNINGS
    return VerificationVerdict.PASSED


def _evidence_text(request: VerificationAgentRequest) -> str:
    parts = list(request.test_evidence)
    if request.repository_diff:
        parts.append(request.repository_diff)
    if request.coding_result is not None:
        parts.append(request.coding_result.final_diff)
        for ref in request.coding_result.evidence:
            parts.append(ref.title or "")
            parts.append(ref.excerpt or "")
        for record in request.coding_result.command_results:
            parts.append(record.stdout)
            parts.append(record.stderr)
    return "\n".join(parts)


def _criterion_supported(statement: str, evidence_text: str) -> bool:
    terms = [term for term in re.findall(r"[a-z0-9]+", statement.lower()) if len(term) > 3]
    if not terms:
        return True
    evidence = evidence_text.lower()
    matched = [term for term in terms if term in evidence]
    return len(matched) >= max(1, min(3, len(terms) // 2))
