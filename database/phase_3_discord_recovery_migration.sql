-- Phase 3: GhostTrail-to-Discord simulated recovery handoff and read-only shipment share links.
-- Apply once to an existing Aftermath AI database after the previous phase migrations.

CREATE TABLE IF NOT EXISTS discord_recovery_handoffs (
    handoff_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES recovery_plans(plan_id) ON DELETE CASCADE,
    order_id UUID NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    previewed_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discord_recovery_handoffs_order
    ON discord_recovery_handoffs(order_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_discord_recovery_handoffs_expiry
    ON discord_recovery_handoffs(expires_at)
    WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS shipment_share_tokens (
    token_hash TEXT PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES recovery_plans(plan_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shipment_share_tokens_order
    ON shipment_share_tokens(order_id, expires_at DESC);
