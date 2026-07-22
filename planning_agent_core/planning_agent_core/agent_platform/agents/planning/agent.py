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
from planning_agent_core.agent_platform.agents.planning.config import PlanningAgentConfig
from planning_agent_core.agent_platform.agents.planning.state import (
    PlanningAgentRequest,
    PlanningAgentResult,
    PlanningAgentState,
)
from planning_agent_core.agent_platform.agents.planning.workflow import build_planning_agent_workflow
from planning_agent_core.agent_platform.config.models import AgentConfig, materialize_agent_config
from planning_agent_core.agent_platform.factory.builders import AgentBuilder
from planning_agent_core.agent_platform.factory.registry import AgentBuilderRegistry
from planning_agent_core.agent_platform.runtime.dependency_container import AgentDependencyContainer
from planning_agent_core.agent_platform.runtime.execution_context import AgentExecutionContext
from planning_agent_core.schemas import ProjectPlanSpec
from planning_agent_core.skills.plan_validation import PlanValidationInput, PlanValidationSkill
from planning_agent_core.skills.requirement_extraction import (
    EvidenceRef,
    NormalizedRequirement,
    RequirementExtractionInput,
    RequirementExtractionSkill,
)


class PlanningAgent(BaseAgent):
    def __init__(self, *, config: PlanningAgentConfig, dependencies: AgentDependencyContainer) -> None:
        self.config = config
        self.dependencies = dependencies
        self.workflow_steps = build_planning_agent_workflow(config)
        self._initialized = False

    @property
    def agent_type(self) -> str:
        return "planning"

    async def initialize(self) -> None:
        self._initialized = True

    async def validate_request(self, request: AgentRequest) -> None:
        typed = PlanningAgentRequest.model_validate(request.model_dump(mode="json"))
        if typed.agent_type != self.agent_type:
            raise AgentValidationError("PlanningAgent only accepts planning requests")
        if not (typed.objective or typed.original_request or typed.plan or typed.session_id):
            raise AgentValidationError("Planning requests require an objective, original request, plan, or session_id")

    async def execute(
        self,
        request: AgentRequest,
        context: AgentExecutionContext,
    ) -> PlanningAgentResult:
        typed = PlanningAgentRequest.model_validate(request.model_dump(mode="json"))
        original_request = typed.original_request or typed.objective
        state = PlanningAgentState(phase="requirement_extraction")
        requirement_result = await RequirementExtractionSkill().run(
            intent="extract requirements",
            context=_skill_context(typed.project_id, str(typed.execution_id)),
            input_data=RequirementExtractionInput(
                original_request=original_request,
                chunks=[chunk.model_dump(mode="json") for chunk in typed.document_chunks],
            ).model_dump(mode="json"),
        )
        state.extracted_requirements = [
            NormalizedRequirement.model_validate(item)
            for item in requirement_result.output.get("requirements", [])
        ]

        if typed.clarification_required:
            state.phase = "waiting_for_clarification"
            state_ref = await self._save_state(context, state)
            return PlanningAgentResult(
                execution_id=typed.execution_id,
                project_id=typed.project_id,
                task_id=typed.task_id,
                status=AgentRunStatus.WAITING,
                summary="Planning is waiting for clarification before decomposition.",
                state=state_ref,
                next_action=AgentNextAction.REQUEST_CLARIFICATION,
                requirements=state.extracted_requirements,
                clarification_questions=["Clarify the requested task scope before planning."],
            )

        plan = typed.plan or await self._legacy_plan_if_available(typed)
        validation = None
        errors: list[AgentError] = []
        next_action = AgentNextAction.REQUEST_APPROVAL if self.config.approval_required else AgentNextAction.RUN_CODING
        status = AgentRunStatus.SUCCEEDED
        summary = "Planning completed."

        if plan is None:
            status = AgentRunStatus.WAITING
            next_action = AgentNextAction.REQUEST_CLARIFICATION
            summary = "Requirements were extracted, but no plan was provided or generated."
        elif self.config.require_plan_validation:
            state.phase = "plan_validation"
            validation_result = await PlanValidationSkill().run(
                intent="validate plan",
                context=_skill_context(typed.project_id, str(typed.execution_id)),
                input_data=PlanValidationInput(plan=plan.model_dump(mode="json")).model_dump(mode="json"),
            )
            validation = PlanValidationSkill.output_schema.model_validate(validation_result.output)  # type: ignore[union-attr]
            if not validation.valid:
                status = AgentRunStatus.BLOCKED
                next_action = AgentNextAction.REQUEST_CLARIFICATION
                summary = "Planning produced an invalid plan."
                errors = [
                    AgentError(
                        category=AgentErrorCategory.VALIDATION_ERROR,
                        message=finding.message,
                        code=finding.code,
                    )
                    for finding in validation.findings
                    if finding.severity == "error"
                ]
        state.phase = "completed" if status == AgentRunStatus.SUCCEEDED else "blocked"
        state.plan = plan
        state.validation = validation
        state_ref = await self._save_state(context, state)
        artifacts = []
        if plan is not None:
            artifacts.append(
                ArtifactReference(
                    artifact_id=f"plan:{typed.execution_id}",
                    artifact_type="plan",
                    uri=f"agent-state://{state_ref.namespace}/{state_ref.key}#plan",
                    title=plan.summary,
                )
            )
        return PlanningAgentResult(
            execution_id=typed.execution_id,
            project_id=typed.project_id,
            task_id=typed.task_id,
            status=status,
            summary=summary,
            output_artifacts=artifacts,
            evidence=[EvidenceRef.model_validate(ref) for ref in requirement_result.source_refs],
            state=state_ref,
            next_action=next_action,
            errors=errors,
            requirements=state.extracted_requirements,
            plan=plan,
            validation=validation,
        )

    async def shutdown(self) -> None:
        self._initialized = False

    async def _legacy_plan_if_available(self, request: PlanningAgentRequest) -> ProjectPlanSpec | None:
        if not self.config.allow_legacy_planning_service or self.dependencies.planning_service is None:
            return None
        if request.session_id is None:
            return None
        version = await self.dependencies.planning_service.draft_plan(request.session_id)
        return ProjectPlanSpec.model_validate(version.plan_json)

    async def _save_state(self, context: AgentExecutionContext, state: PlanningAgentState) -> StateReference:
        checkpoint_id = await self.dependencies.checkpoint_store.save(
            identity=context.checkpoint,
            state=state.model_dump(mode="json"),
        )
        return StateReference(
            namespace=context.checkpoint.agent_type,
            key=context.checkpoint.key,
            checkpoint_id=checkpoint_id,
        )


class PlanningAgentBuilder(AgentBuilder):
    @property
    def agent_type(self) -> str:
        return "planning"

    def build(self, *, config: AgentConfig, dependencies: AgentDependencyContainer) -> BaseAgent:
        return PlanningAgent(
            config=PlanningAgentConfig.model_validate(materialize_agent_config(config)),
            dependencies=dependencies,
        )


def register_planning_agent(registry: AgentBuilderRegistry) -> None:
    registry.register("planning", PlanningAgentBuilder())


def _skill_context(project_key: str, session_id: str):
    from planning_agent_core.skills.base import SkillContext

    return SkillContext(project_key=project_key, session_id=session_id)
