from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planning_agent_core.domain.enums import PlanningSessionStatus
from planning_agent_core.domain.events import EventEnvelope
from planning_agent_core.models import ExternalArtifact, PlanningSession
from planning_agent_core.ports.event_inbox import EventInboxPort


class OrchestrationAction(StrEnum):
    IGNORED = "ignored"
    UNMAPPED_PROJECT = "unmapped_project"
    CONTEXT_SYNC_ONLY = "context_sync_only"
    NO_WAITING_SESSION = "no_waiting_session"
    RESUME_PLANNING = "resume_planning"


@dataclass(frozen=True)
class OrchestrationResult:
    event_id: str
    action: OrchestrationAction
    reason: str
    project_id: UUID | None = None
    planning_session_id: UUID | None = None
    thread_id: str | None = None
    workflow_result: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "action": self.action.value,
            "reason": self.reason,
            "project_id": str(self.project_id) if self.project_id else None,
            "planning_session_id": (
                str(self.planning_session_id) if self.planning_session_id else None
            ),
            "thread_id": self.thread_id,
            "workflow_result": self.workflow_result,
        }


class PlanningRunnerPort(Protocol):
    async def run(self, session_id: UUID) -> dict[str, Any]:
        ...


class ProjectEventOrchestrator:
    def __init__(
        self,
        *,
        db: AsyncSession,
        event_inbox: EventInboxPort,
        planning_runner: PlanningRunnerPort,
    ) -> None:
        self.db = db
        self.event_inbox = event_inbox
        self.planning_runner = planning_runner

    async def handle_persisted_event(self, event_id: str) -> OrchestrationResult:
        envelope = await self.event_inbox.get(event_id)
        if envelope is None:
            raise KeyError(f"Webhook event not found: {event_id}")

        await self.event_inbox.mark_processing(event_id)
        try:
            result = await self.route_event(event_id=event_id, envelope=envelope)
        except Exception as exc:
            await self.event_inbox.mark_failed(event_id, str(exc))
            raise

        await self.event_inbox.mark_processed(event_id)
        return result

    async def route_event(
        self,
        *,
        event_id: str,
        envelope: EventEnvelope,
    ) -> OrchestrationResult:
        if envelope.source != "openproject":
            return OrchestrationResult(
                event_id=event_id,
                action=OrchestrationAction.IGNORED,
                reason=f"Unsupported event source: {envelope.source}",
            )

        project_id = await self._resolve_project_id(envelope)
        if project_id is None:
            return OrchestrationResult(
                event_id=event_id,
                action=OrchestrationAction.UNMAPPED_PROJECT,
                reason="No local project mapping exists for this OpenProject event",
            )

        if not should_resume_planning(envelope):
            return OrchestrationResult(
                event_id=event_id,
                action=OrchestrationAction.CONTEXT_SYNC_ONLY,
                reason="Event does not currently map to a resumable planning action",
                project_id=project_id,
            )

        session = await self._find_waiting_planning_session(project_id)
        if session is None:
            return OrchestrationResult(
                event_id=event_id,
                action=OrchestrationAction.NO_WAITING_SESSION,
                reason="No waiting planning session exists for the mapped project",
                project_id=project_id,
            )

        workflow_result = await self.planning_runner.run(session.id)
        thread_id = f"planning-session-{session.id}"
        return OrchestrationResult(
            event_id=event_id,
            action=OrchestrationAction.RESUME_PLANNING,
            reason="Resumed the waiting planning workflow for the mapped project",
            project_id=project_id,
            planning_session_id=session.id,
            thread_id=thread_id,
            workflow_result=workflow_result,
        )

    async def _resolve_project_id(self, envelope: EventEnvelope) -> UUID | None:
        project_artifact = await self._find_openproject_artifact(
            artifact_type="project",
            external_id=envelope.external_project_id,
        )
        if project_artifact is not None:
            return project_artifact.project_id

        work_package_artifact = await self._find_openproject_artifact(
            artifact_type="work_package",
            external_id=envelope.external_work_package_id,
        )
        if work_package_artifact is not None:
            return work_package_artifact.project_id

        return None

    async def _find_openproject_artifact(
        self,
        *,
        artifact_type: str,
        external_id: str | None,
    ) -> ExternalArtifact | None:
        if not external_id:
            return None

        return await self.db.scalar(
            select(ExternalArtifact).where(
                ExternalArtifact.system_name == "openproject",
                ExternalArtifact.artifact_type == artifact_type,
                ExternalArtifact.external_id == external_id,
            )
        )

    async def _find_waiting_planning_session(
        self,
        project_id: UUID,
    ) -> PlanningSession | None:
        waiting_statuses = (
            PlanningSessionStatus.INTAKE,
            PlanningSessionStatus.NEEDS_CLARIFICATION,
            PlanningSessionStatus.READY_FOR_PLANNING,
        )
        return await self.db.scalar(
            select(PlanningSession)
            .where(
                PlanningSession.project_id == project_id,
                PlanningSession.status.in_([status.value for status in waiting_statuses]),
            )
            .order_by(PlanningSession.created_at.desc())
            .limit(1)
        )


def should_resume_planning(envelope: EventEnvelope) -> bool:
    event_type = envelope.event_type.lower()
    payload_action = str(envelope.payload.get("action", "")).lower()

    if envelope.external_comment_id:
        return True

    markers = ("comment", "approval", "approve", "resume", "rework")
    return any(marker in event_type or marker in payload_action for marker in markers)
