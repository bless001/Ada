from __future__ import annotations

from planning_agent_core.agent_platform.agents.planning.config import PlanningAgentConfig


PLANNING_WORKFLOW_STEPS: tuple[str, ...] = (
    "document_ingestion",
    "requirement_extraction",
    "ambiguity_assessment",
    "repository_inspection",
    "implementation_status_classification",
    "planning_decomposition",
    "plan_validation",
    "context_capsule",
    "openproject_projection",
    "neo4j_projection",
    "weaviate_projection",
)


def build_planning_agent_workflow(config: PlanningAgentConfig) -> tuple[str, ...]:
    return tuple(step for step in PLANNING_WORKFLOW_STEPS if step in config.skill_names)
