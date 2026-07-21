from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel


class FakeInput(BaseModel):
    text: str


class FakeOutput(BaseModel):
    normalized: str


def test_builtin_skill_manifests_cover_required_planning_skills():
    from planning_agent_core.skills.manifest import load_builtin_skill_manifests

    manifests = load_builtin_skill_manifests()

    assert {
        "document_ingestion",
        "requirement_extraction",
        "ambiguity_assessment",
        "repository_inspection",
        "implementation_status_classification",
        "planning_decomposition",
        "dependency_validation",
        "openproject_projection",
        "neo4j_projection",
        "weaviate_projection",
        "context_capsule",
    }.issubset(manifests)
    assert manifests["ambiguity_assessment"].status == "implemented"
    assert manifests["planning_decomposition"].status == "implemented"
    assert manifests["requirement_extraction"].status == "planned"


def test_duplicate_skill_manifests_fail_clearly(tmp_path: Path):
    from planning_agent_core.skills.manifest import load_skill_manifests

    payload = {
        "name": "duplicate_skill",
        "version": "1.0.0",
        "description": "duplicate",
        "status": "planned",
    }
    (tmp_path / "a.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate skill manifest"):
        load_skill_manifests(tmp_path)


def test_registry_rejects_skill_registered_against_planned_manifest():
    from planning_agent_core.skills.base import BaseSkill, SkillContext, SkillResult
    from planning_agent_core.skills.manifest import SkillManifest
    from planning_agent_core.skills.registry import SkillRegistry

    class PlannedSkill(BaseSkill):
        name = "planned_skill"
        description = "planned"
        side_effects = False

        def can_handle(self, intent: str, context: SkillContext) -> float:
            return 1.0

        async def run(
            self,
            *,
            intent: str,
            context: SkillContext,
            input_data: dict[str, Any],
        ) -> SkillResult:
            return SkillResult(skill_name=self.name, success=True)

    registry = SkillRegistry(
        {
            "planned_skill": SkillManifest(
                name="planned_skill",
                version="0.1.0",
                description="planned",
                status="planned",
            )
        }
    )

    with pytest.raises(ValueError, match="manifest is planned"):
        registry.register(PlannedSkill())


@pytest.mark.asyncio
async def test_skill_node_adapter_validates_input_and_output():
    from planning_agent_core.skills.base import BaseSkill, SkillContext, SkillResult
    from planning_agent_core.skills.manifest import SkillManifest
    from planning_agent_core.skills.registry import SkillRegistry
    from planning_agent_core.workflow.skill_node import SkillNodeAdapter

    class FakeSkill(BaseSkill):
        name = "fake_skill"
        description = "fake"
        input_schema = FakeInput
        output_schema = FakeOutput

        def can_handle(self, intent: str, context: SkillContext) -> float:
            return 1.0

        async def run(
            self,
            *,
            intent: str,
            context: SkillContext,
            input_data: dict[str, Any],
        ) -> SkillResult:
            return SkillResult(
                skill_name=self.name,
                success=True,
                output={"normalized": input_data["text"].strip().lower()},
            )

    registry = SkillRegistry(
        {
            "fake_skill": SkillManifest(
                name="fake_skill",
                version="1.0.0",
                description="fake",
                input_schema=f"{FakeInput.__module__}.{FakeInput.__qualname__}",
                output_schema=f"{FakeOutput.__module__}.{FakeOutput.__qualname__}",
            )
        }
    )
    registry.register(FakeSkill())

    result = await SkillNodeAdapter(registry).run(
        skill_name="fake_skill",
        intent="normalize",
        context=SkillContext(project_key="demo"),
        input_data={"text": " Hello "},
    )

    assert result.output == {"normalized": "hello"}


def test_agent_registry_references_declared_skill_manifests():
    from planning_agent_core.agents.registry import AgentRegistry
    from planning_agent_core.skills.manifest import load_builtin_skill_manifests
    from planning_agent_core.skills.registry import SkillRegistry

    skill_registry = SkillRegistry(load_builtin_skill_manifests())

    AgentRegistry().validate_against_skills(skill_registry)
