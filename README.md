# Aftermath AI

**When a business workflow breaks halfway through, Aftermath helps teams find out what happened and recover safely.**

A checkout can succeed while the next step fails. A customer has paid, inventory has been reserved, but the shipment was never created. The payment system, store, and shipping service may each tell a different part of the story. Retrying blindly could create a duplicate shipment or charge.

Aftermath AI is envisioned as the recovery layer for moments like this. It brings the evidence together, checks the actual state of each system, recommends a safe next step, and verifies the outcome before anyone is told the problem is resolved. The intended experience connects customers, operators, and a coordinated AI team around the same verified order state.

## The product vision

Aftermath is designed to turn a messy, partially completed workflow into a clear path forward:

1. **Notice the break.** Detect when a process stops after earlier steps have already succeeded.
2. **Reconstruct the story.** Put events from different systems into one timeline and distinguish confirmed facts from unknowns.
3. **Check what is true now.** Confirm whether the payment, order, inventory reservation, and shipment actually exist before taking action.
4. **Choose a safe recovery.** Recommend whether to continue, retry, compensate, or hand the case to a person. Require approval for consequential actions.
5. **Verify the result.** Read the business records again and close the incident only when the final state is consistent.

Aftermath aims to help operations and engineering teams get a customer's order back on track without creating a second problem.

### Who it is for

- **Commerce operations teams** managing paid orders that are stuck between systems.
- **Engineers and incident responders** who need a trustworthy timeline and a clear recovery decision.
- **Customers** who deserve an honest status update while a problem is being investigated.

The same approach could eventually help other multi-system workflows, such as onboarding, subscriptions, and business automations.

## See the idea in action

This repository is a **demo of the first part of that vision**, built around one repeatable scenario:

1. Browse a five-product test storefront and place an order using Razorpay Test Mode.
2. The backend verifies the test payment and records the order and inventory reservation.
3. A shipment failure is deliberately created after payment succeeds.
4. Open **Shipment Monitoring** to see the order, products, incident, status, and recorded event timeline.
5. Open the Discord help link from the shipment view.

The shipment is a sample failure. No physical parcel is sent, and the test checkout does not charge real money.

### What works today

| Experience | What the demo shows |
| --- | --- |
| Test storefront | Product browsing, cart, checkout, and order confirmation |
| Payment verification | Server-side checks of the Razorpay Test Mode result before the local order is finalized |
| Incident record | A deliberately failed shipment with an incident, event, and audit record |
| Shipment monitor | Order details, purchased products, shipment status, issue details, and event timeline |
| Investigation data | Read-only APIs for shipment status, timeline, issues, and available carrier information |
| Discord entry point | A help link in the shipment view; the repository also contains an optional webhook alert path for the simulated order endpoint |

### What comes next

The full recovery experience is still a product direction, not a feature of this demo. The vision documents describe **GhostTrail** as the evidence-gathering investigator within Aftermath and a Switch-connected team in Discord where people can review findings and approve consequential actions. Planned work includes state reconciliation, AI-assisted diagnosis, recovery plans, controlled action execution, and read-back verification. Customers would see progress in the store and a restored order only after the backend confirms it.

<details>
<summary>Run the demo locally (developer setup)</summary>

## Local setup

You will need Python 3.11+, Node.js and npm, PostgreSQL, and Razorpay **Test Mode** keys.

From the repository root, create a local database and apply the schema and payment migration:

```powershell
createdb -U postgres aftermath_ai
psql -U postgres -d aftermath_ai -f .\database\schema.sql
psql -U postgres -d aftermath_ai -f .\database\razorpay_test_mode_migration.sql
```

