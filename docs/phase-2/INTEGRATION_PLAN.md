# Phase 2 — Integration plan

## Discord access constraint

The current operator can see and use the existing Discord bot in the AFTERMATH_AI server, but does not have its bot token, source code, hosting access, or permission to ask the host to change its configuration.

An Application ID is public metadata. It cannot authenticate a bot or authorize API calls. The existing bot therefore cannot be adopted by the Aftermath backend under the current access model.

## Decision

Do not make Phase 2 depend on the inaccessible bot. Keep Discord delivery as an optional outbound notification channel and continue building the core recovery platform independently.

The repository already has an outbound Discord webhook dispatcher:
- `backend/app/notifications.py`
- `DISCORD_WEBHOOK_URL` and `DISCORD_ALERT_TIMEOUT` in `backend/app/config.py`
- `notification_deliveries` outbox records persisted with incidents.

That integration can send incident embeds when a server-channel webhook URL is supplied. It does not require control of the bot process, but a user with the Discord server's **Manage Webhooks** permission must create the webhook and provide its URL securely. Do not put the URL in source control or chat.

If that permission is unavailable, leave Discord delivery disabled. Do not attempt to scrape credentials, reuse another person's token, or bypass server permissions.

## Re-enable Discord later

Choose one authorized route:
1. Ask a server administrator to create a dedicated channel webhook for Aftermath AI and place its URL in the backend secret store; or
2. Create a separate Aftermath AI Discord application under an account the project owner controls, then ask a server administrator to install it with only the required channel permissions. Store its bot token in the backend secret store.

The Application ID `1565633171322576906` may be used to identify the existing application, but it is not a credential.

## Phase 2 sequencing

1. Replace browser-generated customer session identifiers with authenticated customer identity and role-based authorization.
2. Harden Razorpay webhook ingestion, signature validation, idempotency, and reconciliation.
3. Build incident classification, evidence timelines, and human-approved recovery plans.
4. Add live carrier tracking and verified shipment state updates.
5. Add operational dashboards and notification delivery observability.
6. Enable Discord as an optional adapter once an authorized webhook or bot credential is available.

## Security and release gates

- No secrets in Git, frontend bundles, issue comments, or chat.
- Discord delivery failure must never roll back a committed order or incident.
- Persist delivery attempts and errors; retries must be bounded and idempotent.
- Do not mark an incident resolved based only on a Discord message or an LLM recommendation.
- Keep consequential recovery actions behind explicit authorization and audit logging.
