from __future__ import annotations

from pydantic import Field

from planning_agent_core.agent_platform.config.models import AgentConfig


class VerificationAgentConfig(AgentConfig):
    agent_type: str = "verification"
    checkpoint_namespace: str = "verification"
    approval_required: bool = False
    independent_workspace: bool = True
    require_diff_for_pass: bool = True
    warning_terms: list[str] = Field(default_factory=lambda: ["todo", "fixme", "temporary", "hack"])
