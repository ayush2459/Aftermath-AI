-- PostgreSQL bootstrap schema. Apply to a fresh aftermath_ai database.
-- Existing local databases are not uploaded to GitHub.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS products (
 product_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 price_paise INTEGER NOT NULL CHECK(price_paise >= 0), currency CHAR(3) NOT NULL DEFAULT 'INR',
 stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK(stock_quantity >= 0), image_url TEXT,
 is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS orders (
 order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), customer_session TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'created' CHECK(status IN ('created','payment_pending','paid','processing','recovery_required','recovery_in_progress','restored','shipped','cancelled','needs_human')),
 total_paise INTEGER NOT NULL CHECK(total_paise >= 0), currency CHAR(3) NOT NULL DEFAULT 'INR', incident_id UUID,
 version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS order_items (
 order_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
 product_id TEXT NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price_paise INTEGER NOT NULL CHECK(unit_price_paise >= 0),
 line_total_paise INTEGER GENERATED ALWAYS AS (quantity * unit_price_paise) STORED, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(order_id,product_id)
);
CREATE TABLE IF NOT EXISTS payments (
 payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID NOT NULL UNIQUE REFERENCES orders(order_id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','captured','failed','refunded','unknown')),
 amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0), currency CHAR(3) NOT NULL DEFAULT 'INR',
 simulated_provider_ref TEXT UNIQUE, idempotency_key TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS inventory_reservations (
 reservation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID NOT NULL REFERENCES orders(order_id),
 product_id TEXT NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL CHECK(quantity > 0),
 status TEXT NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','released','consumed')),
 idempotency_key TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(order_id,product_id)
);
CREATE TABLE IF NOT EXISTS shipments (
 shipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID NOT NULL UNIQUE REFERENCES orders(order_id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','creating','created','shipped','failed','unknown','cancelled')),
 idempotency_key TEXT NOT NULL UNIQUE, provider_ref TEXT UNIQUE, last_error TEXT,\n carrier_name TEXT, carrier_code TEXT, tracking_number TEXT, current_location TEXT, estimated_delivery_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS incidents (
 incident_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), order_id UUID NOT NULL REFERENCES orders(order_id),
 status TEXT NOT NULL DEFAULT 'open', severity TEXT NOT NULL DEFAULT 'medium', title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
 correlation_id UUID NOT NULL DEFAULT gen_random_uuid(), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS events (
 event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), incident_id UUID REFERENCES incidents(incident_id), order_id UUID REFERENCES orders(order_id),
 source TEXT NOT NULL, event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info', message TEXT NOT NULL,
 payload JSONB NOT NULL DEFAULT '{}'::jsonb, correlation_id UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), incident_id UUID NOT NULL REFERENCES incidents(incident_id),
 evidence_type TEXT NOT NULL, source TEXT NOT NULL, content JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS recovery_plans (
 plan_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), incident_id UUID NOT NULL REFERENCES incidents(incident_id),
 status TEXT NOT NULL DEFAULT 'proposed', plan JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS approvals (
 approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), plan_id UUID NOT NULL REFERENCES recovery_plans(plan_id),
 status TEXT NOT NULL DEFAULT 'pending', requested_by TEXT, decided_by TEXT, decision_reason TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), decided_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS recovery_actions (
 action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), incident_id UUID NOT NULL REFERENCES incidents(incident_id),
 plan_id UUID REFERENCES recovery_plans(plan_id), action_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 idempotency_key TEXT NOT NULL UNIQUE, input JSONB NOT NULL DEFAULT '{}'::jsonb, result JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS audit_log (
 audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), incident_id UUID REFERENCES incidents(incident_id),
 actor_type TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL, decision TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '', details JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_incident ON events(incident_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_incident ON audit_log(incident_id,created_at DESC);

INSERT INTO products(product_id,name,description,price_paise,currency,stock_quantity,image_url,is_active) VALUES
('aurora-headphones','Aurora Wireless Headphones','Over-ear wireless headphones with immersive sound.',349900,'INR',25,'/static/products/aurora-headphones.jpg',TRUE),
('pulse-smartwatch','Pulse Smartwatch','Smartwatch with health and activity tracking.',499900,'INR',20,'/static/products/pulse-smartwatch.jpg',TRUE),
('nova-speaker','Nova Bluetooth Speaker','Portable Bluetooth speaker with rich sound.',229900,'INR',30,'/static/products/nova-speaker.jpg',TRUE),
('orbit-keyboard','Orbit Mechanical Keyboard','Mechanical keyboard with RGB backlighting.',599900,'INR',15,'/static/products/orbit-keyboard.jpg',TRUE),
('echo-desk-lamp','Echo Desk Lamp','Adjustable LED desk lamp for workspaces.',179900,'INR',18,'/static/products/echo-desk-lamp.jpg',TRUE)
ON CONFLICT(product_id) DO UPDATE SET name=EXCLUDED.name, description=EXCLUDED.description, price_paise=EXCLUDED.price_paise, currency=EXCLUDED.currency, image_url=EXCLUDED.image_url, is_active=EXCLUDED.is_active;

DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['products','orders','payments','inventory_reservations','shipments','incidents','recovery_plans','recovery_actions'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_updated_at ON %I', t, t);
  EXECUTE format('CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
 END LOOP;
END $$;
