from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class SkillContext(BaseModel):
    project_key: str
    session_id: str | None = None
    plan_version_id: str | None = None
    node_identity_id: str | None = None

    # References only. Do not put huge documents here.
    document_ids: list[str] = []
    chunk_ids: list[str] = []

    metadata: dict[str, Any] = {}


class SkillResult(BaseModel):
    skill_name: str
    success: bool
    output: dict[str, Any] = {}
    questions: list[dict[str, Any]] = []
    errors: list[str] = []
    source_refs: list[dict[str, Any]] = []


class BaseSkill(ABC):
    name: str
    description: str
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    side_effects: bool = False

    @abstractmethod
    def can_handle(self, intent: str, context: SkillContext) -> float:
        """
        Return confidence between 0.0 and 1.0.
        """

    @abstractmethod
    async def run(
        self,
        *,
        intent: str,
        context: SkillContext,
        input_data: dict[str, Any],
    ) -> SkillResult:
        """
        Execute the skill.
        """