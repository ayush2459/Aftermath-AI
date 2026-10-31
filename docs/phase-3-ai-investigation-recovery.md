# Phase 3: GhostTrail AI investigation and safe recovery planning

## Delivered

- Deterministic incident evidence collection at `GET /api/agent-tools/investigate/{incident_id}`.
- State reconciliation for payment, order, inventory reservations, and shipment records.
- Evidence timeline, audit records, and notification delivery state in investigation output.
- AI diagnosis at `POST /api/agent-tools/diagnose/{incident_id}`.
- OpenAI-compatible chat-completions adapter; defaults to Groq-compatible base URL and configurable model.
- Strict diagnosis schema validation; evidence references must match collected finding codes.
- Deterministic fallback when no AI key is configured, provider call fails, or provider output is invalid.
- Persisted diagnosis in the existing `evidence` table and audit log.
- Recovery proposal at `POST /api/recovery/propose/{incident_id}`.
- Approval decision record at `POST /api/recovery/plans/{plan_id}/decision`.
- Recovery proposals include preconditions, expected effect, risk, idempotency strategy, and verification criteria.
- Approval and rejection are auditable. Neither decision executes the proposed action.
- Regression tests for reconciliation, diagnosis validation, and recovery proposal rules.
- CI on Phase 3 pushes and pull requests targeting Phase 3.

## Local configuration

Optional environment variables in `backend/.env`:

```dotenv
AI_API_KEY=
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile
```

If `AI_API_KEY` is absent, diagnosis uses the deterministic fallback. Keep provider credentials on the backend only; never expose them in frontend variables or commit them.

## API workflow

1. Collect evidence:

   `GET /api/agent-tools/investigate/{incident_id}?customer_session=...`

2. Generate and persist diagnosis:

   `POST /api/agent-tools/diagnose/{incident_id}?customer_session=...`

3. Generate a recovery proposal and pending approval record:

   `POST /api/recovery/propose/{incident_id}?customer_session=...`

4. Record a demo operator decision:

   `POST /api/recovery/plans/{plan_id}/decision`

   JSON body:

   ```json
   {
     "customer_session": "same-browser-session",
     "decided_by": "operator-display-name",
     "decision": "approved",
     "reason": "Reviewed the evidence and accepted the proposed next step."
   }
   ```

   Use `rejected` to decline the proposal. A decision is one-time and audited.

## Safety and limitations

- LLM output is untrusted advisory content. It cannot execute SQL, invoke payment/carrier APIs, or change business state.
- Only collected finding codes can be referenced by a diagnosis. Invalid output falls back to deterministic rules.
- No payment retry, refund, stock adjustment, or shipment creation is implemented by this phase.
- Approval endpoint records a demo attestation only. There is no authenticated operator identity, and the endpoint must not be treated as a production authorization boundary.
- Do not expose the demo approval API publicly as a production control until real operator authentication/authorization is designed and reviewed.
- Existing seeded carrier failures remain simulated. No live carrier feed or physical parcel tracking is introduced.
- Razorpay remains Test Mode.
- No customer accounts, login, or RBAC are added.
- Uses existing `evidence`, `recovery_plans`, `approvals`, and `audit_log` tables from the bootstrap schema; this phase adds no database migration.

## Validation

From `backend`:

```bash
PYTHONPATH=. pytest tests -q
python -m compileall -q app
```

CI additionally runs frontend tests and the production frontend build.
