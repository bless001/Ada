from __future__ import annotations

from pydantic import BaseModel

from planning_agent_core.domain.enums import ProjectStatus
from planning_agent_core.domain.repositories import RepositoryBinding


class Project(BaseModel):
    project_key: str
    name: str
    status: ProjectStatus = ProjectStatus.DRAFT
    repository: RepositoryBinding | None = None
