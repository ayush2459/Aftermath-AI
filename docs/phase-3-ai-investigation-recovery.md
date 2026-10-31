# Phase 3: GhostTrail investigation and safe recovery planning

## Goal

Turn Aftermath AI from an incident-alerting demo into an evidence-led investigation and recovery-planning system. Phase 3 builds on the Phase 2 notification outbox and incident records; it does not replace PostgreSQL as the source of truth.

## Phase 2 dependency

- Base branch: `phase-2/discord-operations`.
- Phase 2 PR #8 remains separate and must be merged before this phase is merged into Phase 1/main.
- The notification worker remains a separate process. Local development may run it alongside the API.
- Existing database migrations must be additive. Never re-run the bootstrap schema against an existing database.

## Scope

### 1. GhostTrail evidence collection

- Build an investigation service for a single incident.
- Gather the related order, payment verification/payment state, inventory reservation, shipment, incident, event timeline, audit entries, and notification-delivery state where available.
- Use bounded, deterministic database queries and stable ordering.
- Record source, observation time, and whether each item is confirmed, missing, stale, or contradictory.
- Do not treat a missing record as proof that an external action did not occur.

### 2. State reconciliation

- Define an explicit state snapshot for payment, order, inventory, and shipment.
- Detect known inconsistencies (for example, captured test payment with failed shipment creation, or an order marked fulfilled without a verified shipment).
- Return findings with evidence references and severity; do not silently mutate business state.
- Keep Razorpay in Test Mode and label seeded/demo carrier failures as simulated.

### 3. AI-assisted diagnosis

- Add an LLM provider adapter behind a configuration boundary; support deterministic fallback when no provider is configured.
- Send only the minimum incident evidence needed for diagnosis.
- Require a versioned, validated structured response: summary, likely cause, evidence references, confidence, unknowns, and recommended next step.
- Treat model output as untrusted advice. Reject invalid evidence references and never let the model directly execute SQL, call payment APIs, or create shipments.
- Persist diagnosis metadata and output so investigations are auditable and repeatable.

### 4. Recovery planning

- Generate typed recovery proposals: retry a safe idempotent step, continue a workflow, compensate, or request operator review.
- Each proposal must include preconditions, expected effects, risk/severity, idempotency key strategy, and verification query.
- Mark actions requiring external side effects as approval-required.
- Phase 3 may expose approval and execution interfaces, but no high-impact action executes without an explicit operator approval record.

### 5. Read-back verification

- After any permitted demo-safe action, re-read authoritative database state.
- Mark recovery complete only when defined invariants pass.
- Otherwise retain the incident as open or recovery-required and explain which invariant failed.
- Keep an audit trail of proposal, approval, execution attempt, and verification result.

## Explicit exclusions

- No customer login, customer accounts, RBAC, or access-management layer.
- No production payment processing, live refunds, or automatic payment retries.
- No live carrier integration, real parcel movement, or claims of live tracking.
- No autonomous high-impact actions.
- No replacing PostgreSQL records with LLM-generated state.
- No breaking changes to Phase 1/2 contracts without an additive migration and regression tests.

## Suggested implementation sequence

1. Inspect and document existing database models, event contracts, and service boundaries.
2. Implement deterministic incident evidence collection and reconciliation with unit/integration tests.
3. Add versioned diagnosis schemas and a provider-independent diagnosis service with deterministic fallback.
4. Add recovery proposal models and approval/audit records.
5. Implement demo-safe action execution and read-back verification.
6. Add API endpoints and a focused operator-facing investigation view.
7. Add CI coverage and an end-to-end test using seeded demo incidents.

## Acceptance criteria

- An incident investigation can be generated entirely from persisted evidence without an LLM.
- Findings distinguish confirmed facts, missing evidence, stale observations, and contradictions.
- Every diagnosis claim references collected evidence or is explicitly labelled uncertain.
- LLM output cannot execute tools or mutate business state.
- Recovery proposals are structured, idempotency-aware, and approval-gated.
- A demo-safe recovery is not marked complete until read-back invariants pass.
- Existing Phase 1 and Phase 2 tests continue to pass.
- All demo/test-mode and simulated-carrier boundaries are visible in API responses and UI.
