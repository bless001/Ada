from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from planning_agent_core.db import Base


def now_utc() -> datetime:
    return datetime.utcnow()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    source_type: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class PlanningSession(Base):
    __tablename__ = "planning_sessions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="intake")
    input_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="text")
    original_request: Mapped[str | None] = mapped_column(Text)
    intake_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    planning_session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("planning_sessions.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ClarificationQuestion(Base):
    __tablename__ = "clarification_questions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    planning_session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("planning_sessions.id", ondelete="CASCADE"), nullable=False)
    question_key: Mapped[str] = mapped_column(String(120), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    answer_format: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_number"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    planning_session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("planning_sessions.id", ondelete="SET NULL"))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    summary: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    generated_from: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanNodeIdentity(Base):
    __tablename__ = "plan_node_identities"
    __table_args__ = (UniqueConstraint("project_id", "stable_key"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    stable_key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    current_plan_node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PlanNode(Base):
    __tablename__ = "plan_nodes"
    __table_args__ = (UniqueConstraint("plan_version_id", "node_identity_id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    plan_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False)
    node_identity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_node_identities.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    inherited_context: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    local_constraints: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    assumptions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    expected_outputs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    likely_components: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    priority: Mapped[str | None] = mapped_column(String(40))
    size_estimate: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="proposed")
    node_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PlanNodeRelation(Base):
    __tablename__ = "plan_node_relations"
    __table_args__ = (UniqueConstraint("plan_version_id", "from_node_id", "to_node_id", "relation_type"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    plan_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False)
    from_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_nodes.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExternalArtifact(Base):
    __tablename__ = "external_artifacts"
    __table_args__ = (UniqueConstraint("system_name", "artifact_type", "external_id"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    node_identity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_node_identities.id", ondelete="SET NULL"))
    system_name: Mapped[str] = mapped_column(String(60), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_url: Mapped[str | None] = mapped_column(Text)
    external_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ProvisioningJob(Base):
    __tablename__ = "provisioning_jobs"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ContextCapsule(Base):
    __tablename__ = "context_capsules"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    plan_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_versions.id", ondelete="CASCADE"), nullable=False)
    plan_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("plan_nodes.id", ondelete="CASCADE"), nullable=False)
    capsule_type: Mapped[str] = mapped_column(String(60), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    capsule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    token_estimate: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
