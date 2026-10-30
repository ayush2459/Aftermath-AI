# Aftermath AI

Backend and PostgreSQL database starter for the Aftermath AI hackathon MVP.

## Repository layout
- `backend/` — FastAPI application and locally bundled product photos.
- `database/schema.sql` — PostgreSQL schema and demo seed records.
- `database/update_product_images.sql` — assigns local image paths to seeded products.

## Security
- Never commit `.env`, database passwords, API keys, access tokens, production customer data, or database dumps.
- Payments in this demo are simulated; no real payment provider is connected.
- Use synthetic/demo data only.

See `backend/README.md` for Windows setup and API usage.
