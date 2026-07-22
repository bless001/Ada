from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from planning_agent_core.domain.enums import (
    ApprovalDecision,
    ApprovalScope,
    RepositoryAccessMode,
)
from planning_agent_core.domain.events import EventEnvelope
from planning_agent_core.domain.repositories import RepositoryBinding
from planning_agent_core.models import (
    AgentJob,
    ApprovalRecord,
    ExternalArtifact,
    Project,
    RepositoryBindingRecord,
    RepositoryRelationshipRecord,
    RepositorySymbolRecord,
    WebhookEvent,
)
from planning_agent_core.persistence.approvals import SqlAlchemyApprovalRecordStore
from planning_agent_core.persistence.openproject_artifacts import (
    SqlAlchemyOpenProjectArtifactStore,
)
from planning_agent_core.persistence.event_inbox import SqlAlchemyEventInbox
from planning_agent_core.persistence.repository_bindings import (
    SqlAlchemyRepositoryBindingStore,
)
from planning_agent_core.persistence.repository_index import SqlAlchemyRepositoryIndexStore
from planning_agent_core.ports.approvals import ApprovalRecordInput
from planning_agent_core.services.repository_analysis_service import RepositoryAnalysisService


POSTGRES_URL_ENV = "PHASE3_POSTGRES_DATABASE_URL"


@pytest.fixture(scope="module")
def postgres_database_url() -> str:
    database_url = os.getenv(POSTGRES_URL_ENV)
    if not database_url:
        pytest.skip(f"Set {POSTGRES_URL_ENV} to run live Postgres Phase 3 integration tests")
    return database_url


@pytest.fixture(scope="module")
def migrated_postgres_url(postgres_database_url: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    package_root = repo_root / "planning_agent_core"
    env = os.environ.copy()
    env["DATABASE_URL"] = postgres_database_url

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=package_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return postgres_database_url


def test_phase3_alembic_upgrade_creates_expected_tables(migrated_postgres_url: str):
    with psycopg.connect(_to_psycopg_url(migrated_postgres_url)) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            assert cur.fetchone()[0] == "0009_repository_index"

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'pm_webhook_events',
                      'agent_jobs',
                      'agent_executions',
                      'approval_records',
                      'openproject_outbound_operations',
                      'openproject_reconciliation_snapshots',
                      'pm_context_snapshots',
                      'repository_bindings',
                      'repository_relationships',
                      'repository_symbols'
                  )
                ORDER BY table_name
                """
            )
            assert [row[0] for row in cur.fetchall()] == [
                "agent_executions",
                "agent_jobs",
                "approval_records",
                "openproject_outbound_operations",
                "openproject_reconciliation_snapshots",
                "pm_context_snapshots",
                "pm_webhook_events",
                "repository_bindings",
                "repository_relationships",
                "repository_symbols",
            ]

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'agent_executions'
                """
            )
            execution_columns = {row[0] for row in cur.fetchall()}
            assert {
                "project_id",
                "agent_name",
                "thread_id",
                "trigger_event_id",
                "attempt_number",
                "status",
                "config_snapshot",
                "error_summary",
            } <= execution_columns


