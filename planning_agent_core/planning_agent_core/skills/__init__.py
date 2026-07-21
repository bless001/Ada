from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.llm import StructuredLLM
from planning_agent_core.skills.ambiguity_assessment import AmbiguityAssessmentSkill
from planning_agent_core.skills.document_ingestion import DocumentIngestionSkill
from planning_agent_core.skills.manifest import load_builtin_skill_manifests
from planning_agent_core.skills.planning_decomposition import PlanningDecompositionSkill
from planning_agent_core.skills.registry import SkillRegistry


def build_skill_registry(
    *,
    db: AsyncSession | None = None,
    include_database_skills: bool = False,
    llm: StructuredLLM | None = None,
) -> SkillRegistry:
    llm_client = llm or StructuredLLM()

    registry = SkillRegistry(load_builtin_skill_manifests())
    registry.register(AmbiguityAssessmentSkill(llm_client))
    registry.register(PlanningDecompositionSkill(llm_client))

    if include_database_skills:
        if db is None:
            raise ValueError("Database-backed skills require a database session")
        registry.register(DocumentIngestionSkill(db))

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
