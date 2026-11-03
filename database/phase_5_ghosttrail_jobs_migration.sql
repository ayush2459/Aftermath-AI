-- Durable event-driven GhostTrail investigation jobs and Discord handoff payloads.
-- Apply once to an existing Aftermath database.

CREATE TABLE IF NOT EXISTS ghosttrail_investigation_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL UNIQUE REFERENCES incidents(incident_id) ON DELETE CASCADE,
    customer_session TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processing','completed','failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ghosttrail_jobs_due
    ON ghosttrail_investigation_jobs(status, next_attempt_at, created_at);

ALTER TABLE notification_deliveries
    ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
