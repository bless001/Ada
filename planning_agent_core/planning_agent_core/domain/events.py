from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    source: str
    event_type: str
    idempotency_key: str
    occurred_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    external_project_id: str | None = None
    external_work_package_id: str | None = None
    external_comment_id: str | None = None
