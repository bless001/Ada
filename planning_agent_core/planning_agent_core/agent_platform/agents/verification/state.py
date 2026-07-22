from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from planning_agent_core.agent_platform.agents.base.contracts import AgentRequest, AgentResult, AgentRunStatus
from planning_agent_core.domain.coding import CodingAttemptResult
from planning_agent_core.schemas import AcceptanceCriterionSpec


class VerificationVerdict(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"


class VerificationFinding(BaseModel):
    severity: str
    code: str
    message: str
    acceptance_criterion_key: str | None = None


class VerificationAgentRequest(AgentRequest):
    agent_type: Literal["verification"] = "verification"
    acceptance_criteria: list[AcceptanceCriterionSpec] = Field(default_factory=list)
    coding_result: CodingAttemptResult | None = None
    repository_diff: str | None = None
    test_evidence: list[str] = Field(default_factory=list)


class VerificationAgentState(BaseModel):
    phase: str = "created"
    verdict: VerificationVerdict | None = None
    findings: list[VerificationFinding] = Field(default_factory=list)


class VerificationAgentResult(AgentResult):
    agent_type: Literal["verification"] = "verification"
    status: AgentRunStatus
    verdict: VerificationVerdict
    findings: list[VerificationFinding] = Field(default_factory=list)
