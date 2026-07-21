CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS pm_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key TEXT NOT NULL UNIQUE,
    source_tool TEXT NOT NULL DEFAULT 'openproject',
    event_type TEXT NOT NULL DEFAULT 'unknown',
    external_project_id TEXT,
    external_work_package_id TEXT,
    external_comment_id TEXT,
    headers JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processing_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'processing', 'processed', 'failed', 'dead_letter')),
    processed_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0,
    retry_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_pm_webhook_events_status
    ON pm_webhook_events(processing_status, received_at);

CREATE INDEX IF NOT EXISTS idx_pm_webhook_events_work_package
    ON pm_webhook_events(external_work_package_id);

CREATE INDEX IF NOT EXISTS idx_pm_webhook_events_retry
    ON pm_webhook_events(processing_status, retry_at);

CREATE TABLE IF NOT EXISTS agent_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES pm_webhook_events(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL DEFAULT 'process_pm_event',
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed', 'dead_letter')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    retry_at TIMESTAMPTZ,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    error_message TEXT,
    last_error JSONB
);

CREATE INDEX IF NOT EXISTS idx_agent_jobs_status
    ON agent_jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_agent_jobs_retry
    ON agent_jobs(status, retry_at);

CREATE INDEX IF NOT EXISTS idx_agent_jobs_lease
    ON agent_jobs(lease_expires_at);

CREATE TABLE IF NOT EXISTS pm_context_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_tool TEXT NOT NULL DEFAULT 'openproject',
    external_work_package_id TEXT NOT NULL,
    subject TEXT,
    status_name TEXT,
    type_name TEXT,
    project_name TEXT,
    description_raw TEXT,
    work_package_payload JSONB,
    activities_payload JSONB,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pm_context_snapshots_wp
    ON pm_context_snapshots(external_work_package_id, synced_at DESC);
