from __future__ import annotations

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
from planning_agent_core.agent_platform.agents.coding.config import CodingAgentConfig
from planning_agent_core.agent_platform.agents.coding.state import CodingAgentRequest, CodingAgentResult, CodingAgentState
from planning_agent_core.agent_platform.agents.coding.workflow import build_coding_agent_workflow
from planning_agent_core.agent_platform.config.models import AgentConfig, materialize_agent_config
from planning_agent_core.agent_platform.factory.builders import AgentBuilder
from planning_agent_core.agent_platform.factory.registry import AgentBuilderRegistry
from planning_agent_core.agent_platform.runtime.dependency_container import AgentDependencyContainer
from planning_agent_core.agent_platform.runtime.execution_context import AgentExecutionContext
from planning_agent_core.domain.enums import CodingAttemptStatus


class CodingAgent(BaseAgent):
    def __init__(self, *, config: CodingAgentConfig, dependencies: AgentDependencyContainer) -> None:
        self.config = config
        self.dependencies = dependencies
        self.workflow_steps = build_coding_agent_workflow(config)
        self._initialized = False

    @property
    def agent_type(self) -> str:
        return "coding"

    async def initialize(self) -> None:
        self._initialized = True

    async def validate_request(self, request: AgentRequest) -> None:
        typed = CodingAgentRequest.model_validate(request.model_dump(mode="json"))
        if typed.agent_type != self.agent_type:
            raise AgentValidationError("CodingAgent only accepts coding requests")
        if not typed.task_id:
            raise AgentValidationError("Coding requests require task_id")
        if typed.coding_attempt is None:
            raise AgentValidationError("Coding requests require a coding_attempt payload")
        if not typed.approved:
            raise AgentValidationError("Coding requests must be approved before execution")

    async def execute(
        self,
        request: AgentRequest,
        context: AgentExecutionContext,
    ) -> CodingAgentResult:
        typed = CodingAgentRequest.model_validate(request.model_dump(mode="json"))
        state = CodingAgentState(phase="running", coding_attempt=typed.coding_attempt)
        errors: list[AgentError] = []
        coding_result = None

        if self.dependencies.coding_service is None:
            state.phase = "blocked"
            state_ref = await self._save_state(context, state)
            return CodingAgentResult(
                execution_id=typed.execution_id,
                project_id=typed.project_id,
                task_id=typed.task_id,
                status=AgentRunStatus.BLOCKED,
                summary="Coding agent is missing CodingService dependency.",
                state=state_ref,
                next_action=AgentNextAction.ESCALATE,
                errors=[
                    AgentError(
                        category=AgentErrorCategory.DEPENDENCY_ERROR,
                        message="CodingService dependency is required for coding execution.",
                        code="missing_coding_service",
                    )
                ],
            )

        try:
            coding_result = await self.dependencies.coding_service.run_explicit_attempt(
                project_key=typed.project_id,
                request=typed.coding_attempt,
            )
        except Exception as exc:
            errors.append(
                AgentError(
                    category=AgentErrorCategory.TOOL_EXECUTION_ERROR,
                    message=str(exc),
                    code="coding_attempt_failed",
                )
            )

        state.result = coding_result
        if coding_result is None:
            state.phase = "failed"
            status = AgentRunStatus.FAILED
            next_action = AgentNextAction.RETRY
            summary = "Coding attempt failed before producing a result."
        elif coding_result.status == CodingAttemptStatus.SUCCEEDED:
            state.phase = "completed"
            status = AgentRunStatus.SUCCEEDED
            next_action = AgentNextAction.RUN_VERIFICATION
            summary = "Coding attempt completed and is ready for verification."
        elif coding_result.status == CodingAttemptStatus.BLOCKED:
            state.phase = "blocked"
            status = AgentRunStatus.BLOCKED
            next_action = AgentNextAction.ESCALATE
            summary = "Coding attempt is blocked by policy or repository state."
        else:
            state.phase = "failed"
            status = AgentRunStatus.FAILED
            next_action = AgentNextAction.RETRY
            summary = "Coding attempt failed quality checks."

        state_ref = await self._save_state(context, state)
        artifacts = []
        evidence = []
        if coding_result is not None:
            artifacts.append(
                ArtifactReference(
                    artifact_id=f"coding-result:{typed.execution_id}",
                    artifact_type="coding_result",
                    uri=f"agent-state://{state_ref.namespace}/{state_ref.key}#coding_result",
                    title=f"Coding result for {typed.task_id}",
                    metadata={"changed_files": coding_result.changed_files},
                )
            )
            evidence = coding_result.evidence
            errors.extend(
                AgentError(
                    category=AgentErrorCategory.TOOL_EXECUTION_ERROR,
                    message=message,
                    code="coding_attempt_error",
                )
                for message in coding_result.errors
            )
        return CodingAgentResult(
            execution_id=typed.execution_id,
            project_id=typed.project_id,
            task_id=typed.task_id,
            status=status,
            summary=summary,
            output_artifacts=artifacts,
            evidence=evidence,
            state=state_ref,
            next_action=next_action,
            errors=errors,
            coding_result=coding_result,
        )

    async def shutdown(self) -> None:
        self._initialized = False

    async def _save_state(self, context: AgentExecutionContext, state: CodingAgentState) -> StateReference:
        checkpoint_id = await self.dependencies.checkpoint_store.save(
            identity=context.checkpoint,
            state=state.model_dump(mode="json"),
        )
        return StateReference(
            namespace=context.checkpoint.agent_type,
            key=context.checkpoint.key,
            checkpoint_id=checkpoint_id,
        )


class CodingAgentBuilder(AgentBuilder):
    @property
    def agent_type(self) -> str:
        return "coding"

    def build(self, *, config: AgentConfig, dependencies: AgentDependencyContainer) -> BaseAgent:
        return CodingAgent(
            config=CodingAgentConfig.model_validate(materialize_agent_config(config)),
            dependencies=dependencies,
        )


def register_coding_agent(registry: AgentBuilderRegistry) -> None:
    registry.register("coding", CodingAgentBuilder())
