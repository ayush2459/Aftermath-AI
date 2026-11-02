# Unified Aftermath AI customer support

## Customer experience

Customers contact the existing Aftermath Discord bot in one configured recovery channel. The bot routes GhostTrail recovery commands and ordinary support messages to the Aftermath API.

## Current implementation

- The direct Discord client uses the existing Discord bot token and Discord Gateway.
- `CASE <case_code>` retrieves the saved GhostTrail diagnosis and approved recovery plan.
- `CONFIRM <case_code>` executes only the previously approved simulated recovery and verifies the committed database state before returning a shipment link.
- Other messages are sent to `POST /api/support/cases` when the customer mentions the bot.
- Reports are categorized deterministically as shipment recovery, payment support, account support, software bug, or general support.
- The API requires the server-side `DISCORD_RECOVERY_AGENT_KEY`.
- Discord channel identifiers are stored as SHA-256 hashes. Common email addresses and credential formats are redacted before report text is persisted.
- Discord message IDs provide idempotency when available.
- Customer-facing replies do not expose internal errors or implementation details.

## Specialist boundaries

### GhostTrail recovery specialist

Handles shipment failures using persisted evidence, an approved recovery plan, an explicit customer confirmation, idempotent execution, and a verified read-only shipment URL. Current shipment execution is simulation-only; it does not contact a carrier or move a real parcel.

### Software issue specialist

The unified intake currently classifies and records software bug reports. It does not yet write or publish application code. A future repair worker must use a disposable environment, path allowlists, isolated credentials, test gates, audit trails and explicit authorization. Do not connect a customer-facing Discord bot directly to a general-purpose repository write token.

## Database migration

For an existing database:

    psql -d aftermath_ai -f database/phase_4_unified_support_migration.sql

Fresh databases also receive the `support_cases` table from `database/schema.sql`.

## Direct Discord integration

Run the client locally from the backend directory:

    python -m app.discord_recovery_agent

The process uses the existing Discord bot token and listens only in the configured recovery channel. Enable **Message Content Intent** for the bot in the Discord Developer Portal. The bot needs permission to view the channel, read message history, send messages and embed links.

**Important:** Only one process may connect to Discord Gateway using a given bot token at a time. Stop any other bot process using the same token before starting this client. The existing REST-based incident notifications can continue using the bot token; they do not open a Gateway connection.

## Environment

Set these values in the backend `.env` file:

    DISCORD_BOT_TOKEN=<existing-discord-bot-token>
    DISCORD_RECOVERY_AGENT_KEY=<new-random-shared-secret>
    DISCORD_RECOVERY_CHANNEL_ID=<numeric-discord-channel-id>
    AFTERMATH_API_BASE_URL=http://127.0.0.1:8000

If `DISCORD_RECOVERY_CHANNEL_ID` is omitted, the client falls back to the existing `DISCORD_CHANNEL_ID`. Keep all secrets server-side; never place them in Vite variables, Discord messages, source control or customer-visible replies.
