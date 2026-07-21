from __future__ import annotations

from typing import Protocol

from planning_agent_core.domain.events import EventEnvelope


class EventInboxPort(Protocol):
    async def persist(self, envelope: EventEnvelope) -> str:
        ...

    async def get(self, event_id: str) -> EventEnvelope | None:
        ...

    async def mark_processing(self, event_id: str) -> None:
        ...

    async def mark_processed(self, event_id: str) -> None:
        ...

    async def mark_failed(self, event_id: str, message: str) -> None:
        ...
