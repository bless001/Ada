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
    AgentFlowApproval,
    AgentFlowNotFoundError,
    AgentFlowVersionConflictError,
    AgentRouteDecision,
    PersistedAgentFlow,
)
from planning_agent_core.agent_platform.agents.base.errors import AgentValidationError
from planning_agent_core.agent_platform.runtime import AgentDependencyContainer
from planning_agent_core.api.deps import get_db
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


class AgentFlowStartPayload(AgentExecutePayload):
    max_steps: int = Field(default=10, ge=1, le=100)


class AgentFlowResumePayload(BaseModel):
    expected_version: int = Field(ge=1)
    request: AgentExecutionRequestPayload | None = None
    config: SerializeAsAny[AgentConfig] | None = None
    correlation_id: str | None = None
    approval: AgentFlowApproval | None = None
    max_steps: int = Field(default=10, ge=1, le=100)


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
    orchestration_result = await service.execute(
        _build_execution_request(
            request=payload.request,
            config=config,
            workflow_id=payload.workflow_id,
            correlation_id=payload.correlation_id,
        )
    )
    return AgentExecutionResponse(
        persisted_result_id=orchestration_result.persisted.result_id,
        result=orchestration_result.result,
        route=orchestration_result.route,
    )


@router.post("/flows", response_model=PersistedAgentFlow)
async def start_agent_flow(
    payload: AgentFlowStartPayload,
    db: AsyncSession = Depends(get_db),
) -> PersistedAgentFlow:
    config = payload.config or _default_config_for(payload.request.agent_type)
    _validate_config_type(payload.request.agent_type, config)
    service = create_agent_platform_service_for_db(db)
    try:
        return await service.start_flow(
            _build_execution_request(
                request=payload.request,
                config=config,
                workflow_id=payload.workflow_id,
                correlation_id=payload.correlation_id,
            ),
            max_steps=payload.max_steps,
        )
    except Exception as exc:
        raise _flow_http_exception(exc) from exc


@router.get("/flows/{flow_id}", response_model=PersistedAgentFlow)
async def get_agent_flow(
    flow_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PersistedAgentFlow:
    service = create_agent_platform_service_for_db(db)
    try:
        return await service.get_flow(flow_id)
    except Exception as exc:
        raise _flow_http_exception(exc) from exc


@router.post("/flows/{flow_id}/resume", response_model=PersistedAgentFlow)
async def resume_agent_flow(
    flow_id: UUID,
    payload: AgentFlowResumePayload,
    db: AsyncSession = Depends(get_db),
) -> PersistedAgentFlow:
    service = create_agent_platform_service_for_db(db)
    try:
        current = await service.get_flow(flow_id)
        execution = None
        if payload.request is not None:
            config = payload.config or _default_config_for(payload.request.agent_type)
            _validate_config_type(payload.request.agent_type, config)
            execution = _build_execution_request(
                request=payload.request,
                config=config,
                workflow_id=current.workflow_id,
                correlation_id=payload.correlation_id or current.correlation_id,
            )
        return await service.resume_flow(
            flow_id=flow_id,
            expected_version=payload.expected_version,
            request=execution,
            approval=payload.approval,
            max_steps=payload.max_steps,
        )
    except Exception as exc:
        raise _flow_http_exception(exc) from exc


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
        flow_store=SqlAlchemyAgentFlowStore(db),
    )


def _default_config_for(agent_type: str) -> AgentConfig:
    config = load_agent_platform_config().agents.get(agent_type)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent type: {agent_type}")
    return config


def _validate_config_type(agent_type: str, config: AgentConfig) -> None:
    if config.agent_type != agent_type:
        raise HTTPException(
            status_code=422,
            detail="config.agent_type must match request.agent_type",
        )


def _build_execution_request(
    *,
    request: AgentExecutionRequestPayload,
    config: AgentConfig,
    workflow_id: str | None,
    correlation_id: str | None,
) -> AgentExecutionRequest:
    execution_kwargs = {
        "agent_type": request.agent_type,
        "request": request,
        "config": config,
    }
    if workflow_id is not None:
        execution_kwargs["workflow_id"] = workflow_id
    if correlation_id is not None:
        execution_kwargs["correlation_id"] = correlation_id
    return AgentExecutionRequest.model_validate(execution_kwargs)


def _flow_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, AgentFlowNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AgentFlowVersionConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AgentValidationError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(status_code=500, detail=str(exc))
