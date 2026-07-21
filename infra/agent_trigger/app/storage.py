import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    created: bool


@dataclass(frozen=True)
class JobLease:
    event_id: str
    attempt_count: int


class EventStore:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def insert_event(
        self,
        *,
        source_tool: str,
        event_type: str,
        external_project_id: str | None,
        external_work_package_id: str | None,
        external_comment_id: str | None,
        idempotency_key: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> StoredEvent:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pm_webhook_events (
                        idempotency_key,
                        source_tool,
                        event_type,
                        external_project_id,
                        external_work_package_id,
                        external_comment_id,
                        headers,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id
                    """,
                    (
                        idempotency_key,
                        source_tool,
                        event_type,
                        external_project_id,
                        external_work_package_id,
                        external_comment_id,
                        json.dumps(headers),
                        json.dumps(payload),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        """
                        SELECT id
                        FROM pm_webhook_events
                        WHERE idempotency_key = %s
                        """,
                        (idempotency_key,),
                    )
                    existing = cur.fetchone()
                    if not existing:
                        raise RuntimeError(
                            "Webhook event conflict resolution did not find existing event"
                        )
                    return StoredEvent(event_id=str(existing["id"]), created=False)

                event_id = str(row["id"])

                cur.execute(
                    """
                    INSERT INTO agent_jobs (event_id, job_type, status)
                    VALUES (%s, 'process_pm_event', 'queued')
                    """,
                    (event_id,),
                )

                return StoredEvent(event_id=event_id, created=True)

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM pm_webhook_events WHERE id = %s", (event_id,))
                return cur.fetchone()

    def list_recoverable_event_ids(self, *, limit: int = 50) -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id
                    FROM agent_jobs
                    WHERE status NOT IN ('done', 'dead_letter')
                      AND (
                          (status = 'queued' AND (retry_at IS NULL OR retry_at <= now()))
                          OR (
                              status = 'running'
                              AND (lease_expires_at IS NULL OR lease_expires_at < now())
                          )
                      )
                    ORDER BY COALESCE(retry_at, created_at)
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [str(row["event_id"]) for row in cur.fetchall()]

    def claim_event(
        self,
        event_id: str,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> JobLease | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'running',
                        attempt_count = attempt_count + 1,
                        started_at = now(),
                        finished_at = NULL,
                        lease_owner = %s,
                        lease_expires_at = now() + (%s * interval '1 second'),
                        retry_at = NULL,
                        error_message = NULL
                    WHERE event_id = %s
                      AND status NOT IN ('done', 'dead_letter')
                      AND (
                          status IN ('queued', 'failed')
                          OR (
                              status = 'running'
                              AND (lease_expires_at IS NULL OR lease_expires_at < now())
                          )
                      )
                      AND (retry_at IS NULL OR retry_at <= now())
                    RETURNING attempt_count
                    """,
                    (lease_owner, lease_seconds, event_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None

                attempt_count = int(row["attempt_count"])
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'processing',
                        retry_count = retry_count + 1,
                        retry_at = NULL
                    WHERE id = %s
                    """,
                    (event_id,),
                )
                return JobLease(event_id=event_id, attempt_count=attempt_count)

    def mark_processing(self, event_id: str) -> None:
        self.claim_event(event_id, lease_owner="legacy-worker", lease_seconds=300)

    def mark_processed(self, event_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'processed',
                        processed_at = now(),
                        retry_at = NULL,
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (event_id,),
                )
                cur.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'done',
                        finished_at = now(),
                        error_message = NULL,
                        retry_at = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        last_error = NULL
                    WHERE event_id = %s
                    """,
                    (event_id,),
                )

    def mark_failed(self, event_id: str, error_message: str) -> None:
        self.mark_dead_letter(
            event_id,
            error_message=error_message,
            retry_category="unknown",
            retryable=False,
        )

    def mark_retrying(
        self,
        event_id: str,
        *,
        error_message: str,
        retry_at: datetime,
        retry_category: str,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                last_error = {
                    "message": error_message[:2000],
                    "category": retry_category,
                    "retryable": True,
                    "retry_at": retry_at.isoformat(),
                }
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'pending',
                        retry_at = %s,
                        error_message = %s
                    WHERE id = %s
                    """,
                    (retry_at, error_message[:2000], event_id),
                )
                cur.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'queued',
                        finished_at = now(),
                        error_message = %s,
                        retry_at = %s,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        last_error = %s::jsonb
                    WHERE event_id = %s
                    """,
                    (
                        error_message[:2000],
                        retry_at,
                        json.dumps(last_error),
                        event_id,
                    ),
                )

    def mark_dead_letter(
        self,
        event_id: str,
        *,
        error_message: str,
        retry_category: str,
        retryable: bool,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                last_error = {
                    "message": error_message[:2000],
                    "category": retry_category,
                    "retryable": retryable,
                }
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'dead_letter',
                        processed_at = now(),
                        retry_at = NULL,
                        error_message = %s
                    WHERE id = %s
                    """,
                    (error_message[:2000], event_id),
                )
                cur.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'dead_letter',
                        finished_at = now(),
                        error_message = %s,
                        retry_at = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        last_error = %s::jsonb
                    WHERE event_id = %s
                    """,
                    (
                        error_message[:2000],
                        json.dumps(last_error),
                        event_id,
                    ),
                )

    def insert_context_snapshot(
        self,
        *,
        external_work_package_id: str,
        subject: str | None,
        status_name: str | None,
        type_name: str | None,
        project_name: str | None,
        description_raw: str | None,
        work_package_payload: dict[str, Any] | None,
        activities_payload: dict[str, Any] | None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pm_context_snapshots (
                        external_work_package_id,
                        subject,
                        status_name,
                        type_name,
                        project_name,
                        description_raw,
                        work_package_payload,
                        activities_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    """,
                    (
                        external_work_package_id,
                        subject,
                        status_name,
                        type_name,
                        project_name,
                        description_raw,
                        json.dumps(work_package_payload or {}),
                        json.dumps(activities_payload or {}),
                    ),
                )
