from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.services.planning_service import PlanningService
from planning_agent_core.services.provisioning_service import ProvisioningService
from planning_agent_core.workflow.state import PlanningGraphState


def make_nodes(db: AsyncSession):
    planning_service = PlanningService(db)
    provisioning_service = ProvisioningService(db)

    async def load_session(state: PlanningGraphState) -> PlanningGraphState:
        context = await planning_service.load_session_context(state["session_id"])
        return {
            **state,
            **context,
        }

    async def load_document_context(state: PlanningGraphState) -> PlanningGraphState:
        # First version can be simple.
        # Later this loads document chunks + summaries from PostgreSQL.
        return {
            **state,
            "document_chunk_ids": [],
            "chunk_summaries": [],
        }

    async def assess_ambiguity(state: PlanningGraphState) -> PlanningGraphState:
        assessment = await planning_service.assess_ambiguity_for_graph(
            original_request=state["original_request"],
            intake=state["intake"],
            chunk_summaries=state.get("chunk_summaries", []),
        )

        if assessment.questions:
            return {
                **state,
                "ambiguity_status": "needs_clarification",
                "clarification_questions": [
                    q.model_dump(mode="json") for q in assessment.questions
                ],
            }

        return {
            **state,
            "ambiguity_status": "ready_for_planning",
            "clarification_questions": [],
        }

    async def save_clarification_questions(
        state: PlanningGraphState,
    ) -> PlanningGraphState:
        await planning_service.save_questions_from_graph(
            session_id=state["session_id"],
            project_id=state["project_id"],
            questions=state["clarification_questions"],
        )
        return state

    async def draft_plan(state: PlanningGraphState) -> PlanningGraphState:
        plan = await planning_service.generate_plan_for_graph(
            project_key=state["project_key"],
            original_request=state["original_request"],
            intake=state["intake"],
            chunk_summaries=state.get("chunk_summaries", []),
        )

        return {
            **state,
            "plan": plan.model_dump(mode="json"),
        }

    async def persist_plan(state: PlanningGraphState) -> PlanningGraphState:
        plan_version = await planning_service.persist_plan_from_graph(
            session_id=state["session_id"],
            plan_json=state["plan"],
        )

        return {
            **state,
            "plan_version_id": plan_version.id,
        }

    async def build_context_capsules(state: PlanningGraphState) -> PlanningGraphState:
        await planning_service.build_context_capsules_for_plan(
            plan_version_id=state["plan_version_id"],
        )
        return state

    async def enqueue_provisioning(state: PlanningGraphState) -> PlanningGraphState:
        response = await provisioning_service.enqueue_project_projection(
            state["project_key"]
        )

        return {
            **state,
            "provisioning_job_ids": response.job_ids,
        }

    return {
        "load_session": load_session,
        "load_document_context": load_document_context,
        "assess_ambiguity": assess_ambiguity,
        "save_clarification_questions": save_clarification_questions,
        "draft_plan": draft_plan,
        "persist_plan": persist_plan,
        "build_context_capsules": build_context_capsules,
        "enqueue_provisioning": enqueue_provisioning,
    }