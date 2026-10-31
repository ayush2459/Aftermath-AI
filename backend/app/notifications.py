import json
import logging
import urllib.request
from urllib.error import HTTPError, URLError

from sqlalchemy import text
from .config import (
    DISCORD_ALERT_TIMEOUT,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    DISCORD_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)


def _send_discord(payload):
    """Send a Discord message through the bot API or webhook fallback."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID:
        url = (
            f"https://discord.com/api/v10/channels/"
            f"{DISCORD_CHANNEL_ID}/messages"
        )
        headers = {
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "AftermathAI/1.0",
        }
    elif DISCORD_WEBHOOK_URL:
        url = DISCORD_WEBHOOK_URL
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AftermathAI/1.0",
        }
    else:
        logger.warning("Discord is not configured; notification remains pending.")
        return False

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=DISCORD_ALERT_TIMEOUT
        ) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(
                    f"Discord returned HTTP {response.status}"
                )
        return True

    except HTTPError as exc:
        # Discord's response body contains useful error codes/messages.
        # Never log request headers, tokens, or webhook URLs.
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "No response body available"

        logger.error(
            "Discord API rejected notification: HTTP %s; response: %s",
            exc.code,
            error_body[:1500],
        )
        raise RuntimeError(
            f"Discord returned HTTP {exc.code}: {error_body[:500]}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            f"Discord request failed: {exc.reason}"
        ) from exc


def dispatch_discord_alert(db, incident_id, notification_key="incident.created"):
    """Deliver one incident alert using the persistent notification outbox."""
    if not (
        (DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID)
        or DISCORD_WEBHOOK_URL
    ):
        logger.warning("Discord credentials are not configured.")
        return False

    dedupe_key = f"{incident_id}:{notification_key}"
    try:
        # Each logical event receives one durable, independently retryable outbox row.
        db.execute(text("""
            INSERT INTO notification_deliveries
                (incident_id, channel, status, dedupe_key)
            VALUES (:incident_id, 'discord', 'pending', :dedupe_key)
            ON CONFLICT (dedupe_key) DO NOTHING
        """), {"incident_id": incident_id, "dedupe_key": dedupe_key})
        db.commit()

        # Claim atomically to prevent concurrent duplicate sends.
        claimed = db.execute(text("""
            UPDATE notification_deliveries
            SET status = 'sending',
                attempts = attempts + 1,
                last_error = NULL,
                updated_at = NOW()
            WHERE dedupe_key = :dedupe_key
              AND attempts < 5
              AND (
                    (status = 'pending' AND updated_at <= NOW())
                    OR (
                        status = 'failed'
                        AND updated_at <= NOW() - make_interval(
                            secs => LEAST(900, 30 * POWER(2, GREATEST(attempts - 1, 0))::INTEGER)
                        )
                    )
                    OR (
                        status = 'sending'
                        AND updated_at < NOW() - INTERVAL '5 minutes'
                    )
              )
            RETURNING incident_id
        """), {"incident_id": incident_id, "dedupe_key": dedupe_key}).first()
        db.commit()

        if not claimed:
            return False

        details = db.execute(text("""
            SELECT
                i.incident_id,
                i.status AS incident_status,
                i.severity,
                i.title,
                i.summary,
                o.order_id,
                o.status AS order_status,
                o.total_paise,
                s.status AS shipment_status,
                s.last_error,
                (
                    SELECT e.message
                    FROM events e
                    WHERE e.incident_id = i.incident_id
                    ORDER BY e.created_at DESC
                    LIMIT 1
                ) AS latest_event
            FROM incidents i
            JOIN orders o ON o.order_id = i.order_id
            LEFT JOIN shipments s ON s.order_id = o.order_id
            WHERE i.incident_id = :incident_id
        """), {"incident_id": incident_id}).mappings().first()

        if not details:
            raise ValueError("Incident not found.")

        reason = (
            details["latest_event"]
            or details["last_error"]
            or details["summary"]
            or "No failure details available"
        )
        embed = {
            "title": f"🚨 Aftermath AI: {details['title']}",
            "description": (details["summary"] or reason or "Incident requires attention")[:4096],
            "color": 15158332,
            "fields": [
                {"name": "Severity", "value": str(details["severity"])[:1024], "inline": True},
                {"name": "Incident", "value": str(details["incident_status"])[:1024], "inline": True},
                {"name": "Order", "value": str(details["order_status"])[:1024], "inline": True},
                {"name": "Shipment", "value": str(details["shipment_status"] or "Unknown")[:1024], "inline": True},
                {"name": "Order Value", "value": f"₹{details['total_paise'] / 100:.2f}", "inline": True},
                {"name": "Failure Reason", "value": str(reason)[:1024], "inline": False},
                {"name": "Order ID", "value": str(details["order_id"])[:1024], "inline": False},
                {"name": "Incident ID", "value": str(details["incident_id"])[:1024], "inline": False},
            ],
            "footer": {"text": "Aftermath AI • Incident monitoring"},
        }

        _send_discord({"embeds": [embed]})

        db.execute(text("""
            UPDATE notification_deliveries
            SET status = 'sent',
                sent_at = NOW(),
                last_error = NULL,
                updated_at = NOW()
            WHERE dedupe_key = :dedupe_key
        """), {"incident_id": incident_id, "dedupe_key": dedupe_key})
        db.commit()
        logger.info("Discord alert sent for incident %s (%s)", incident_id, notification_key)
        return True

    except Exception as exc:
        db.rollback()
        logger.exception("Discord alert failed for incident %s", incident_id)
        try:
            db.execute(text("""
                UPDATE notification_deliveries
                SET status = 'failed',
                    last_error = :error,
                    updated_at = NOW()
                WHERE dedupe_key = :dedupe_key
            """), {
                "incident_id": incident_id,
                "dedupe_key": dedupe_key,
                "error": str(exc)[:2000],
            })
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not update notification failure status")
        return False
