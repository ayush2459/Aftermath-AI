# Unified Aftermath AI customer support

## Customer experience

Customers use one Discord-backed Switch Room and address the Aftermath Recovery agent. The agent routes messages to the appropriate specialist workflow and keeps all customer replies plain-language.

## Current implementation

- POST /api/support/cases accepts addressed customer reports from the Switch agent.
- Reports are categorized deterministically as shipment recovery, payment support, account support, software bug, or general support.
- The API requires the server-side DISCORD_RECOVERY_AGENT_KEY.
- Discord room identifiers are stored as SHA-256 hashes. Common email addresses and credential formats are redacted before report text is persisted.
- Switch event IDs provide idempotency when available.
- Customer-facing replies do not expose internal errors or implementation details.
- Existing CASE and CONFIRM commands continue to use the GhostTrail-approved shipment recovery workflow.

## Specialist boundaries

### GhostTrail recovery specialist

Handles shipment failures using persisted evidence, an approved recovery plan, an explicit customer confirmation, idempotent execution, and a verified read-only shipment URL. Current shipment execution is simulation-only; it does not contact a carrier or move a real parcel.

### Software issue specialist

The unified intake currently classifies and records software bug reports. It does not yet write or publish application code. The next stage is a separately deployed, isolated repair worker that can:
1. Reproduce the reported behavior in a disposable environment.
2. Inspect only relevant repository files and tests.
3. Generate a minimal patch from untrusted customer input treated strictly as data.
4. Run existing backend/frontend test suites and security checks.
5. Reject changes to secrets, authentication boundaries, payments, customer data, deployment credentials, or unrelated files.
6. Publish only through the repository's permitted non-force-push path and only after required authorization.
7. Verify the deployed page before telling the customer the issue is resolved.

Do not connect a customer-facing Discord agent directly to a general-purpose repository write token. The repair worker must have its own narrowly scoped credential, isolated workspace, path allowlist, test gate, audit trail, and deployment verification.

## Database migration

For an existing database:

    psql -d aftermath_ai -f database/phase_4_unified_support_migration.sql

Fresh databases also receive the support_cases table from database/schema.sql.

## Switch agent

The existing Switch WebSocket client handles GhostTrail CASE and CONFIRM commands. Other addressed customer messages are sent to /api/support/cases. Switch remains the owner of the Discord Gateway connection; Aftermath does not open a second Discord connection.

## Environment

Reuse the existing backend-only DISCORD_RECOVERY_AGENT_KEY shared secret. Do not place it in Vite variables, Discord messages, source control, or customer-visible replies.
