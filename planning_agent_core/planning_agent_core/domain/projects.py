from __future__ import annotations

from pydantic import BaseModel

from planning_agent_core.domain.enums import ProjectStatus, RepositoryAccessMode


class RepositoryBinding(BaseModel):
    repository_key: str
    mount_path: str
    access_mode: RepositoryAccessMode = RepositoryAccessMode.READ_ONLY


class Project(BaseModel):
    project_key: str
    name: str
    status: ProjectStatus = ProjectStatus.DRAFT
    repository: RepositoryBinding | None = None
