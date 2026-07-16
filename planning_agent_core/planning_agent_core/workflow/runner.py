from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.workflow.graph import build_planning_graph


class PlanningWorkflowRunner:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(self, session_id: UUID) -> dict:
        graph = build_planning_graph(self.db)

        result = await graph.ainvoke(
            {
                "session_id": session_id,
                "errors": [],
            }
        )

        return result