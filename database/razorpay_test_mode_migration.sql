-- Discord incident notification outbox. Safe to apply to an existing database.
CREATE TABLE IF NOT EXISTS notification_deliveries (
 delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 incident_id UUID NOT NULL UNIQUE REFERENCES incidents(incident_id) ON DELETE CASCADE,
 channel TEXT NOT NULL DEFAULT 'discord',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','failed')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
 last_error TEXT,
 sent_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notification_deliveries_status
 ON notification_deliveries(status, updated_at);

-- Razorpay Test Mode payment metadata migration.
-- Run once against the aftermath_ai database after backing it up.
ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'simulated';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS razorpay_signature TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_razorpay_order_id
  ON payments(razorpay_order_id) WHERE razorpay_order_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_razorpay_payment_id
  ON payments(razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL;
