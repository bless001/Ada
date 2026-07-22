from __future__ import annotations

from planning_agent_core.agent_platform.factory import AgentFactory, create_default_agent_factory
from planning_agent_core.agent_platform.orchestration import (
    AgentExecutionRequest,
    AgentFlowOrchestrator,
    AgentFlowResult,
    AgentOrchestrationResult,
    AgentOrchestrator,
    AgentTransitionRequestResolver,
)
from planning_agent_core.agent_platform.runtime import AgentDependencyContainer


class AgentPlatformService:
    """Application-facing entry point for running registered agents through the orchestrator."""

    def __init__(
        self,
        *,
        dependencies: AgentDependencyContainer,
        factory: AgentFactory | None = None,
        orchestrator: AgentOrchestrator | None = None,
    ) -> None:
        self.dependencies = dependencies
        self.factory = factory or create_default_agent_factory(dependencies)
        self.orchestrator = orchestrator or AgentOrchestrator(
            factory=self.factory,
            dependencies=dependencies,
        )

    async def execute(self, request: AgentExecutionRequest) -> AgentOrchestrationResult:
        return await self.orchestrator.run_once(request)

    async def execute_flow(
        self,
        request: AgentExecutionRequest,
        *,
        transition_resolver: AgentTransitionRequestResolver | None = None,
        max_steps: int = 10,
    ) -> AgentFlowResult:
        flow_orchestrator = AgentFlowOrchestrator(
            step_orchestrator=self.orchestrator,
            transition_resolver=transition_resolver,
        )
        return await flow_orchestrator.run(request, max_steps=max_steps)


def create_agent_platform_service(
    dependencies: AgentDependencyContainer | None = None,
) -> AgentPlatformService:
    return AgentPlatformService(dependencies=dependencies or AgentDependencyContainer())
