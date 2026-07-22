from __future__ import annotations

import re

from planning_agent_core.agent_platform.agents.base.agent import BaseAgent
from planning_agent_core.agent_platform.agents.base.contracts import (
    AgentError,
    AgentErrorCategory,
    AgentNextAction,
    AgentRequest,
    AgentRunStatus,
    ArtifactReference,
    StateReference,
)
from planning_agent_core.agent_platform.agents.base.errors import AgentValidationError
from planning_agent_core.agent_platform.agents.verification.config import VerificationAgentConfig
from planning_agent_core.agent_platform.agents.verification.state import (
    VerificationAgentRequest,
    VerificationAgentResult,
    VerificationAgentState,
    VerificationFinding,
    VerificationVerdict,
)
from planning_agent_core.agent_platform.agents.verification.workflow import build_verification_agent_workflow
from planning_agent_core.agent_platform.config.models import AgentConfig, materialize_agent_config
from planning_agent_core.agent_platform.factory.builders import AgentBuilder
from planning_agent_core.agent_platform.factory.registry import AgentBuilderRegistry
from planning_agent_core.agent_platform.runtime.dependency_container import AgentDependencyContainer
from planning_agent_core.agent_platform.runtime.execution_context import AgentExecutionContext
from planning_agent_core.domain.enums import CodingAttemptStatus


class VerificationAgent(BaseAgent):
    def __init__(self, *, config: VerificationAgentConfig, dependencies: AgentDependencyContainer) -> None:
        self.config = config
        self.dependencies = dependencies
        self.workflow_steps = build_verification_agent_workflow(config)
        self._initialized = False

    @property
    def agent_type(self) -> str:
        return "verification"

    async def initialize(self) -> None:
        self._initialized = True

    async def validate_request(self, request: AgentRequest) -> None:
        typed = VerificationAgentRequest.model_validate(request.model_dump(mode="json"))
        if typed.agent_type != self.agent_type:
            raise AgentValidationError("VerificationAgent only accepts verification requests")
        if not typed.task_id:
            raise AgentValidationError("Verification requests require task_id")
        if typed.coding_result is None and not typed.repository_diff:
            raise AgentValidationError("Verification requires a coding result or repository diff")

    async def execute(
        self,
        request: AgentRequest,
        context: AgentExecutionContext,
    ) -> VerificationAgentResult:
        typed = VerificationAgentRequest.model_validate(request.model_dump(mode="json"))
        findings = _evaluate_request(typed, self.config)
        verdict = _verdict(findings)
        state = VerificationAgentState(phase="completed", verdict=verdict, findings=findings)
        state_ref = await self._save_state(context, state)
        status = AgentRunStatus.SUCCEEDED
        next_action = AgentNextAction.COMPLETE
        if verdict == VerificationVerdict.CHANGES_REQUESTED:
            status = AgentRunStatus.FAILED
            next_action = AgentNextAction.RUN_CODING
        elif verdict == VerificationVerdict.BLOCKED:
            status = AgentRunStatus.BLOCKED
            next_action = AgentNextAction.ESCALATE
        artifacts = [
            ArtifactReference(
                artifact_id=f"verification:{typed.execution_id}",
                artifact_type="verification_result",
                uri=f"agent-state://{state_ref.namespace}/{state_ref.key}#verification",
                title=f"Verification verdict: {verdict.value}",
            )
        ]
        return VerificationAgentResult(
            execution_id=typed.execution_id,
            status=status,
            summary=f"Verification completed with verdict: {verdict.value}.",
            output_artifacts=artifacts,
            evidence=(typed.coding_result.evidence if typed.coding_result else []),
            state=state_ref,
            next_action=next_action,
            errors=[
                AgentError(
                    category=AgentErrorCategory.BLOCKED_ERROR if verdict == VerificationVerdict.BLOCKED else AgentErrorCategory.VALIDATION_ERROR,
                    message=finding.message,
                    code=finding.code,
                )
                for finding in findings
                if finding.severity in {"error", "blocked"}
            ],
            verdict=verdict,
            findings=findings,
        )

    async def shutdown(self) -> None:
        self._initialized = False

    async def _save_state(self, context: AgentExecutionContext, state: VerificationAgentState) -> StateReference:
        checkpoint_id = await self.dependencies.checkpoint_store.save(
            identity=context.checkpoint,
            state=state.model_dump(mode="json"),
        )
        return StateReference(
            namespace=context.checkpoint.agent_type,
            key=context.checkpoint.key,
            checkpoint_id=checkpoint_id,
        )


class VerificationAgentBuilder(AgentBuilder):
    @property
    def agent_type(self) -> str:
        return "verification"

    def build(self, *, config: AgentConfig, dependencies: AgentDependencyContainer) -> BaseAgent:
        return VerificationAgent(
            config=VerificationAgentConfig.model_validate(materialize_agent_config(config)),
            dependencies=dependencies,
        )


def register_verification_agent(registry: AgentBuilderRegistry) -> None:
    registry.register("verification", VerificationAgentBuilder())


def _evaluate_request(
    request: VerificationAgentRequest,
    config: VerificationAgentConfig,
) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    coding_result = request.coding_result
    diff = request.repository_diff or (coding_result.final_diff if coding_result else "")
    evidence_text = _evidence_text(request)

    if coding_result is None:
        findings.append(
            VerificationFinding(
                severity="blocked",
                code="missing_coding_result",
                message="Verification cannot independently inspect a missing coding result.",
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

    if config.require_diff_for_pass and not diff.strip():
        findings.append(
            VerificationFinding(
                severity="blocked",
                code="missing_diff",
                message="Verification requires an actual repository diff.",
            )
        )

    if coding_result is not None:
        for record in coding_result.command_results:
            if record.timed_out:
                findings.append(
                    VerificationFinding(
                        severity="error",
                        code="test_timeout",
                        message=f"Quality command timed out: {' '.join(record.command)}",
                    )
                )
            elif record.exit_code != 0:
                findings.append(
                    VerificationFinding(
                        severity="error",
                        code="test_failure",
                        message=f"Quality command failed: {' '.join(record.command)}",
                    )
                )

    for criterion in request.acceptance_criteria:
        if not _criterion_supported(criterion.statement, evidence_text):
            findings.append(
                VerificationFinding(
                    severity="error",
                    code="acceptance_criterion_unmet",
                    message=f"Acceptance criterion is not supported by diff or evidence: {criterion.statement}",
                    acceptance_criterion_key=criterion.key,
                )
            )

    lowered = f"{diff}\n{evidence_text}".lower()
    for term in config.warning_terms:
        if term.lower() in lowered:
            findings.append(
                VerificationFinding(
                    severity="warning",
                    code="warning_term_detected",
                    message=f"Verification found warning term: {term}",
                )
            )
    return findings


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
