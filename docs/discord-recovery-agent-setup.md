# Aftermath AI direct Discord recovery agent

This integration connects the existing Aftermath Discord bot directly to Discord Gateway using `discord.py`. Switch is not required for the recovery workflow.

## Customer workflow

1. Customer opens GhostTrail for the failed order.
2. GhostTrail collects evidence, generates a diagnosis, proposes a recovery plan and records operator approval.
3. GhostTrail creates a short-lived, random case code and displays the Discord support invite.
4. Customer posts `CASE <case_code>` in the configured recovery channel.
5. The Aftermath bot retrieves the saved GhostTrail diagnosis and approved plan, then explains the proposed simulated action.
6. Customer explicitly confirms by posting `CONFIRM <case_code>`.
7. The bot calls the authenticated execution endpoint. The backend rechecks approval, payment capture, seeded-failure eligibility and inventory reservations before changing records.
8. The backend sets the order to `restored`, shipment to `created`, and incident to `resolved`; writes recovery, event and audit records; then reads the committed state back.
9. The bot replies with the corrected shipment-page link. The link is read-only and expires after seven days.

**Simulation boundary:** no carrier API is called, no real parcel is created or moved, no delivery is claimed, no payment is changed, and inventory quantities/reservations are not mutated. Carrier and tracking details are clearly marked as simulated.

## 1. Apply database migrations

For an existing database, back it up and apply the relevant migrations:

    psql -U postgres -d aftermath_ai -f database/phase_3_discord_recovery_migration.sql
    psql -U postgres -d aftermath_ai -f database/phase_4_unified_support_migration.sql

## 2. Configure the existing Discord bot

Install dependencies from the backend directory:

    cd backend
    python -m pip install -r requirements.txt

Generate a high-entropy shared secret:

    openssl rand -hex 32

Add these values to `backend/.env`. Keep all existing database and provider settings:

    DISCORD_BOT_TOKEN=<existing-discord-bot-token>
    DISCORD_RECOVERY_AGENT_KEY=<generated-random-secret>
    DISCORD_RECOVERY_CHANNEL_ID=<numeric-channel-id>
    DISCORD_SUPPORT_INVITE_URL=<your-existing-discord-invite>
    PUBLIC_FRONTEND_URL=http://localhost:5173
    AFTERMATH_API_BASE_URL=http://127.0.0.1:8000

The bot token is the existing bot token from Discord Developer Portal. Do not paste it into chat or commit it to GitHub. The recovery channel ID is the numeric ID of the channel where customers will use `CASE` and `CONFIRM`. Enable Developer Mode in Discord, then right-click the channel and choose **Copy Channel ID**.

If `DISCORD_RECOVERY_CHANNEL_ID` is not set, the client falls back to the existing `DISCORD_CHANNEL_ID`.

## 3. Enable Discord permissions and intent

In Discord Developer Portal, open the existing application and its **Bot** settings. Enable **Message Content Intent** under Privileged Gateway Intents.

The bot must be a member of the server and have these permissions in the recovery channel:
- View Channel
- Read Message History
- Send Messages
- Embed Links

Do not create a second Discord application or bot.

## 4. Run the services

Start the FastAPI backend in one terminal:

    cd backend
    source .venv/bin/activate
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Start the Discord client in a second terminal:

    cd backend
    source .venv/bin/activate
    python -m app.discord_recovery_agent

Only one process may connect to Discord Gateway with a given bot token at a time. Stop any existing bot process using that same token before starting this client. The backend's REST-based incident notification sender does not open a Gateway connection and can continue to use the same bot token.

## 5. Verify the complete flow

1. Create a seeded failed test order and open its shipment page.
2. Open GhostTrail, investigate, diagnose, propose a plan and record approval.
3. Select **Send approved recovery to Discord** and copy the displayed case code.
4. In the configured Discord channel, send `CASE <case_code>`.
5. Review the returned diagnosis and approved action.
6. Explicitly send `CONFIRM <case_code>`.
7. Confirm the bot posts a corrected shipment URL.
8. Open the URL in a fresh browser session. It should show the restored order, simulated carrier reference and persisted recovery event.
9. Verify database states:
   - `orders.status = 'restored'`
   - `shipments.status = 'created'`
   - `incidents.status = 'resolved'`
   - `recovery_actions.action_type = 'discord_simulated_shipment_restore'` and `status = 'completed'`

## Security notes

- Case codes are random, stored only as SHA-256 hashes, expire after 60 minutes and are bound to one approved order/plan.
- The agent-only endpoints require `X-Aftermath-Agent-Key`; never expose this key to the browser or Discord messages.
- The bot listens only in the configured recovery channel. Commands require an opaque case code; execution requires explicit confirmation.
- Shipment share links are opaque, read-only and expire after seven days.
- Keep bot tokens and recovery secrets out of source control, frontend environment variables and customer-visible replies.
- The current storefront uses browser customer-session identifiers for owner access. Treat this as a demo identity mechanism, not production authentication.
