# Aftermath AI
### Resilient commerce. Intelligent recovery. Minimal disruption.

Aftermath AI is a resilient-commerce platform concept designed to help e-commerce teams respond when a transaction succeeds but a downstream operation—such as inventory allocation, order processing, or shipment creation—fails.

The project demonstrates the critical **payment-to-recovery journey**: a customer places an order, the payment provider confirms the transaction, the backend verifies it, and a shipment failure is recorded as an incident that can be investigated through structured APIs.

> **Current build:** React storefront · FastAPI backend · PostgreSQL · Razorpay Test Mode · shipment investigation APIs  
> **Demo scope:** The shipment failure is deliberately seeded after a verified test payment. This repository is a development/hackathon demo, not a live fulfilment or production payment system.

---

## Contents

- [Why Aftermath AI?](#-why-aftermath-ai)
- [Product vision](#-product-vision)
- [How the current demo works](#-how-the-current-demo-works)
- [Capabilities](#-capabilities)
- [Architecture](#-architecture)
- [Technology stack](#-technology-stack)
- [Repository structure](#-repository-structure)
- [Getting started](#-getting-started)
- [Environment configuration](#-environment-configuration)
- [API reference](#-api-reference)
- [Database model](#-database-model)
- [Security and reliability](#-security-and-reliability)
- [Roadmap](#-roadmap)
- [Testing and validation](#-testing-and-validation)
- [Limitations](#-limitations)
- [Contributing](#-contributing)

---

## 🚨 Why Aftermath AI?

A successful payment does not guarantee a successful order.

Consider this scenario:

1. A customer places an order on an e-commerce website.
2. The payment provider captures the payment.
3. The order moves to its next processing stage.
4. A downstream service fails—for example, the carrier allocation request times out.
5. The customer has paid, but the shipment has not been created.

This creates an operational and customer-experience problem. Teams need to identify what failed, gather the right evidence, understand the impact, and decide what action is safe.

**Aftermath AI is being developed around that recovery gap:** connect operational signals, investigate incidents, guide recovery decisions, and make the process observable and auditable.

## 🎯 Product vision

The intended platform evolves from a commerce recovery demo into an AI-assisted incident investigation and recovery layer that can integrate with existing e-commerce applications.

The broader experience is planned around:

- **Event-aware incident detection** — identify failures across payment, order, inventory, and fulfilment workflows.
- **Contextual investigation** — collect relevant order data, service events, shipment status, logs, and other approved evidence.
- **AI-assisted diagnosis** — summarize the incident, identify likely causes, and explain the impact using available evidence.
- **Recovery planning** — propose practical next steps and identify actions that need human approval.
- **Controlled execution** — run permitted recovery actions through explicitly defined tools and integrations.
- **Human oversight** — keep sensitive or irreversible decisions reviewable and approval-driven.
- **Auditability** — retain event history, decisions, action results, and correlation identifiers.

These are product goals, not a claim that every capability is already implemented. The current implementation and planned work are separated below.

## 🔄 How the current demo works

```mermaid
flowchart TD
    A[Customer visits React storefront] --> B[Select products and build cart]
    B --> C[FastAPI creates local pending order]
    C --> D[Razorpay Test Mode order created]
    D --> E[Razorpay Standard Checkout]
    E --> F[Checkout returns payment details]
    F --> G[Backend verifies signature and fetches payment]
    G --> H{Order, amount, currency and capture valid?}
    H -- No --> I[Reject verification / keep order unresolved]
    H -- Yes --> J[Mark payment captured and update order]
    J --> K[Reserve inventory]
    K --> L[Seed shipment allocation failure]
    L --> M[Create incident, event and audit record]
    M --> N[Inspect shipment through agent-facing APIs]
```

### End-to-end flow

1. The React storefront retrieves active products from the FastAPI API.
2. A customer adds products to the cart and starts checkout.
3. The backend validates the requested products and available stock, creates a local pending order, and creates a Razorpay Test Mode order.
4. Razorpay Standard Checkout handles the test payment.
5. The frontend sends the returned Razorpay order ID, payment ID, signature, and local order ID to the backend.
6. The backend verifies the payment signature and fetches the payment from Razorpay. It checks the linked order, amount, currency, and captured status.
7. Only after successful verification does the backend finalize the local payment, decrement inventory, and update the order.
8. The demo deliberately creates a failed shipment record, an open incident, an event, and an audit entry.
9. The shipment investigation APIs expose the recorded state for inspection.

## ✨ Capabilities

### Implemented in the current repository

| Area | Current capability |
|---|---|
| Storefront | React + Vite product catalogue, product images, cart quantity controls, order summary |
| Backend API | FastAPI application, health endpoint, product listing, legacy simulated order endpoint |
| Database | PostgreSQL schema for products, orders, items, payments, reservations, shipments, incidents, events, evidence, recovery plans, approvals, recovery actions, and audit records |
| Payment | Razorpay Standard Checkout integration in Test Mode |
| Verification | Server-side signature verification and provider-side payment lookup; order, amount, currency, and captured-status checks |
| Inventory | Stock validation and inventory reservation records during payment finalization |
| Incident creation | Seeded shipment failure, incident record, event record, and audit entry after verified test payment |
| Investigation APIs | Shipment record, status, timeline, location, ETA, carrier details, and issue endpoints |
| Product assets | Product photographs served by FastAPI static files |
| API discovery | Interactive FastAPI documentation through Swagger UI |

### Planned capabilities

The following are part of the intended product direction and should be treated as roadmap items until their code and integrations are added:

- AI investigation agent for multi-source incident analysis.
- Structured log ingestion and correlation across services.
- Automated root-cause hypotheses with evidence references and confidence indicators.
- Recovery-plan generation with risk and impact assessment.
- Human approval and operator review interface.
- Recovery action execution with idempotency, retries, and rollback/compensation strategies.
- Real carrier, shipping, inventory, and commerce-platform integrations.
- Real-time incident updates using WebSockets or Server-Sent Events.
- Discord or other collaboration-platform entry points for incident handoff.
- A secure integration/onboarding experience for connecting a merchant's backend.
- Operational dashboard for incidents, timelines, approvals, actions, and outcomes.
- Metrics, monitoring, alerting, and deployment hardening.

## 🏗️ Architecture

### Current high-level architecture

```mermaid
flowchart LR
    U[Customer] --> FE[React + Vite Storefront]
    FE --> API[FastAPI Backend]
    API --> DB[(PostgreSQL)]
    API --> RZ[Razorpay Test Mode]
    API --> STATIC[Product Static Assets]
    API --> TOOLS[Shipment Investigation APIs]
    TOOLS --> DB
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| React storefront | Product discovery, cart interactions, checkout initiation, payment result display |
| FastAPI backend | API endpoints, validation, payment orchestration, verification, incident and shipment records |
| PostgreSQL | Persistent commerce, payment, inventory, shipment, incident, event, recovery, and audit data |
| Razorpay Test Mode | Test order creation and payment checkout |
| Shipment agent tools | Narrow read-only APIs that expose shipment and event context |
| Static assets | Product images served from the backend |

### Intended recovery architecture

The longer-term architecture is expected to introduce event ingestion, an investigation/orchestration layer, AI reasoning with structured outputs, policy checks, approval workflows, and controlled action adapters. These components should interact through explicit contracts rather than unrestricted database or infrastructure access.

## 🧰 Technology stack

| Layer | Technologies |
|---|---|
| Frontend | React 18, Vite, JavaScript, Lucide React |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic |
| Database | PostgreSQL, SQLAlchemy, psycopg |
| Payments | Razorpay Standard Checkout — Test Mode |
| API documentation | OpenAPI / Swagger UI |
| Configuration | Environment variables, python-dotenv |
| Version control | Git and GitHub |

## 📁 Repository structure

```text
Aftermath-AI/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, products, orders, health
│   │   ├── config.py               # Environment-based configuration
│   │   ├── db.py                   # Database session management
│   │   ├── schemas.py              # Request and response models
│   │   ├── payments.py             # Razorpay order and verification routes
│   │   └── shipments.py            # Shipment investigation tool routes
│   ├── static/
│   │   └── products/               # Storefront product photographs
│   ├── .env.example
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Storefront and checkout experience
│   │   └── ...
│   ├── .env.example
│   ├── package.json
│   └── README.md
├── database/
│   ├── schema.sql                  # Fresh database schema and seed products
│   ├── update_product_images.sql
│   ├── razorpay_test_mode_migration.sql
│   └── shipment_agent_tools_migration.sql
└── README.md
```

## 🚀 Getting started

### Prerequisites

- Git
- Python 3.11 or later
- Node.js and npm
- PostgreSQL 14 or later
- Razorpay account with **Test Mode** API keys

### 1. Clone the repository

```powershell
git clone https://github.com/ayush2459/Aftermath-AI.git
cd Aftermath-AI
```

### 2. Create the PostgreSQL database

Open PostgreSQL or use PowerShell:

```sql
CREATE DATABASE aftermath_ai;
```

Apply the bootstrap schema from the repository root:

```powershell
psql -U postgres -d aftermath_ai -f .\database\schema.sql
```

The schema creates the core commerce and recovery-oriented tables and seeds the demo products.

For an existing database, apply the relevant migrations in order when they have not already been applied:

```powershell
psql -U postgres -d aftermath_ai -f .\database\razorpay_test_mode_migration.sql
psql -U postgres -d aftermath_ai -f .\database\shipment_agent_tools_migration.sql
psql -U postgres -d aftermath_ai -f .\database\update_product_images.sql
```

Do not blindly re-run migrations without checking their contents and whether they are safe to repeat.

### 3. Configure and start the backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` with your local database connection and Razorpay **Test Mode** credentials. See [Environment configuration](#-environment-configuration).

Start FastAPI:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URLs:

- API root: http://127.0.0.1:8000/
- Health check: http://127.0.0.1:8000/health
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

Keep this terminal running.

### 4. Configure and start the frontend

Open a second PowerShell terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev -- --host 127.0.0.1 --port 5176
```

Open http://127.0.0.1:5176.

If you use a different frontend origin, add that exact origin to the backend `CORS_ORIGINS` setting and restart FastAPI.

### 5. Verify product images

The backend serves product assets from `/static`. For example:

http://127.0.0.1:8000/static/products/aurora-headphones.jpg

The product records should use image paths such as `/static/products/aurora-headphones.jpg`. Check `GET /api/products` if an image is missing.

## 🔐 Environment configuration

Keep secrets in local environment files. Never commit `.env` files or paste secret values into issues, pull requests, screenshots, or chat.

### Backend — `backend/.env`

Use the tracked `backend/.env.example` as the source of truth for variable names. The application expects:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL SQLAlchemy connection URL |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins |
| `RAZORPAY_MODE` | Must remain `test` for this demo |
| `RAZORPAY_KEY_ID` | Public Razorpay Test Mode Key ID |
| `RAZORPAY_KEY_SECRET` | Private Razorpay Test Mode Key Secret; backend only |

Example format (replace placeholders locally):

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/aftermath_ai
CORS_ORIGINS=http://localhost:5176,http://127.0.0.1:5176
RAZORPAY_MODE=test
RAZORPAY_KEY_ID=your_test_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
```

If your database password contains URL-reserved characters, URL-encode them in the connection URL.

### Frontend — `frontend/.env`

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Only public configuration belongs in frontend environment variables. Vite exposes `VITE_*` variables to browser code, so **never put the Razorpay Key Secret or database credentials in the frontend**.

## 📡 API reference

The running Swagger UI at http://127.0.0.1:8000/docs is the definitive interactive reference.

### Core API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | API information and documentation links |
| `GET` | `/health` | Database connectivity health check |
| `GET` | `/api/products` | List active products |
| `POST` | `/api/orders` | Legacy simulated order and seeded failure flow |

### Razorpay payment API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/payments/razorpay/orders` | Validate cart, create local pending order and Razorpay Test Mode order |
| `POST` | `/api/payments/razorpay/verify` | Verify checkout signature and provider payment details, then finalize the demo order |

The verification request contains:

```json
{
  "order_id": "LOCAL_ORDER_UUID",
  "razorpay_order_id": "order_from_razorpay",
  "razorpay_payment_id": "payment_from_checkout",
  "razorpay_signature": "signature_from_checkout"
}
```

The values above are placeholders. Use the actual response from the order-creation endpoint and Razorpay Checkout.

### Shipment investigation tools

Every endpoint below expects an `order_id` UUID query parameter.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/agent-tools/get_shipment` | Shipment record and associated order context |
| `GET` | `/api/agent-tools/get_shipment_status` | Shipment and order lifecycle status |
| `GET` | `/api/agent-tools/get_shipment_timeline` | Chronological event history |
| `GET` | `/api/agent-tools/get_shipment_location` | Latest stored shipment location, if available |
| `GET` | `/api/agent-tools/get_shipment_eta` | Carrier-provided estimated delivery time, if available |
| `GET` | `/api/agent-tools/get_carrier_details` | Carrier and tracking details, if available |
| `GET` | `/api/agent-tools/get_shipment_issues` | Failure, delay, exception, and shipment error details |

These are read-only business tools. They do not invent a carrier, location, tracking number, or ETA. A missing shipment returns HTTP 404.

## 🗄️ Database model

The PostgreSQL schema is designed to represent both the commerce transaction and the recovery lifecycle.

| Table | Purpose |
|---|---|
| `products` | Product catalogue, pricing, stock, and image references |
| `orders` | Customer order and lifecycle status |
| `order_items` | Products and quantities associated with an order |
| `payments` | Payment status, amount, provider references, and idempotency |
| `inventory_reservations` | Inventory held against an order |
| `shipments` | Shipment lifecycle, carrier metadata, tracking, location, and ETA |
| `incidents` | Operational incidents associated with orders |
| `events` | Timestamped operational events and correlation identifiers |
| `evidence` | Structured evidence collected for an incident |
| `recovery_plans` | Proposed recovery plans |
| `approvals` | Approval decisions associated with recovery plans |
| `recovery_actions` | Recovery action inputs, results, and execution status |
| `audit_log` | Actor, decision, reason, and details for auditable operations |

The schema includes UUID identifiers, foreign-key relationships, status constraints, JSONB fields for structured payloads, idempotency keys on selected operations, and indexes for common incident/event lookups.

The presence of a table in the schema does not mean its complete application workflow or UI is already implemented.

## 🛡️ Security and reliability principles

The current demo includes several important safeguards:

- Razorpay integration is restricted to Test Mode by backend configuration.
- The Razorpay Key Secret is read by the backend and is not returned to the browser.
- Payment verification checks the provider signature and fetches the payment before local finalization.
- The backend validates the expected Razorpay order, amount, currency, and captured status.
- Product stock is checked before order creation and re-checked while finalizing a verified payment.
- Database writes for payment finalization and incident creation are grouped transactionally.
- Selected records use unique idempotency keys and database constraints.
- Shipment investigation endpoints expose specific business data instead of direct database access.
- Missing carrier information is represented as unavailable rather than fabricated.
- Environment files and database credentials must remain outside source control.

For a production system, additional work is required: authentication and authorization, rate limiting, webhook signature verification and reconciliation, secrets management, stronger concurrency and retry handling, observability, data retention controls, deployment hardening, and security testing.

## 🧭 Roadmap

The roadmap below describes the intended direction; priorities may change as the prototype evolves.

### Phase 1 — Commerce foundation
- [x] React storefront and product catalogue
- [x] FastAPI backend and PostgreSQL schema
- [x] Razorpay Test Mode order creation
- [x] Server-side payment verification
- [x] Seeded shipment failure and incident creation
- [x] Shipment investigation APIs

### Phase 2 — Incident intelligence
- [ ] Ingest application and service logs
- [ ] Correlate events across order and service boundaries
- [ ] Build incident timeline and evidence collection
- [ ] Add AI-assisted investigation and root-cause summaries
- [ ] Return structured findings with evidence references

### Phase 3 — Recovery orchestration
- [ ] Generate recovery plans with risk and impact details
- [ ] Add approval and operator review workflows
- [ ] Implement safe, idempotent recovery action adapters
- [ ] Add retries, compensation, and reconciliation paths
- [ ] Record action outcomes in the audit trail

### Phase 4 — Integrations and collaboration
- [ ] Merchant backend integration and secure onboarding
- [ ] E-commerce, inventory, and carrier integrations
- [ ] Discord or collaboration-platform incident handoff
- [ ] Real-time incident updates and notifications

### Phase 5 — Production readiness
- [ ] Authentication, authorization, and tenant isolation
- [ ] Automated unit, integration, and end-to-end tests
- [ ] Metrics, logs, tracing, and alerting
- [ ] CI/CD, deployment environments, and secrets management
- [ ] Load, resilience, and security testing

## 🧪 Testing and validation

Useful local checks:

**Backend**
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m compileall app
```

**Frontend production build**
```powershell
cd frontend
npm install
npm run build
```

**API checks**
- Open `/health` and confirm the database reports connected.
- Open `/api/products` and confirm seeded products are returned.
- Use Swagger UI to inspect the payment and shipment tool endpoints.
- Use Razorpay Test Mode credentials and test payment details only.
- After a verified test payment, inspect the generated incident and shipment using the returned local order ID.

A successful frontend build or API response is not a substitute for a full end-to-end test. Payment and inventory scenarios should be tested against a non-production database.

## ⚠️ Current limitations

- Razorpay is configured for Test Mode; this project is not a live payment integration.
- The shipment failure is deliberately seeded to demonstrate the recovery investigation path.
- No live carrier shipment is created, and carrier location/ETA/tracking fields may be empty.
- The shipment endpoints currently provide read-only investigation data; they do not execute recovery actions.
- The AI investigation agent, automated recovery runner, approval UI, real-time event streaming, and external collaboration integrations are roadmap items.
- The repository should not be treated as production-ready until the security, reliability, testing, and operational work described above is completed.

## 🤝 Contributing

Contributions, bug reports, and thoughtful suggestions are welcome.

1. Fork the repository.
2. Create a focused feature branch.
3. Keep secrets, local databases, and generated environment files out of commits.
4. Add or update tests and documentation with behavior changes.
5. Open a pull request describing the change and how it was validated.

## 📄 License

No license is currently specified in this repository. Until a license is added, the default copyright restrictions apply; do not assume the code is open for reuse or redistribution.

---

<div align="center">

**Aftermath AI — because a successful checkout should not become an unresolved incident.**

Built as a resilient-commerce and AI-assisted recovery project.

</div>
