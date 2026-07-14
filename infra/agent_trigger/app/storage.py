import json
from typing import Any

import psycopg
from psycopg.rows import dict_row


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
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> str:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pm_webhook_events (
                        source_tool,
                        event_type,
                        external_project_id,
                        external_work_package_id,
                        external_comment_id,
                        headers,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        source_tool,
                        event_type,
                        external_project_id,
                        external_work_package_id,
                        external_comment_id,
                        json.dumps(headers),
                        json.dumps(payload),
                    ),
                )
                event_id = str(cur.fetchone()["id"])

                cur.execute(
                    """
                    INSERT INTO agent_jobs (event_id, job_type)
                    VALUES (%s, 'process_pm_event')
                    """,
                    (event_id,),
                )

                return event_id

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM pm_webhook_events WHERE id = %s", (event_id,))
                return cur.fetchone()

    def mark_processing(self, event_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'processing',
                        retry_count = retry_count + 1
                    WHERE id = %s
                    """,
                    (event_id,),
                )
                cur.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'running',
                        started_at = now()
                    WHERE event_id = %s
                    """,
                    (event_id,),
                )

    def mark_processed(self, event_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'processed',
                        processed_at = now(),
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
                        error_message = NULL
                    WHERE event_id = %s
                    """,
                    (event_id,),
                )

    def mark_failed(self, event_id: str, error_message: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pm_webhook_events
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (error_message[:2000], event_id),
                )
                cur.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'failed',
                        finished_at = now(),
                        error_message = %s
                    WHERE event_id = %s
                    """,
                    (error_message[:2000], event_id),
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
