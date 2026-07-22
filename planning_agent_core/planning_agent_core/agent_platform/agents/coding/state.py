from __future__ import annotations

from pydantic import BaseModel

from planning_agent_core.agent_platform.agents.base.contracts import AgentRequest, AgentResult, AgentRunStatus
from planning_agent_core.domain.coding import CodingAttemptRequest, CodingAttemptResult


class CodingAgentRequest(AgentRequest):
    agent_type: str = "coding"
    coding_attempt: CodingAttemptRequest | None = None
    approved: bool = False


class CodingAgentState(BaseModel):
    phase: str = "created"
    coding_attempt: CodingAttemptRequest | None = None
    result: CodingAttemptResult | None = None


class CodingAgentResult(AgentResult):
    agent_type: str = "coding"
    status: AgentRunStatus
    coding_result: CodingAttemptResult | None = None
