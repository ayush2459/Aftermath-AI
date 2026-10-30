# Aftermath AI storefront

React + Vite storefront connected to the existing FastAPI backend and Razorpay Standard Checkout (Test Mode).

## Run locally (Windows PowerShell)

Terminal 1 — backend:
```powershell
cd C:\Users\Ayush\Aftermath-AI\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:
```powershell
cd C:\Users\Ayush\Aftermath-AI\frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the Vite URL printed in the terminal (normally http://localhost:5173).

## Payment flow

1. The storefront loads the active products from `GET /api/products`.
2. The Pay button calls `POST /api/payments/razorpay/orders` with the selected cart.
3. Razorpay Standard Checkout opens with the server-created Razorpay order ID.
4. On checkout success, the browser sends the returned payment ID, order ID and signature plus the local order UUID to `POST /api/payments/razorpay/verify`.
5. The backend validates the signature and fetches the payment from Razorpay before marking it captured and creating the seeded shipment-failure incident.
6. The UI displays the verified order and links to the backend docs for inspecting the recovery tools.

The Key Secret remains on the backend only. The frontend receives only the public Razorpay Key ID. Use Test Mode keys and test payment details only. This demo does not take real payments or create a real carrier shipment.

## Configuration

Set `VITE_API_BASE_URL` in `.env` if the backend is not at `http://127.0.0.1:8000`. Backend CORS defaults already allow `http://localhost:5173` and `http://localhost:3000`.

Build check:
```powershell
npm run build
```
