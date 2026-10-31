"""Poll the durable Discord outbox and retry due notifications.

Run with: python -m app.notification_worker
Use one worker instance per environment; row claiming is concurrency-safe.
"""
import logging
import time

from sqlalchemy import text

from .db import SessionLocal
from .notifications import dispatch_discord_alert

logger = logging.getLogger("aftermath.notification_worker")
POLL_SECONDS = 30
BATCH_SIZE = 25


def run_once():
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT incident_id, dedupe_key
            FROM notification_deliveries
            WHERE attempts < 5
              AND (
                    status = 'pending'
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
            ORDER BY updated_at ASC
            LIMIT :batch_size
        """), {"batch_size": BATCH_SIZE}).mappings().all()
        db.commit()
        delivered = 0
        for row in rows:
            # The event suffix is stored after the incident UUID and colon.
            notification_key = row["dedupe_key"].split(":", 1)[1]
            if dispatch_discord_alert(db, row["incident_id"], notification_key):
                delivered += 1
        return len(rows), delivered
    finally:
        db.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting Aftermath AI Discord outbox worker")
    while True:
        try:
            scanned, delivered = run_once()
            if scanned:
                logger.info("Scanned %s notifications; delivered %s", scanned, delivered)
        except Exception:
            logger.exception("Notification worker iteration failed")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
