from __future__ import annotations

from planning_agent_core.skills.base import BaseSkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill:
        return self._skills[name]

    def all(self) -> list[BaseSkill]:
        return list(self._skills.values())

    def names(self) -> list[str]:
        return list(self._skills.keys())