In one terminal, start the API:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Set DATABASE_URL and Razorpay Test Mode keys in .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the storefront:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Open the URL printed by Vite (usually [http://localhost:5173](http://localhost:5173)). The shipment monitor is at `/shipments`; the API health check and interactive docs are at [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) and [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Keep secrets in `backend/.env`, never in the frontend. If you run the frontend on another port, add that origin to `CORS_ORIGINS` in the backend environment. For an existing database, see [database setup](database/README.md) before applying migrations.

</details>

## Project map

- [frontend/](frontend/) — the test store and shipment monitoring experience.
- [backend/](backend/) — order, payment, shipment, and incident APIs.
- [database/](database/) — local PostgreSQL schema, demo products, and migrations.

This is a development prototype. It does not yet investigate incidents with AI, execute recovery actions, connect to a live carrier, or run a verified end-to-end restoration. Its purpose is to make the failure and its business context visible while those recovery capabilities are built.


## GhostTrail and Discord recovery workflow

The current branch includes an end-to-end **simulated shipment-failure recovery path**:

1. The order API records the failed shipment, incident, event, audit entry, and a durable Discord notification-outbox row in one database transaction.
2. The notification worker retries pending Discord notifications with bounded exponential backoff.
3. GhostTrail gathers persisted order, payment, inventory, shipment, event, and audit evidence; creates an advisory diagnosis and recovery proposal; and creates a short-lived Discord handoff.
4. In the configured Discord recovery channel, operators use `CASE <code>` to inspect the case, `STATUS <code>` to read current persisted state, and `CONFIRM <code>` to explicitly approve and execute the guarded demo action.
5. The backend rechecks payment, shipment, inventory, approval, expiry, and idempotency preconditions. The bot reports success only after it reads back the expected order, shipment, and incident states.

The customer-facing storefront and shipment pages do not expose operator controls. The Operations Dashboard is a read-only monitoring surface. Recovery decisions and commands remain in Discord.

### Run the background processes

Run the API, notification worker, and Discord Gateway bot as **three separate long-lived processes** using the same backend environment and database:

```bash
# Terminal 1 — API
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — durable Discord notification outbox
cd backend
source .venv/bin/activate
python -m app.notification_worker

# Terminal 3 — Discord command bot (only one Gateway instance per token)
cd backend
source .venv/bin/activate
python -m app.discord_recovery_agent
```

Configure the backend environment with the existing database and Discord settings: `DISCORD_BOT_TOKEN`, `DISCORD_RECOVERY_AGENT_KEY`, `DISCORD_RECOVERY_CHANNEL_ID` (or `DISCORD_CHANNEL_ID`), `DISCORD_SUPPORT_INVITE_URL`, and `PUBLIC_FRONTEND_URL`. The bot also needs `AFTERMATH_API_BASE_URL` pointing to the reachable API. Never put these secrets in frontend environment variables or commit them.

The worker is not started by the FastAPI web process. In deployment, configure it as a separate background/worker service with restart-on-failure. The Discord bot is a separate long-running process as well. If either process is stopped, the API can still persist incidents, but Discord delivery or command handling will pause until that process is running again.

### Discord command sequence

- `CASE <code>` — inspect the GhostTrail evidence and proposed action; this also records that the case was previewed.
- `STATUS <code>` — read the current incident, approval, payment, shipment, and recovery-action state without changing it.
- `CONFIRM <code>` — explicitly approve and execute the eligible simulated recovery. If a request times out, use `STATUS` before deciding whether to retry.

The case code expires after 60 minutes. A completed recovery is idempotent; repeating the confirmation does not create a duplicate action.

### Current scope and honest limitations

- The automated failure currently originates from the seeded shipment-allocation failure created by the demo order flow. This is not yet a universal detector for arbitrary third-party checkout, payment, inventory, or carrier systems.
- The outbox worker delivers and retries Discord notifications. GhostTrail investigation and plan preparation are initiated by opening its handoff page; this is not yet a durable autonomous investigation worker.
- The recovery action is a guarded database simulation. No live carrier API is contacted and no physical parcel is created or moved.
- The Operations Dashboard refreshes by polling. It is not a WebSocket/SSE stream.
- Discord approval, state checks, idempotency, audit records, and read-back verification are implemented for the seeded demo path. Production provider reconciliation requires real provider adapters and credentials.
