# PostgreSQL database

Aftermath AI uses PostgreSQL for commerce state, incident evidence, AI-agent runs, recovery approvals/actions, verification, customer handoff sessions and external integration events.

## Fresh local database

From the repository root in PowerShell:

```powershell
createdb -U postgres aftermath_ai
psql -v ON_ERROR_STOP=1 -U postgres -d aftermath_ai -f .\database\schema.sql
```

The bootstrap schema creates the core commerce tables and then applies the Razorpay, shipment-tool and AI-recovery migrations through psql's relative include command. Run it with `psql`, not by pasting the file into a generic SQL editor.

## Existing local database

Back up your database first. Then inspect which migrations have already been applied. For a database that already has the original schema, Razorpay Test Mode migration and shipment-agent migration, apply only the new AI/recovery foundation migration:

```powershell
pg_dump -U postgres -d aftermath_ai -F c -f .\aftermath_ai_before_agent_migration.dump
psql -v ON_ERROR_STOP=1 -U postgres -d aftermath_ai -f .\database\agent_recovery_foundation_migration.sql
```

If the Razorpay or shipment migrations have not yet been applied, apply them before the AI/recovery migration:

```powershell
psql -v ON_ERROR_STOP=1 -U postgres -d aftermath_ai -f .\database\razorpay_test_mode_migration.sql
psql -v ON_ERROR_STOP=1 -U postgres -d aftermath_ai -f .\database\shipment_agent_tools_migration.sql
psql -v ON_ERROR_STOP=1 -U postgres -d aftermath_ai -f .\database\agent_recovery_foundation_migration.sql
```

Do not re-run the original bootstrap schema against a populated database without reviewing its seed upsert behavior. The demo product upsert intentionally refreshes product names, descriptions, prices, currency, image paths and active flags; it does not overwrite stock quantity.

## New AI/recovery persistence

The new migration adds:
- `agent_runs` and `agent_checkpoints` for durable agent execution and resumability.
- `recovery_verifications` for independent, per-action verification results.
- `carrier_attempts` for idempotent shipment allocation/retry history.
- `recovery_sessions` for expiring, single-use website-to-Discord handoff tokens (store token hashes, never raw tokens).
- `discord_user_links` for Discord identity association with a customer session.
- `integration_events` as an idempotent webhook/event inbox for Switch or other adapters.
- Additional version, risk, expiry, approval, execution and verification metadata on recovery tables.
- `events.occurred_at`, backfilled from `created_at`, to match the shipment timeline API.

The Switch integration is intentionally generic until the exact Switch product and webhook/API contract are confirmed.

## Verify the database

Run these checks after migration:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'events'
ORDER BY ordinal_position;

SELECT COUNT(*) AS seeded_products FROM products;
SELECT COUNT(*) AS incidents FROM incidents;
```

Expected new tables: `agent_runs`, `agent_checkpoints`, `recovery_verifications`, `carrier_attempts`, `recovery_sessions`, `discord_user_links`, and `integration_events`.

Confirm that `events.occurred_at` exists and is non-null. Existing order, payment, inventory and incident rows should remain intact.

## Data and secret hygiene

Only synthetic demo product records and schema/migrations belong in this repository. Never commit database dumps, customer data, raw recovery tokens, Discord credentials, Razorpay secrets, or `.env` files. Store only a cryptographic hash of a recovery token. Restrict database roles and API access in deployment; the AI agent should access business data through authenticated backend tools rather than unrestricted SQL.

