import json
import logging
import urllib.request
import urllib.error

from sqlalchemy import text
from .config import DISCORD_WEBHOOK_URL, DISCORD_ALERT_TIMEOUT

logger = logging.getLogger(__name__)


def dispatch_discord_alert(db, incident_id):
    if not DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook is not configured.")
        return False

    try:
        # Claim the notification so concurrent requests do not send duplicates.
        claimed = db.execute(text("""
            UPDATE notification_deliveries
            SET status = 'sending',
                attempts = attempts + 1,
                last_error = NULL,
                updated_at = NOW()
            WHERE incident_id = :incident_id
              AND (
                    status IN ('pending', 'failed')
                    OR (
                        status = 'sending'
                        AND updated_at < NOW() - INTERVAL '5 minutes'
                    )
              )
            RETURNING incident_id
        """), {"incident_id": incident_id}).first()

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
            "description": details["summary"] or reason,
            "color": 15158332,
            "fields": [
                {"name": "Severity", "value": str(details["severity"]), "inline": True},
                {"name": "Incident", "value": str(details["incident_status"]), "inline": True},
                {"name": "Order", "value": str(details["order_status"]), "inline": True},
                {"name": "Shipment", "value": str(details["shipment_status"] or "Unknown"), "inline": True},
                {"name": "Order Value", "value": f"₹{details['total_paise'] / 100:.2f}", "inline": True},
                {"name": "Failure Reason", "value": str(reason)[:1024], "inline": False},
                {"name": "Order ID", "value": str(details["order_id"]), "inline": False},
                {"name": "Incident ID", "value": str(details["incident_id"]), "inline": False},
            ],
            "footer": {"text": "Aftermath AI • Incident monitoring"},
        }

        body = json.dumps({"embeds": [embed]}).encode("utf-8")
        request = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(
            request, timeout=DISCORD_ALERT_TIMEOUT
        ) as response:
            if response.status not in (200, 204):
                raise RuntimeError(
                    f"Discord returned HTTP {response.status}"
                )

        db.execute(text("""
            UPDATE notification_deliveries
            SET status = 'sent',
                sent_at = NOW(),
                last_error = NULL,
                updated_at = NOW()
            WHERE incident_id = :incident_id
        """), {"incident_id": incident_id})
        db.commit()

        logger.info("Discord alert sent for incident %s", incident_id)
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
                WHERE incident_id = :incident_id
            """), {
                "incident_id": incident_id,
                "error": str(exc)[:2000],
            })
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not update notification failure status")

        return False
