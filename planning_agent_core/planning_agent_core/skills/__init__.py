from planning_agent_core.llm import StructuredLLM
from planning_agent_core.skills.ambiguity_assessment import AmbiguityAssessmentSkill
from planning_agent_core.skills.manifest import load_builtin_skill_manifests
from planning_agent_core.skills.planning_decomposition import PlanningDecompositionSkill
from planning_agent_core.skills.registry import SkillRegistry


def build_skill_registry() -> SkillRegistry:
    llm = StructuredLLM()

    registry = SkillRegistry(load_builtin_skill_manifests())
    registry.register(AmbiguityAssessmentSkill(llm))
    registry.register(PlanningDecompositionSkill(llm))
    registry.validate_required_manifests(
        (
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
        )
    )

    return registry