@pytest.mark.asyncio
async def test_phase3_event_inbox_duplicate_delivery_creates_one_job(
    migrated_postgres_url: str,
):
    engine = create_async_engine(migrated_postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    delivery_id = str(uuid4())
    envelope = EventEnvelope(
        source="openproject",
        event_type="work_package.updated",
        external_project_id="12",
        external_work_package_id="34",
        payload={"action": "work_package.updated", "delivery_id": delivery_id},
        headers={"x-request-id": delivery_id},
    )

    try:
        async with session_factory() as session:
            inbox = SqlAlchemyEventInbox(session)
            first = await inbox.persist(envelope)
            second = await inbox.persist(envelope)

            assert first.created is True
            assert second.created is False
            assert second.event_id == first.event_id

            event_count = await session.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.idempotency_key == envelope.idempotency_key
                )
            )
            assert event_count is not None

            jobs = await session.scalars(
                select(AgentJob).where(AgentJob.event_id == event_count.id)
            )
            assert len(list(jobs)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_phase4_openproject_artifact_mapping_upsert_is_idempotent(
    migrated_postgres_url: str,
):
    engine = create_async_engine(migrated_postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    external_id = f"wp-{uuid4()}"

    try:
        async with session_factory() as session:
            project = Project(
                project_key=f"phase4-artifacts-{uuid4()}",
                name="Phase 4 Artifact Mapping",
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            store = SqlAlchemyOpenProjectArtifactStore(session)
            first = await store.upsert_mapping(
                project_id=project.id,
                artifact_type="work_package",
                external_id=external_id,
                external_url=f"/api/v3/work_packages/{external_id}",
                external_payload={"subject": "First"},
            )
            second = await store.upsert_mapping(
                project_id=project.id,
                artifact_type="work_package",
                external_id=external_id,
                external_url=f"/api/v3/work_packages/{external_id}",
                external_payload={"subject": "Second"},
            )

            assert second.artifact_id == first.artifact_id
            artifact = await session.scalar(
                select(ExternalArtifact).where(ExternalArtifact.id == first.artifact_id)
            )
            assert artifact is not None
            assert artifact.external_payload == {"subject": "Second"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_phase4_approval_record_source_decision_is_idempotent(
    migrated_postgres_url: str,
):
    engine = create_async_engine(migrated_postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source_event_id = f"approval-{uuid4()}"

    try:
        async with session_factory() as session:
            project = Project(
                project_key=f"phase4-approvals-{uuid4()}",
                name="Phase 4 Approval Record",
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            store = SqlAlchemyApprovalRecordStore(session)
            first = await store.record(
                ApprovalRecordInput(
                    project_id=project.id,
                    approval_scope=ApprovalScope.PLANNING,
                    decision=ApprovalDecision.APPROVED,
                    source_event_id=source_event_id,
                    payload={"comment": {"raw": "Approved."}},
                )
            )
            second = await store.record(
                ApprovalRecordInput(
                    project_id=project.id,
                    approval_scope=ApprovalScope.PLANNING,
                    decision=ApprovalDecision.APPROVED,
                    source_event_id=source_event_id,
                    payload={"comment": {"raw": "Approved."}},
                )
            )

            assert second.approval_id == first.approval_id
            approvals = await session.scalars(
                select(ApprovalRecord).where(
                    ApprovalRecord.source_event_id == source_event_id
                )
            )
            assert len(list(approvals)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_phase5_repository_binding_upsert_is_idempotent(
    migrated_postgres_url: str,
):
    engine = create_async_engine(migrated_postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            project = Project(
                project_key=f"phase5-repositories-{uuid4()}",
                name="Phase 5 Repository Binding",
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            store = SqlAlchemyRepositoryBindingStore(session)
            first = await store.upsert_binding(
                project_id=project.id,
                binding=RepositoryBinding(
                    repository_key="sample-project",
                    mount_path="/workspace/repositories/sample_project",
                    access_mode=RepositoryAccessMode.READ_ONLY,
                    command_allowlist=("pytest",),
                ),
            )
            second = await store.upsert_binding(
                project_id=project.id,
                binding=RepositoryBinding(
                    repository_key="sample-project",
                    mount_path="/workspace/repositories/sample_project",
                    access_mode=RepositoryAccessMode.READ_WRITE,
                    write_allowlist=("src/**", "tests/**"),
                    command_allowlist=("pytest", "python"),
                ),
            )

            assert first.repository_key == second.repository_key == "sample-project"
            record = await session.scalar(
                select(RepositoryBindingRecord).where(
                    RepositoryBindingRecord.project_id == project.id,
                    RepositoryBindingRecord.repository_key == "sample-project",
                )
            )
            assert record is not None
            assert record.access_mode == RepositoryAccessMode.READ_WRITE.value
            assert record.write_allowlist == ["src/**", "tests/**"]

            loaded = await store.get_binding(
                project_id=project.id,
                repository_key="sample-project",
            )
            assert loaded == second
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_phase5_repository_index_replace_is_queryable(
    migrated_postgres_url: str,
):
    from planning_agent_core.adapters.repository_analysis import PythonAstRepositoryAnalyzer

    repo_root = Path(__file__).resolve().parents[1]
    sample_project = repo_root / "sample_project"
    engine = create_async_engine(migrated_postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            project = Project(
                project_key=f"phase5-index-{uuid4()}",
                name="Phase 5 Repository Index",
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            index = await PythonAstRepositoryAnalyzer(
                [
                    RepositoryBinding(
                        repository_key="sample-project",
                        mount_path=str(sample_project),
                    )
                ]
            ).index_repository(repository_key="sample-project")

            store = SqlAlchemyRepositoryIndexStore(session)
            await store.replace_index(project_id=project.id, index=index)
            await store.replace_index(project_id=project.id, index=index)

            symbols = await store.list_symbols(
                project_id=project.id,
                repository_key="sample-project",
            )
            relationships = await store.list_relationships(
                project_id=project.id,
                repository_key="sample-project",
            )

            assert {symbol.name for symbol in symbols} >= {
                "main.py",
                "calculate_total",
                "checkout",
                "services.payment.PaymentService",
            }
            assert any(
                relationship.relationship_type.value == "calls"
                and relationship.target_name == "calculate_total"
                for relationship in relationships
            )

            symbol_records = await session.scalars(
                select(RepositorySymbolRecord).where(
                    RepositorySymbolRecord.project_id == project.id,
                    RepositorySymbolRecord.repository_key == "sample-project",
                )
            )
            relationship_records = await session.scalars(
                select(RepositoryRelationshipRecord).where(
                    RepositoryRelationshipRecord.project_id == project.id,
                    RepositoryRelationshipRecord.repository_key == "sample-project",
                )
            )
            assert len(list(symbol_records)) == len(index.symbols)
            assert len(list(relationship_records)) == len(index.relationships)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_phase5_repository_analysis_service_binds_and_indexes_sample_project(
    migrated_postgres_url: str,
):
    repo_root = Path(__file__).resolve().parents[1]
    sample_project = repo_root / "sample_project"
    engine = create_async_engine(migrated_postgres_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            project = Project(
                project_key=f"phase5-service-{uuid4()}",
                name="Phase 5 Repository Service",
            )
            session.add(project)
            await session.commit()

            service = RepositoryAnalysisService(
                session,
                repository_mount_root=str(repo_root),
            )
            binding = await service.bind_repository(
                project_key=project.project_key,
                binding=RepositoryBinding(
                    repository_key="sample-project",
                    mount_path=str(sample_project),
                ),
            )
            summary = await service.index_repository(
                project_key=project.project_key,
                repository_key=binding.repository_key,
            )
            symbols = await service.list_symbols(
                project_key=project.project_key,
                repository_key=binding.repository_key,
            )

            assert summary.symbol_count >= 4
            assert summary.relationship_count >= 3
            assert {symbol.name for symbol in symbols} >= {"calculate_total", "checkout"}
            assert any("LSP analysis is unavailable" in warning for warning in summary.warnings)
    finally:
        await engine.dispose()


def _to_psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
