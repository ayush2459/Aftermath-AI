# Phase 2: Discord operations and notification reliability

## Implemented

- Discord bot REST delivery with server-side bot token and channel ID.
- Incoming webhook fallback for environments that use webhooks.
- Rich incident embeds with severity, incident/order/shipment state, value, failure reason and IDs.
- Persistent PostgreSQL notification outbox.
- Event-level idempotency using `dedupe_key`, so an incident can produce a creation alert and a separate shipment recovery update without duplicate delivery for the same event.
- Bounded retries: at most five delivery attempts, exponential backoff starting at 30 seconds, and recovery of stale `sending` claims after five minutes.
- A background outbox worker: `python -m app.notification_worker`.
- Payment verification creates incident alerts for both the normal recovery path and critical inventory reconciliation.
- Sample shipment recovery emits a separate operational update. It remains explicitly illustrative and does not change real carrier fulfillment.
- Transport tests cover bot authentication, webhook fallback, missing configuration and Discord error responses.
- CI runs for pushes to the Phase 2 branch and pull requests targeting the Phase 1 branch.

## Configuration

Keep credentials only in `backend/.env` locally or the backend hosting provider's secret manager:

```dotenv
DISCORD_BOT_TOKEN=
DISCORD_CHANNEL_ID=
DISCORD_WEBHOOK_URL=
DISCORD_ALERT_TIMEOUT=8
```

The bot API is preferred when both bot token and channel ID are present. The webhook is used only as a fallback. Never commit real tokens or webhook URLs, and never expose them to frontend code.

## Database migration

For an existing database, back it up first, then apply:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/phase_2_notifications_migration.sql
```

The migration adds event-level idempotency to the existing outbox and preserves existing notification rows. Do not rerun the bootstrap `database/schema.sql` against an existing database.

Fresh databases should use the updated `database/schema.sql`.

## Run the retry worker

Start the API and the worker as separate processes using the same backend environment and database:

```bash
cd backend
source .venv/bin/activate
python -m app.notification_worker
```

For a hosted deployment, configure a separate background worker service with start command `python -m app.notification_worker`, the same code revision, and the same environment variables/database URL as the API. A web service alone does not run this worker.

The worker polls every 30 seconds, processes at most 25 due notifications per pass, and relies on atomic database claims to avoid concurrent duplicate sends. Failed rows stop retrying after five attempts and remain visible in the outbox for operator review.

## Validation

Run locally:

```bash
cd backend
python -m compileall -q app
pytest tests -q
```

The automated tests mock Discord transport; they do not require live Discord credentials. A separate live test already confirmed that the configured bot can post text and rich embeds to the target channel, and that one incident notification reached the outbox state `sent`.

## Operational boundaries

- Discord is an alerting destination, not the source of truth; PostgreSQL outbox rows remain authoritative.
- Payment and shipment notifications are generated only from application events; no live carrier webhook/polling integration is added by this phase.
- The sample recovery alert describes a simulated customer-facing action, not a parcel movement.
- Payment notifications are only exercised against Razorpay Test Mode until a separate production readiness review.
- The background worker must be deployed and kept running separately from the FastAPI web service.
- No login system, customer accounts, RBAC, or access-management layer is introduced.
