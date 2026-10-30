-- Shipment business fields for agent-facing shipment tools.
-- Safe to run on an existing database; all new fields are nullable because
-- the current demo shipment is intentionally seeded without a real carrier.
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS carrier_name TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS carrier_code TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS tracking_number TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS current_location TEXT;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS estimated_delivery_at TIMESTAMPTZ;

-- Existing databases may use occurred_at/received_at instead of created_at.
-- The order timeline index already exists in the user's schema as
-- idx_events_order_occurred (order_id, occurred_at), so no extra index is needed.
