from __future__ import annotations

from pydantic import BaseModel, Field

from planning_agent_core.domain.enums import ImplementationStatus, RequirementStatus
from planning_agent_core.domain.evidence import EvidenceRef


class Requirement(BaseModel):
    key: str
    statement: str
    status: RequirementStatus = RequirementStatus.PROPOSED
    implementation_status: ImplementationStatus | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
