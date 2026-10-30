-- Shipment business fields for agent-facing shipment tools.
-- Safe to run on an existing database; all new fields are nullable because
-- the current demo shipment is intentionally seeded without a real carrier.
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS carrier_name TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS carrier_code TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS tracking_number TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS current_location TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS estimated_delivery_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_events_order_timeline
  ON events(order_id, created_at ASC);
