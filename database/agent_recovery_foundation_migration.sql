-- Aftermath AI: AI-agent, recovery, identity and integration persistence foundation.
-- Apply once to an existing database with:
--   psql -v ON_ERROR_STOP=1 -U postgres -d aftermath_ai -f database/agent_recovery_foundation_migration.sql
-- Safe to re-run: DDL is guarded with IF NOT EXISTS / catalog checks.
BEGIN;

-- The API reads occurred_at, while the original bootstrap schema only had created_at.
ALTER TABLE events ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;
UPDATE events SET occurred_at = created_at WHERE occurred_at IS NULL;
ALTER TABLE events ALTER COLUMN occurred_at SET DEFAULT NOW();
ALTER TABLE events ALTER COLUMN occurred_at SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_order_occurred ON events(order_id, occurred_at ASC, event_id ASC);

-- Incident lifecycle metadata.
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS resolution_summary TEXT;
CREATE INDEX IF NOT EXISTS idx_incidents_order_created ON incidents(order_id, created_at DESC);

-- Versioned recovery plans. The JSON plan remains the extensible, typed-at-the-API payload.
ALTER TABLE recovery_plans ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE recovery_plans ADD COLUMN IF NOT EXISTS risk_level TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE recovery_plans ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE recovery_plans ADD COLUMN IF NOT EXISTS expected_postconditions JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE recovery_plans ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_recovery_plans_incident_created ON recovery_plans(incident_id, created_at DESC);

-- Approval scope, expiry and replay protection.
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS plan_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'internal';
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS uq_approvals_idempotency_key
  ON approvals(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_approvals_plan_status ON approvals(plan_id, status, created_at DESC);

-- Recovery execution lifecycle and provider correlation.
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS attempt_number INTEGER NOT NULL DEFAULT 1;
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS requested_by TEXT;
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE recovery_actions ADD COLUMN IF NOT EXISTS external_reference TEXT;
CREATE INDEX IF NOT EXISTS idx_recovery_actions_incident_created ON recovery_actions(incident_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_status ON recovery_actions(status, updated_at DESC);

-- One durable record per agent investigation/recovery run.
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  correlation_id UUID NOT NULL DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','waiting_approval','completed','failed','cancelled','escalated')),
  trigger_source TEXT NOT NULL DEFAULT 'system',
  agent_name TEXT NOT NULL DEFAULT 'aftermath-recovery-agent',
  model_provider TEXT,
  model_name TEXT,
  current_node TEXT,
  diagnosis JSONB NOT NULL DEFAULT '{}'::jsonb,
  final_result JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_code TEXT,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_incident_created ON agent_runs(incident_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created ON agent_runs(status, created_at DESC);

-- LangGraph resumability. Store only approved workflow state; never persist secrets in checkpoint JSON.
CREATE TABLE IF NOT EXISTS agent_checkpoints (
  checkpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
  checkpoint_key TEXT NOT NULL,
  node_name TEXT NOT NULL,
  state JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(run_id, checkpoint_key)
);
CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_run_created ON agent_checkpoints(run_id, created_at DESC);

-- Independent, auditable verification checks for each recovery action.
CREATE TABLE IF NOT EXISTS recovery_verifications (
  verification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  action_id UUID NOT NULL REFERENCES recovery_actions(action_id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','passed','failed','inconclusive')),
  verifier_name TEXT NOT NULL DEFAULT 'aftermath-verifier',
  checks JSONB NOT NULL DEFAULT '[]'::jsonb,
  observed_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  failure_reason TEXT,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recovery_verifications_action ON recovery_verifications(action_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recovery_verifications_incident ON recovery_verifications(incident_id, created_at DESC);

-- Each carrier allocation/retry attempt is separately tracked to avoid duplicate fulfilment.
CREATE TABLE IF NOT EXISTS carrier_attempts (
  carrier_attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  shipment_id UUID NOT NULL REFERENCES shipments(shipment_id) ON DELETE CASCADE,
  incident_id UUID REFERENCES incidents(incident_id) ON DELETE SET NULL,
  attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
  carrier_code TEXT,
  request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','succeeded','failed','unknown','cancelled')),
  idempotency_key TEXT NOT NULL UNIQUE,
  provider_reference TEXT,
  error_code TEXT,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(shipment_id, attempt_number)
);
CREATE INDEX IF NOT EXISTS idx_carrier_attempts_shipment ON carrier_attempts(shipment_id, attempt_number DESC);

-- Short-lived website-to-Discord recovery handoff. Store only a hash of the opaque token.
CREATE TABLE IF NOT EXISTS recovery_sessions (
  recovery_session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  order_id UUID NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  customer_session TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','consumed','expired','revoked')),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  consumed_by_discord_user_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recovery_sessions_incident_status ON recovery_sessions(incident_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_recovery_sessions_order ON recovery_sessions(order_id, created_at DESC);

-- Discord identity mapping. Keep platform IDs; avoid storing profile data not needed for authorization.
CREATE TABLE IF NOT EXISTS discord_user_links (
  discord_user_id TEXT PRIMARY KEY,
  customer_session TEXT NOT NULL,
  linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  last_verified_at TIMESTAMPTZ,
  UNIQUE(customer_session, discord_user_id)
);
CREATE INDEX IF NOT EXISTS idx_discord_user_links_session ON discord_user_links(customer_session)
  WHERE revoked_at IS NULL;

-- Durable webhook/event inbox for Switch or other external integration adapters.
-- external_event_id is unique per source to make delivery retries idempotent.
CREATE TABLE IF NOT EXISTS integration_events (
  integration_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  external_event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  incident_id UUID REFERENCES incidents(incident_id) ON DELETE SET NULL,
  correlation_id UUID,
  signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'received'
    CHECK (status IN ('received','processing','processed','failed','ignored')),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  last_error TEXT,
  UNIQUE(source, external_event_id)
);
CREATE INDEX IF NOT EXISTS idx_integration_events_status_received ON integration_events(status, received_at);
CREATE INDEX IF NOT EXISTS idx_integration_events_incident ON integration_events(incident_id, received_at DESC);

-- Updated-at triggers for new mutable tables.
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['agent_runs'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_updated_at ON %I', t, t);
    EXECUTE format('CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
  END LOOP;
END $$;

COMMIT;
