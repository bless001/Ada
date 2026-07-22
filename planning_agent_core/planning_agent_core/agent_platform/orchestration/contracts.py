from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, SerializeAsAny

from planning_agent_core.agent_platform.agents.base.contracts import AgentRequest, AgentResult
from planning_agent_core.agent_platform.config.models import AgentConfig


class AgentExecutionRequest(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_type: str
    request: SerializeAsAny[AgentRequest]
    config: SerializeAsAny[AgentConfig]
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))


class PersistedAgentResult(BaseModel):
    result_id: UUID = Field(default_factory=uuid4)
    result: SerializeAsAny[AgentResult]


@runtime_checkable
class AgentResultStore(Protocol):
    async def persist(self, result: AgentResult) -> PersistedAgentResult:
        ...


class InMemoryAgentResultStore(AgentResultStore):
    def __init__(self) -> None:
        self.results: list[PersistedAgentResult] = []

    async def persist(self, result: AgentResult) -> PersistedAgentResult:
        persisted = PersistedAgentResult(result=result)
        self.results.append(persisted)
        return persisted
