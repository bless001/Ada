from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID


class PlanningGraphState(TypedDict, total=False):
    # Required input
    session_id: UUID

    # Loaded from PostgreSQL
    project_id: UUID
    project_key: str
    original_request: str
    input_mode: str
    intake: dict[str, Any]

    # Document context
    document_chunk_ids: list[UUID]
    chunk_summaries: list[dict[str, Any]]

    # Extracted planning knowledge
    requirements: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    assumptions: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    components: list[dict[str, Any]]

    # Ambiguity result
    ambiguity_status: str
    clarification_questions: list[dict[str, Any]]

    # Planning result
    plan: dict[str, Any]
    plan_version_id: UUID

    # Provisioning
    provisioning_job_ids: list[UUID]

    # Error/debug
    errors: list[str]