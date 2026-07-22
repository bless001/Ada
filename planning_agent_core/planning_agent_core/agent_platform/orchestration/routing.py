from __future__ import annotations

from pydantic import BaseModel

from planning_agent_core.agent_platform.agents.base.contracts import AgentNextAction
from planning_agent_core.agent_platform.orchestration.transitions import AgentTransition


class AgentRouteDecision(BaseModel):
    next_agent_type: str | None
    requires_approval: bool
    escalate: bool
    reason: str


def route_transition(transition: AgentTransition) -> AgentRouteDecision:
    if transition.next_action == AgentNextAction.RUN_PLANNING:
        return AgentRouteDecision(next_agent_type="planning", requires_approval=False, escalate=False, reason=transition.reason)
    if transition.next_action == AgentNextAction.RUN_CODING:
        return AgentRouteDecision(next_agent_type="coding", requires_approval=False, escalate=False, reason=transition.reason)
    if transition.next_action == AgentNextAction.RUN_VERIFICATION:
        return AgentRouteDecision(next_agent_type="verification", requires_approval=False, escalate=False, reason=transition.reason)
    if transition.next_action == AgentNextAction.REQUEST_APPROVAL:
        return AgentRouteDecision(next_agent_type=None, requires_approval=True, escalate=False, reason=transition.reason)
    if transition.next_action in {AgentNextAction.ESCALATE, AgentNextAction.REQUEST_CLARIFICATION}:
        return AgentRouteDecision(next_agent_type=None, requires_approval=False, escalate=True, reason=transition.reason)
    return AgentRouteDecision(next_agent_type=None, requires_approval=False, escalate=False, reason=transition.reason)
