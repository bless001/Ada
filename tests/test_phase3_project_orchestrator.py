from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from planning_agent_core.application.project_orchestrator import (
    OrchestrationAction,
    ProjectEventOrchestrator,
    should_resume_planning,
)
from planning_agent_core.domain.events import EventEnvelope


@dataclass
class FakeInbox:
    event: EventEnvelope | None
    marks: list[tuple[str, str]]

    async def get(self, event_id: str) -> EventEnvelope | None:
        self.marks.append(("get", event_id))
        return self.event

    async def mark_processing(self, event_id: str) -> None:
        self.marks.append(("processing", event_id))

    async def mark_processed(self, event_id: str) -> None:
        self.marks.append(("processed", event_id))

    async def mark_failed(self, event_id: str, message: str) -> None:
        self.marks.append(("failed", event_id))


class FakeDb:
    def __init__(self, *scalar_results: Any):
        self.scalar_results = list(scalar_results)
        self.statements: list[Any] = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_results.pop(0)


class FakeRunner:
    def __init__(self, result: dict[str, Any] | None = None, error: Exception | None = None):
        self.result = result or {"selected_skill": "planning_decomposition"}
        self.error = error
        self.calls: list[Any] = []

    async def run(self, session_id):
        self.calls.append(session_id)
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_project_orchestrator_resumes_waiting_planning_thread_from_event():
    project_id = uuid4()
    session_id = uuid4()
    event = EventEnvelope(
        source="openproject",
        event_type="work_package.comment_created",
        external_project_id="12",
        external_comment_id="99",
        payload={"action": "work_package.comment_created"},
    )
    inbox = FakeInbox(event=event, marks=[])
    db = FakeDb(
        SimpleNamespace(project_id=project_id),
        SimpleNamespace(id=session_id),
    )
    runner = FakeRunner()
    orchestrator = ProjectEventOrchestrator(
        db=db,
        event_inbox=inbox,
        planning_runner=runner,
    )

    result = await orchestrator.handle_persisted_event("event-1")

    assert result.action == OrchestrationAction.RESUME_PLANNING
    assert result.project_id == project_id
    assert result.planning_session_id == session_id
    assert result.thread_id == f"planning-session-{session_id}"
    assert runner.calls == [session_id]
    assert inbox.marks == [
        ("get", "event-1"),
        ("processing", "event-1"),
        ("processed", "event-1"),
    ]


@pytest.mark.asyncio
async def test_project_orchestrator_returns_unmapped_without_runner_call():
    event = EventEnvelope(
        source="openproject",
        event_type="work_package.comment_created",
        external_project_id="12",
        payload={"action": "work_package.comment_created"},
    )
    inbox = FakeInbox(event=event, marks=[])
    db = FakeDb(None, None)
    runner = FakeRunner()
    orchestrator = ProjectEventOrchestrator(
        db=db,
        event_inbox=inbox,
        planning_runner=runner,
    )

    result = await orchestrator.handle_persisted_event("event-1")

    assert result.action == OrchestrationAction.UNMAPPED_PROJECT
    assert runner.calls == []
    assert inbox.marks[-1] == ("processed", "event-1")


@pytest.mark.asyncio
async def test_project_orchestrator_routes_non_resumable_events_to_context_sync_only():
    project_id = uuid4()
    event = EventEnvelope(
        source="openproject",
        event_type="work_package.updated",
        external_project_id="12",
        payload={"action": "work_package.updated"},
    )
    inbox = FakeInbox(event=event, marks=[])
    db = FakeDb(SimpleNamespace(project_id=project_id))
    runner = FakeRunner()
    orchestrator = ProjectEventOrchestrator(
        db=db,
        event_inbox=inbox,
        planning_runner=runner,
    )

    result = await orchestrator.handle_persisted_event("event-1")

    assert result.action == OrchestrationAction.CONTEXT_SYNC_ONLY
    assert result.project_id == project_id
    assert runner.calls == []
    assert len(db.statements) == 1


@pytest.mark.asyncio
async def test_project_orchestrator_marks_failed_when_resume_raises():
    project_id = uuid4()
    session_id = uuid4()
    event = EventEnvelope(
        source="openproject",
        event_type="work_package.comment_created",
        external_project_id="12",
        external_comment_id="99",
        payload={"action": "work_package.comment_created"},
    )
    inbox = FakeInbox(event=event, marks=[])
    db = FakeDb(
        SimpleNamespace(project_id=project_id),
        SimpleNamespace(id=session_id),
    )
    runner = FakeRunner(error=TimeoutError("timed out"))
    orchestrator = ProjectEventOrchestrator(
        db=db,
        event_inbox=inbox,
        planning_runner=runner,
    )

    with pytest.raises(TimeoutError):
        await orchestrator.handle_persisted_event("event-1")

    assert ("failed", "event-1") in inbox.marks
    assert ("processed", "event-1") not in inbox.marks


def test_should_resume_planning_uses_comment_and_feedback_markers():
    assert should_resume_planning(
        EventEnvelope(
            source="openproject",
            event_type="work_package.updated",
            external_comment_id="99",
            payload={},
        )
    )
    assert should_resume_planning(
        EventEnvelope(
            source="openproject",
            event_type="work_package.updated",
            payload={"action": "approval.created"},
        )
    )
    assert not should_resume_planning(
        EventEnvelope(
            source="openproject",
            event_type="work_package.updated",
            payload={"action": "work_package.updated"},
        )
    )
