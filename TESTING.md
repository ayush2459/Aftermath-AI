# Testing Aftermath AI

Run these checks from a local checkout with Python 3.11+, Node.js/npm, and PostgreSQL available. The repository does not currently define a `pytest` suite or an `npm test` script; the checks below are the available validation steps.

## Setup

Follow the [root README](README.md#getting-started) to create the `aftermath_ai` database, apply `database/schema.sql`, install `backend/requirements.txt`, and configure `backend/.env` and `frontend/.env` from their example files. Use a disposable database and Razorpay **Test Mode** credentials. Keep `.env` files and payment secrets out of commits.

## Static checks

From the repository root, run the backend syntax check:

```powershell
cd backend
python -m compileall app
cd ..
```

Build the frontend:

```powershell
cd frontend
npm install
npm run build
cd ..
```

These checks catch Python syntax errors and frontend build failures. They do not exercise database or payment behavior.

## API smoke check

Start the backend from `backend/`:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, check that the database is connected and seeded products are available:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/products
```

`/health` should report a healthy database connection, and `/api/products` should return the seeded catalogue. Open `http://127.0.0.1:8000/docs` to inspect request and response schemas.

## Checkout and shipment flow

With the backend and frontend running, use a Razorpay Test Mode checkout and test payment details. Confirm that the storefront receives products, creates a pending order, and shows a verified result after successful checkout. Use the returned local order UUID with the read-only shipment endpoints, for example:

```powershell
$orderId = '<local-order-uuid>'
Invoke-RestMethod "http://127.0.0.1:8000/api/agent-tools/get_shipment_status?order_id=$orderId"
Invoke-RestMethod "http://127.0.0.1:8000/api/agent-tools/get_shipment_issues?order_id=$orderId"
```

The demo intentionally records a shipment failure and an incident after a verified test payment. Check that the shipment status and issue response reflect that failure. A nonexistent order or an order without a shipment should return HTTP 404 from the shipment tools. Use only test payment details; this flow depends on a configured Razorpay Test Mode account and automatic payment capture.

Record which checks ran and their results in each pull request. Do not report the optional checkout flow as verified unless it was completed against a disposable database and Test Mode account.

