from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SerializeAsAny
from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.agent_platform.agents.base import AgentResult
from planning_agent_core.agent_platform.agents.coding import CodingAgentRequest
from planning_agent_core.agent_platform.agents.planning import PlanningAgentRequest
from planning_agent_core.agent_platform.agents.verification import VerificationAgentRequest
from planning_agent_core.agent_platform.config import AgentConfig, load_agent_platform_config
from planning_agent_core.agent_platform.orchestration import (
    AgentExecutionRequest,
    AgentRouteDecision,
)
from planning_agent_core.agent_platform.runtime import AgentDependencyContainer
from planning_agent_core.api.deps import get_db
from planning_agent_core.persistence.agent_platform import (
    SqlAlchemyAgentCheckpointStore,
    SqlAlchemyAgentResultStore,
)
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
from planning_agent_core.services.repository_analysis_service import RepositoryAnalysisService

router = APIRouter(prefix="/v1/agents", tags=["agents"])

AgentExecutionRequestPayload = Annotated[
    PlanningAgentRequest | CodingAgentRequest | VerificationAgentRequest,
    Field(discriminator="agent_type"),
]


class AgentExecutePayload(BaseModel):
    request: AgentExecutionRequestPayload
    config: SerializeAsAny[AgentConfig] | None = None
    workflow_id: str | None = None
    correlation_id: str | None = None


class AgentExecutionResponse(BaseModel):
    persisted_result_id: UUID
    result: SerializeAsAny[AgentResult]
    route: AgentRouteDecision


@router.post("/execute", response_model=AgentExecutionResponse)
async def execute_agent(
    payload: AgentExecutePayload,
    db: AsyncSession = Depends(get_db),
) -> AgentExecutionResponse:
    config = payload.config or _default_config_for(payload.request.agent_type)
    if config.agent_type != payload.request.agent_type:
        raise HTTPException(
            status_code=422,
            detail="config.agent_type must match request.agent_type",
        )

    service = create_agent_platform_service_for_db(db)
    execution_kwargs = {
        "agent_type": payload.request.agent_type,
        "request": payload.request,
        "config": config,
    }
    if payload.workflow_id is not None:
        execution_kwargs["workflow_id"] = payload.workflow_id
    if payload.correlation_id is not None:
        execution_kwargs["correlation_id"] = payload.correlation_id

    orchestration_result = await service.execute(
        AgentExecutionRequest.model_validate(execution_kwargs)
    )
    return AgentExecutionResponse(
        persisted_result_id=orchestration_result.persisted.result_id,
        result=orchestration_result.result,
        route=orchestration_result.route,
    )


def create_agent_platform_service_for_db(db: AsyncSession) -> AgentPlatformService:
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
    )


def _default_config_for(agent_type: str) -> AgentConfig:
    config = load_agent_platform_config().agents.get(agent_type)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent type: {agent_type}")
    return config
