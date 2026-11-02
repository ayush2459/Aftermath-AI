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

# Discord secrets stay server-side. Prefer bot API; webhook remains supported as fallback.
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_ALERT_TIMEOUT = float(os.getenv("DISCORD_ALERT_TIMEOUT", "8"))

# Switch-hosted Discord recovery agent. This shared secret is used only between
# the backend and the separately running Switch agent client.
DISCORD_RECOVERY_AGENT_KEY = os.getenv("DISCORD_RECOVERY_AGENT_KEY", "").strip()
DISCORD_SUPPORT_INVITE_URL = os.getenv(
    "DISCORD_SUPPORT_INVITE_URL", "https://discord.gg/6sCDwusbw"
).strip()
PUBLIC_FRONTEND_URL = os.getenv("PUBLIC_FRONTEND_URL", "http://localhost:5173").rstrip("/")
