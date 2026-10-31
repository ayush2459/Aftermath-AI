# Phase 2: Discord operations integration

## Current access constraints

The current operator can use an existing Discord bot but does not have:
- Discord Developer Portal access for that application
- permission to install applications/bots in the target server
- permission to create channel webhooks
- access to the host machine or bot source code

The existing bot (Application ID `1565633171322576906`) therefore cannot be modified or authenticated by this project. An Application ID is public metadata, not an access credential.

## Existing Aftermath AI implementation

Phase 1 already provides:
- a `notification_deliveries` outbox table
- `backend/app/notifications.py` to format and dispatch incident alerts
- `DISCORD_WEBHOOK_URL` and `DISCORD_ALERT_TIMEOUT` configuration
- delivery status tracking (`pending`, `sending`, `sent`, `failed`)

The service uses a Discord incoming webhook. It does not require a Discord bot token or a bot process. Do not add the existing third-party bot token to this project.

## Feasible integration path

1. Keep Discord delivery disabled while `DISCORD_WEBHOOK_URL` is unset.
2. Continue developing and testing the outbox and notification formatting independently of Discord.
3. When an authorized server administrator can create a webhook, obtain its URL through a secure channel and store it as a backend environment secret:
   - local development: `backend/.env` (never commit this file)
   - deployment: the backend hosting provider's environment/secrets settings
4. Set `DISCORD_ALERT_TIMEOUT=8` (or another suitable bounded timeout).
5. Trigger a controlled test incident in a non-production environment and verify:
   - one alert appears in the intended channel
   - `notification_deliveries.status` becomes `sent`
   - failed delivery records an error and can be retried safely
6. Rotate/revoke the webhook immediately if its URL is exposed.

## Required permissions from a server administrator

At least one of these is required:
- create an incoming webhook in the desired channel and securely provide its URL; or
- install a separately managed Aftermath AI bot in the server with permission to send messages.

Without one of those actions, Discord cannot accept messages from Aftermath AI. There is no supported way to bypass server permissions using only an Application ID or ordinary bot visibility.

## Security and operational notes

- Never commit webhook URLs, bot tokens, or other credentials.
- Never put Discord credentials in frontend code or browser storage.
- Do not log the full webhook URL.
- Treat Discord as an alerting destination, not the source of truth; PostgreSQL outbox records remain authoritative.
- Keep payment, order, customer, and shipment data in alerts to the minimum necessary. Avoid personal or payment-sensitive information.
- The current Phase 1 delivery function sends incident alerts only; additional event types (payment lifecycle, shipment milestones, daily summaries) should be added through the same notification abstraction with tests.

## Phase 2 acceptance criteria

- [ ] Notification formatting tests pass without network access.
- [ ] Missing webhook configuration causes a safe no-send result.
- [ ] Delivery success/failure updates the outbox accurately.
- [ ] Retry behavior is bounded and does not create uncontrolled duplicate alerts.
- [ ] A real Discord webhook test is completed only after an authorized administrator provisions the webhook.
