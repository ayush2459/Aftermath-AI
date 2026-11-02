-- Phase 4: unified Discord support intake and deterministic issue routing.
-- Apply once to an existing Aftermath AI database.

CREATE TABLE IF NOT EXISTS support_cases (
    case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL DEFAULT 'switch_room',
    room_id_hash TEXT NOT NULL,
    source_event_id TEXT,
    category TEXT NOT NULL CHECK (
        category IN ('shipment_recovery','payment_support','account_support','software_bug','general_support')
    ),
    status TEXT NOT NULL DEFAULT 'triaged' CHECK (
        status IN ('triaged','investigating','awaiting_customer','resolved','escalated')
    ),
    customer_message TEXT NOT NULL,
    page_url TEXT,
    resolution_summary TEXT,
    customer_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_support_cases_status_created
    ON support_cases(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_cases_category_created
    ON support_cases(category, created_at DESC);

DROP TRIGGER IF EXISTS trg_support_cases_updated_at ON support_cases;
CREATE TRIGGER trg_support_cases_updated_at
    BEFORE UPDATE ON support_cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
