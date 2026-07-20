from planning_agent_core.llm import StructuredLLM
from planning_agent_core.skills.ambiguity_assessment import AmbiguityAssessmentSkill
from planning_agent_core.skills.planning_decomposition import PlanningDecompositionSkill
from planning_agent_core.skills.registry import SkillRegistry


def build_skill_registry() -> SkillRegistry:
    llm = StructuredLLM()

    registry = SkillRegistry()
    registry.register(AmbiguityAssessmentSkill(llm))
    registry.register(PlanningDecompositionSkill(llm))

    return registry