from __future__ import annotations

from planning_agent_core.agent_platform.factory import AgentFactory, create_default_agent_factory
from planning_agent_core.agent_platform.orchestration import AgentExecutionRequest, AgentOrchestrationResult, AgentOrchestrator
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


def create_agent_platform_service(
    dependencies: AgentDependencyContainer | None = None,
) -> AgentPlatformService:
    return AgentPlatformService(dependencies=dependencies or AgentDependencyContainer())
