import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/aftermath_ai",
)

LOCAL_CORS_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (3000, 5173, 5174, 5176)
]


def cors_origins(configured: str) -> list[str]:
    """Keep the local test storefront reachable alongside configured origins."""
    return list(dict.fromkeys([
        *LOCAL_CORS_ORIGINS,
        *(origin.strip() for origin in configured.split(",") if origin.strip()),
    ]))


CORS_ORIGINS = cors_origins(os.getenv("CORS_ORIGINS", ""))

RAZORPAY_MODE = os.getenv("RAZORPAY_MODE", "test").lower()
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Keep this secret in backend/.env. Never expose it to the frontend.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_ALERT_TIMEOUT = float(os.getenv("DISCORD_ALERT_TIMEOUT", "8"))
