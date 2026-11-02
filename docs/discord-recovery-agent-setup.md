# Aftermath AI Discord recovery agent

This milestone changes Discord from a support-only destination into the final **simulated recovery coordinator**. Switch owns the Discord Gateway connection; Aftermath does not create a second Discord Gateway client.

## Customer workflow

1. Customer opens GhostTrail for the failed order.
2. GhostTrail collects evidence, generates a diagnosis, proposes a recovery plan and records the operator approval.
3. GhostTrail creates a short-lived, random case code and displays the private Discord support invite.
4. Customer mentions **@Aftermath Recovery** in the private Discord support room and sends `CASE <case_code>`.
5. The Switch agent calls the authenticated Aftermath inspect endpoint. It receives the saved GhostTrail diagnosis and approved plan, then explains the proposed simulated action.
6. Customer explicitly confirms by sending `CONFIRM <case_code>`.
7. The agent calls the authenticated execution endpoint. The backend rechecks approval, payment capture, seeded-failure eligibility and inventory reservations before changing any records.
8. The backend sets the order to `restored`, the shipment to `created`, and the incident to `resolved`; writes a recovery action, event and audit record; then reads the committed state back.
9. The agent replies with the corrected shipment-page link. The link is a read-only share URL that expires after seven days.

**Simulation boundary:** no carrier API is called, no real parcel is created or moved, no delivery is claimed, no payment is changed, and inventory quantities/reservations are not mutated. The carrier name and tracking reference are clearly marked as simulated.

## 1. Apply the database migration

Back up the database, then run:

```bash
psql -U postgres -d aftermath_ai -f database/phase_3_discord_recovery_migration.sql
```

This creates:
- `discord_recovery_handoffs`: hashed case codes, expiry, preview and consumption state.
- `shipment_share_tokens`: hashed, expiring, read-only shipment-page links.

## 2. Configure the Aftermath backend

Generate one high-entropy shared secret:

```bash
openssl rand -hex 32
```

Set these values in the backend environment (never in Vite/frontend variables):

```env
DISCORD_RECOVERY_AGENT_KEY=<same-random-secret-used-by-agent-process>
DISCORD_SUPPORT_INVITE_URL=https://discord.gg/your-private-support-invite
PUBLIC_FRONTEND_URL=https://your-deployed-storefront.example
```

Restart FastAPI after setting them. `PUBLIC_FRONTEND_URL` must be the public storefront origin, without a trailing slash. If omitted, the local default is `http://localhost:5173`.

## 3. Register a custom agent in Switch

Use the Switch **API URL / agent bridge**, not the Gateway URL, for agent API calls. The agent protocol documents registration at `POST /agents`, bearer API keys, room-addressed WebSocket events, and posting replies at `POST /agents/{agent_id}/message`.

Create a registration key in Switch Console, then register once:

```bash
curl -X POST "$SWITCH_API_URL/agents" \
  -H "Authorization: Bearer $SWITCH_REGISTRATION_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "aftermath-recovery",
    "display_name": "Aftermath Recovery",
    "description": "Coordinates GhostTrail-approved simulated shipment recovery and returns verified shipment pages.",
    "connector_type": "custom",
    "integration_profile": {
      "connection_model": "always_on",
      "message_exchange": true,
      "pre_invocation_mediation": [],
      "post_invocation_mediation": [],
      "event_reporting": []
    }
  }'
```

Save the returned `id` and `api_key` securely. The agent API key is returned once. Do not register the same agent on every launch.

Invite the agent to the private Discord-backed Switch room. If customer members need to address it, configure the agent's addressing policy in Switch Console for that room (or set its addressing to `anyone` only in this dedicated private support room). The case code and explicit confirmation are still required before any recovery execution.

## 4. Configure and run the Switch client

Install backend requirements:

```bash
cd backend
python -m pip install -r requirements.txt
```

Set the following variables in the agent runner environment. Use the **agent bridge base URL** and a persistent UUID for the connection:

```bash
export AFTERMATH_API_BASE_URL="https://your-aftermath-api.example"
export DISCORD_RECOVERY_AGENT_KEY="<same-secret-as-backend>"
export SWITCH_BRIDGE_BASE_URL="https://your-switch-agent-bridge.example"
export SWITCH_AGENT_ID="<registered-agent-id>"
export SWITCH_AGENT_API_KEY="<agent-api-key>"
export SWITCH_ROOM_ID="<discord-backed-switch-room-id>"
export SWITCH_CONNECTION_ID="$(python -c 'import uuid; print(uuid.uuid4())')"
python -m app.discord_recovery_agent
```

Keep `SWITCH_CONNECTION_ID` stable across restarts by saving it in the process environment/secret store. Run the client as a supervised, persistent process in deployment. It reconnects with its cursor and generation after transient socket drops.

The client acts only on Switch messages marked `addressed`. It accepts:
- `CASE <case_code>` — inspect and summarize the GhostTrail diagnosis and approved plan.
- `CONFIRM <case_code>` — execute the approved simulation after the agent has inspected the case.

## 5. Verify the complete flow

1. Create a seeded failed test order and open its shipment page.
2. Open GhostTrail, investigate, diagnose, propose a plan and record approval.
3. Select **Send approved recovery to Discord** and copy the displayed case code.
4. In the private Discord-backed room, mention `@Aftermath Recovery CASE <case_code>`.
5. Review the returned diagnosis and action.
6. Explicitly send `@Aftermath Recovery CONFIRM <case_code>`.
7. Confirm the agent posts a corrected shipment URL.
8. Open that URL in a browser, including a fresh browser session. It should show the restored order, simulated carrier reference and persisted recovery event.
9. Confirm the database states:
   - `orders.status = 'restored'`
   - `shipments.status = 'created'`
   - `incidents.status = 'resolved'`
   - `recovery_actions.action_type = 'discord_simulated_shipment_restore'` and `status = 'completed'`

Example verification query:

```sql
SELECT
    o.order_id,
    o.status AS order_status,
    s.status AS shipment_status,
    s.carrier_code,
    s.tracking_number,
    i.status AS incident_status,
    ra.status AS recovery_status
FROM orders o
JOIN shipments s ON s.order_id = o.order_id
JOIN incidents i ON i.order_id = o.order_id
LEFT JOIN recovery_actions ra
  ON ra.incident_id = i.incident_id
 AND ra.action_type = 'discord_simulated_shipment_restore'
WHERE o.order_id = '<order-id>'
ORDER BY ra.created_at DESC
LIMIT 1;
```

## Security notes

- Case codes are random, stored only as SHA-256 hashes, expire after 60 minutes and are bound to one approved order/plan.
- The agent-only endpoints require `X-Aftermath-Agent-Key`; never expose this key to the browser or Discord messages.
- The agent requires an inspect step and explicit `CONFIRM RECOVERY` confirmation. Execution is idempotent by recovery plan.
- Shipment share links are opaque, read-only and expire after seven days. Revoke all active share links for an order with `UPDATE shipment_share_tokens SET revoked_at = NOW() WHERE order_id = '<order-id>' AND revoked_at IS NULL;`.
- The current storefront still uses browser customer-session identifiers for owner access. Treat this as a demo identity mechanism, not production authentication. Before production, replace it with authenticated customer identities and rate-limit handoff creation/inspection.
- This integration does not add a second Discord Gateway connection to FastAPI. Switch remains the Discord transport owner.
