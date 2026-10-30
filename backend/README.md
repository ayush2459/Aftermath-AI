# Aftermath AI — Backend starter

FastAPI backend for the hackathon e-commerce recovery demo. It uses PostgreSQL and creates a deterministic seeded shipping failure after a simulated payment.

## Requirements
- Python 3.11+
- PostgreSQL 14+ (tested in the working setup with PostgreSQL 18)
- Database created and schema applied using `../database/schema.sql`

## Windows PowerShell setup
```powershell
cd backend
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```
Set `DATABASE_URL` in `.env`; never commit that file. If your password includes URL-reserved characters, URL-encode them.

## Run
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Open `/health`, `/api/products`, and `/docs` on `http://127.0.0.1:8000`.

## Demo order
```json
{
  "customer_session": "demo-session-001",
  "items": [
    {"product_id": "aurora-headphones", "quantity": 1},
    {"product_id": "nova-speaker", "quantity": 1}
  ]
}
```

The API records a simulated captured payment, inventory reservation, and a deliberately failed shipment/incident. It does not connect to a real payment provider. The next stages (agent execution, human approval UI, SSE, Discord/Switch integration, and automated recovery runner) are not included in this starter.

## Local product photos
Five JPEG photographs are bundled in `static/products/` and served by FastAPI under `/static/products/<product-id>.jpg`. Once the database schema is loaded, run the image URL update script from the repository root:
```powershell
psql -U postgres -d aftermath_ai -f .\database\update_product_images.sql
```
Check `GET /api/products` for each returned `image_url`, or open `http://127.0.0.1:8000/static/products/aurora-headphones.jpg` directly.

## Safety
Demo data only. Do not submit real payment details or use this starter to execute real fulfilment operations. Keep `.env` and database backups out of source control.


## Razorpay Test Mode integration

The real checkout flow is exposed separately from the legacy simulated demo endpoint:

- `POST /api/payments/razorpay/orders` — accepts the same `OrderCreateIn` body as the demo order route, creates a local `payment_pending` order, then creates a Razorpay Test Mode order. Returns `key_id`, `razorpay_order_id`, amount in paise, and the local `order_id`.
- Open Razorpay Standard Checkout in the frontend with the returned key/order/amount.
- `POST /api/payments/razorpay/verify` — send `order_id`, `razorpay_order_id`, `razorpay_payment_id`, and `razorpay_signature`. The backend verifies the signature, fetches the payment from Razorpay, checks order/amount/currency and requires captured status.
- Only after verification does the backend reserve stock, mark the payment captured, and create the seeded shipping incident for Aftermath AI.

### Configure Test Mode keys

1. In the Razorpay Dashboard, switch to **Test Mode**.
2. Go to **Account & Settings → API Keys** and generate a test key pair.
3. Copy the Key ID and Key Secret into your local `backend/.env` as `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`. Never commit `.env` or share the secret in chat.
4. Keep `RAZORPAY_MODE=test`. This backend intentionally refuses payment creation if mode is not `test`.
5. Apply the migration once:
   ```powershell
   psql -U postgres -d aftermath_ai -f .\\database\\razorpay_test_mode_migration.sql
   ```
6. Install the updated requirements and restart FastAPI:
   ```powershell
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

### Test with the API

Create a Razorpay order:
```http
POST http://127.0.0.1:8000/api/payments/razorpay/orders
Content-Type: application/json

{
  "customer_session": "razorpay-test-session-001",
  "items": [{"product_id": "aurora-headphones", "quantity": 1}]
}
```

Use the returned values to open Checkout in the browser. On successful Checkout, post its three Razorpay callback values plus the returned local `order_id` to `/api/payments/razorpay/verify`. Use Razorpay's official Test Mode card/UPI test values shown in its Dashboard/docs; no real money is deducted.

**Important:** Enable automatic payment capture in Razorpay Test Mode. The verify endpoint deliberately refuses to mark an order paid unless Razorpay reports the payment as `captured`. Do not use the old `POST /api/orders` endpoint for checkout testing; it remains a simulated-payment demo route.


## Agent-facing shipment business tools

These endpoints expose narrow shipment operations rather than database access or the full backend. Every tool takes an `order_id` UUID query parameter:

| Tool | Endpoint | Purpose |
|---|---|---|
| `get_shipment` | `GET /api/agent-tools/get_shipment` | Shipment record and order context |
| `get_shipment_status` | `GET /api/agent-tools/get_shipment_status` | Current shipment lifecycle status |
| `get_shipment_timeline` | `GET /api/agent-tools/get_shipment_timeline` | Recorded order/shipment events, oldest first |
| `get_shipment_location` | `GET /api/agent-tools/get_shipment_location` | Latest stored location, if available |
| `get_shipment_eta` | `GET /api/agent-tools/get_shipment_eta` | Estimated delivery timestamp, if available |
| `get_carrier_details` | `GET /api/agent-tools/get_carrier_details` | Carrier and tracking references, if available |
| `get_shipment_issues` | `GET /api/agent-tools/get_shipment_issues` | Failed/delayed/exception events and shipment error |

Example:
```http
GET /api/agent-tools/get_shipment_status?order_id=<order-uuid>
```

The existing `events` table powers the timeline and issue history. The shipment table gains nullable carrier, tracking, location, and ETA fields; null means the carrier has not supplied that information (the seeded demo failure has no real tracking data). Apply the migration to an existing database:

```powershell
psql -U postgres -d aftermath_ai -f .\\database\\shipment_agent_tools_migration.sql
```

For a fresh database, the new columns are also included in `database/schema.sql`. These read-only tools do not fabricate a location or ETA and return HTTP 404 when the order has no shipment.
