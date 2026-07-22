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

from planning_agent_core.domain.events import EventEnvelope
from planning_agent_core.models import AgentJob, ExternalArtifact, Project, WebhookEvent
from planning_agent_core.persistence.openproject_artifacts import (
    SqlAlchemyOpenProjectArtifactStore,
)
from planning_agent_core.persistence.event_inbox import SqlAlchemyEventInbox


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
            assert cur.fetchone()[0] == "0006_op_reconciliation"

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'pm_webhook_events',
                      'agent_jobs',
                      'agent_executions',
                      'openproject_outbound_operations',
                      'openproject_reconciliation_snapshots',
                      'pm_context_snapshots'
                  )
                ORDER BY table_name
                """
            )
            assert [row[0] for row in cur.fetchall()] == [
                "agent_executions",
                "agent_jobs",
                "openproject_outbound_operations",
                "openproject_reconciliation_snapshots",
                "pm_context_snapshots",
                "pm_webhook_events",
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


def _to_psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
