# Aftermath AI

A resilient-commerce demo with a React storefront, FastAPI backend, PostgreSQL persistence, Razorpay Test Mode checkout, and shipment recovery investigation tools.

## Repository layout
- `frontend/` — React + Vite storefront with cart and Razorpay Standard Checkout.
- `backend/` — FastAPI application, payment verification endpoints, shipment agent tools, and bundled product photos.
- `database/schema.sql` — PostgreSQL schema and demo seed records.
- `database/*_migration.sql` — migrations for existing databases.

## Run locally
1. Follow `backend/README.md` to configure PostgreSQL, backend dependencies, and local environment variables.
2. Start FastAPI at `http://127.0.0.1:8000`.
3. Follow `frontend/README.md` to install dependencies and start Vite at `http://localhost:5173`.

## Payment flow
The storefront creates an order through the backend, opens Razorpay Standard Checkout, then sends the checkout response to the backend for signature and payment-status verification. The backend only advances the order after verification. It then creates a seeded shipment failure incident so the recovery tools can be demonstrated.

## Security and demo scope
- Use Razorpay **Test Mode** keys and test payment details only. No real money is charged.
- Keep `.env`, database passwords, Razorpay Key Secret, access tokens, production customer data, and database dumps out of source control.
- The frontend receives only the public Razorpay Key ID; the Key Secret remains server-side.
- The shipment failure is deliberately seeded for demonstration; this is not a live carrier integration.

See `backend/README.md` and `frontend/README.md` for setup instructions.
