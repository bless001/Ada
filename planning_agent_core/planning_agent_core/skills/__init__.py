from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.llm import StructuredLLM
from planning_agent_core.skills.ambiguity_assessment import AmbiguityAssessmentSkill
from planning_agent_core.skills.context_capsule import ContextCapsuleSkill
from planning_agent_core.skills.document_ingestion import DocumentIngestionSkill
from planning_agent_core.skills.implementation_status_classification import (
    ImplementationStatusClassificationSkill,
)
from planning_agent_core.skills.manifest import load_builtin_skill_manifests
from planning_agent_core.skills.neo4j_projection import Neo4jProjectionSkill
from planning_agent_core.skills.openproject_projection import OpenProjectProjectionSkill
from planning_agent_core.skills.plan_validation import PlanValidationSkill
from planning_agent_core.skills.planning_decomposition import PlanningDecompositionSkill
from planning_agent_core.skills.repository_inspection import RepositoryInspectionSkill
from planning_agent_core.skills.requirement_extraction import RequirementExtractionSkill
from planning_agent_core.skills.registry import SkillRegistry
from planning_agent_core.skills.weaviate_projection import WeaviateProjectionSkill


def build_skill_registry(
    *,
    db: AsyncSession | None = None,
    include_database_skills: bool = False,
    llm: StructuredLLM | None = None,
) -> SkillRegistry:
    llm_client = llm or StructuredLLM()

    registry = SkillRegistry(load_builtin_skill_manifests())
    registry.register(RequirementExtractionSkill())
    registry.register(AmbiguityAssessmentSkill(llm_client))
    registry.register(RepositoryInspectionSkill(db if include_database_skills else None))
    registry.register(ImplementationStatusClassificationSkill())
    registry.register(PlanningDecompositionSkill(llm_client))
    registry.register(PlanValidationSkill())
    registry.register(OpenProjectProjectionSkill())
    registry.register(Neo4jProjectionSkill())
    registry.register(WeaviateProjectionSkill())
    registry.register(ContextCapsuleSkill())

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
