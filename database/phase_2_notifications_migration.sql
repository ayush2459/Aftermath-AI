-- Phase 2: event-keyed Discord outbox and safe retry support.
-- Apply to existing databases after the Phase 1 notification outbox migration.
ALTER TABLE notification_deliveries
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT;

UPDATE notification_deliveries
SET dedupe_key = 'incident:' || incident_id::text || ':created'
WHERE dedupe_key IS NULL;

ALTER TABLE notification_deliveries
    ALTER COLUMN dedupe_key SET NOT NULL;

ALTER TABLE notification_deliveries
    DROP CONSTRAINT IF EXISTS notification_deliveries_incident_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_deliveries_dedupe_key
    ON notification_deliveries(dedupe_key);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_retry
    ON notification_deliveries(status, updated_at)
    WHERE status IN ('pending', 'failed', 'sending');
