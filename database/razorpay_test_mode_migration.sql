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
