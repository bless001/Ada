from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.agent_platform.config import load_agent_platform_config
from planning_agent_core.agent_platform.runtime import AgentDependencyContainer
from planning_agent_core.persistence.agent_platform import (
    SqlAlchemyAgentCheckpointStore,
    SqlAlchemyAgentResultStore,
)
from planning_agent_core.persistence.agent_flows import SqlAlchemyAgentFlowStore
from planning_agent_core.persistence.agent_transition_context import (
    SqlAlchemyAgentTransitionContextStore,
)
from planning_agent_core.services.agent_platform_service import (
    AgentPlatformService,
    create_agent_platform_service,
)
from planning_agent_core.services.agent_transition_resolver import (
    ApplicationAgentTransitionResolver,
)
from planning_agent_core.services.coding_service import CodingService
from planning_agent_core.services.planning_service import PlanningService
from planning_agent_core.services.repository_analysis_service import (
    RepositoryAnalysisService,
)


def create_agent_platform_service_for_db(
    db: AsyncSession,
) -> AgentPlatformService:
    platform_config = load_agent_platform_config()
    checkpoint_store = SqlAlchemyAgentCheckpointStore(db)
    result_store = SqlAlchemyAgentResultStore(db)
    dependencies = AgentDependencyContainer(
        db=db,
        planning_service=PlanningService(db),
        coding_service=CodingService(db),
        repository_service=RepositoryAnalysisService(db),
        checkpoint_store=checkpoint_store,
        result_store=result_store,
    )
    transition_resolver = ApplicationAgentTransitionResolver(
        context_store=SqlAlchemyAgentTransitionContextStore(db),
        config=platform_config,
    )
    return create_agent_platform_service(
        dependencies,
        transition_resolver=transition_resolver,
        flow_store=SqlAlchemyAgentFlowStore(db),
        flow_lease_seconds=platform_config.flow_runtime.lease_seconds,
        flow_recovery_enabled=platform_config.flow_runtime.recovery_enabled,
    )
