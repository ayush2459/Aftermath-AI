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
