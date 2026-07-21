from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.api.deps import get_db
from planning_agent_core.application.project_orchestrator import ProjectEventOrchestrator
from planning_agent_core.persistence.event_inbox import SqlAlchemyEventInbox
from planning_agent_core.workflow.runner import PlanningWorkflowRunner

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.post("/{event_id}/orchestrate")
async def orchestrate_event(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    runner = PlanningWorkflowRunner(
        db=db,
        checkpointer=request.app.state.langgraph_checkpointer,
        store=request.app.state.langgraph_store,
    )
    orchestrator = ProjectEventOrchestrator(
        db=db,
        event_inbox=SqlAlchemyEventInbox(db),
        planning_runner=runner,
    )

    try:
        result = await orchestrator.handle_persisted_event(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return result.as_dict()
