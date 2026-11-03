"""Durable background GhostTrail investigation and Discord handoff worker.

Run alongside the existing notification worker:
    python -m app.ghosttrail_worker

Jobs are created in the same transaction as incident creation. The worker
collects evidence, persists an advisory diagnosis and recovery proposal, creates
a short-lived Discord case, and queues that case for Discord delivery. It never
approves or executes recovery.
"""
from __future__ import annotations

import json
import logging
import time
from uuid import UUID

from sqlalchemy import text

from .db import SessionLocal
from .investigation import diagnose_incident
from .recovery import propose_recovery
from .discord_recovery import CreateHandoffIn, create_handoff

logger = logging.getLogger("aftermath.ghosttrail_worker")
POLL_SECONDS = 5
BATCH_SIZE = 10
MAX_ATTEMPTS = 5


def process_job(db, job) -> dict:
    incident_id = UUID(str(job["incident_id"]))
    customer_session = job["customer_session"]

    diagnosis = diagnose_incident(
        incident_id=incident_id,
        customer_session=customer_session,
        db=db,
    )
    proposal = propose_recovery(
        incident_id=incident_id,
        customer_session=customer_session,
        db=db,
    )
    handoff = create_handoff(
        CreateHandoffIn(
            customer_session=customer_session,
            incident_id=incident_id,
            plan_id=UUID(str(proposal["plan_id"])),
        ),
        db=db,
    )
    return {
        "incident_id": str(incident_id),
        "plan_id": str(proposal["plan_id"]),
        "diagnosis_id": str(diagnosis["diagnosis_id"]),
        "diagnosis_provider": diagnosis["provider"],
        "case_code": handoff["case_code"],
        "expires_at": handoff["expires_at"].isoformat(),
        "order_id": str(job["order_id"]),
        "simulation_only": True,
    }


def claim_jobs(db, limit: int = BATCH_SIZE):
    rows = db.execute(text("""
        WITH due AS (
            SELECT job_id
            FROM ghosttrail_investigation_jobs
            WHERE attempts < :max_attempts
              AND (
                (status = 'pending' AND next_attempt_at <= NOW())
                OR (status = 'processing' AND updated_at < NOW() - INTERVAL '5 minutes')
              )
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT :batch_size
        )
        UPDATE ghosttrail_investigation_jobs j
        SET status = 'processing',
            attempts = j.attempts + 1,
            started_at = NOW(),
            updated_at = NOW(),
            last_error = NULL
        FROM due
        WHERE j.job_id = due.job_id
        RETURNING j.job_id, j.incident_id, j.customer_session, j.attempts
    """), {
        "max_attempts": MAX_ATTEMPTS,
        "batch_size": limit,
    }).mappings().all()
    db.commit()
    return [dict(row) for row in rows]


def run_once() -> tuple[int, int]:
    db = SessionLocal()
    try:
        jobs = claim_jobs(db)
        completed = 0
        for job in jobs:
            try:
                order = db.execute(text("""
                    SELECT order_id FROM incidents WHERE incident_id = :incident_id
                """), {"incident_id": job["incident_id"]}).mappings().first()
                if not order:
                    raise ValueError("Incident no longer exists.")

                result = process_job(db, {**job, "order_id": order["order_id"]})
                # The case code is a short-lived bearer credential. Keep it only
                # in the durable Discord outbox until successful delivery.
                db.execute(text("""
                    INSERT INTO notification_deliveries
                        (incident_id, channel, status, dedupe_key, payload)
                    VALUES (
                        :incident_id, 'discord', 'pending',
                        CAST(:incident_id AS TEXT) || ':ghosttrail.ready',
                        CAST(:payload AS JSONB)
                    )
                    ON CONFLICT (dedupe_key) DO NOTHING
                """), {
                    "incident_id": job["incident_id"],
                    "payload": json.dumps(result),
                })
                db.execute(text("""
                    UPDATE ghosttrail_investigation_jobs
                    SET status = 'completed', completed_at = NOW(),
                        updated_at = NOW(), last_error = NULL
                    WHERE job_id = :job_id
                """), {"job_id": job["job_id"]})
                db.execute(text("""
                    INSERT INTO audit_log (
                        incident_id, actor_type, actor_id, action, decision, reason, details
                    ) VALUES (
                        :incident_id, 'system', 'ghosttrail-worker',
                        'autonomous_investigation_completed', 'discord_handoff_queued',
                        'Background investigation, diagnosis, recovery proposal and Discord handoff were persisted. No recovery was approved or executed.',
                        CAST(:details AS JSONB)
                    )
                """), {
                    "incident_id": job["incident_id"],
                    "details": json.dumps({
                        "job_id": str(job["job_id"]),
                        "plan_id": result["plan_id"],
                        "diagnosis_id": result["diagnosis_id"],
                        "diagnosis_provider": result["diagnosis_provider"],
                        "simulation_only": True,
                        "execution_enabled": False,
                    }),
                })
                db.commit()
                completed += 1
            except Exception as exc:
                db.rollback()
                attempts = int(job["attempts"])
                terminal = attempts >= MAX_ATTEMPTS
                delay_seconds = min(900, 30 * (2 ** max(attempts - 1, 0)))
                db.execute(text("""
                    UPDATE ghosttrail_investigation_jobs
                    SET status = :status,
                        last_error = :error,
                        next_attempt_at = NOW() + make_interval(secs => :delay),
                        updated_at = NOW()
                    WHERE job_id = :job_id
                """), {
                    "status": "failed" if terminal else "pending",
                    "error": f"{type(exc).__name__}: {exc}"[:2000],
                    "delay": delay_seconds,
                    "job_id": job["job_id"],
                })
                db.execute(text("""
                    INSERT INTO audit_log (
                        incident_id, actor_type, actor_id, action, decision, reason, details
                    ) VALUES (
                        :incident_id, 'system', 'ghosttrail-worker',
                        'autonomous_investigation_attempt', :decision, :reason,
                        CAST(:details AS JSONB)
                    )
                """), {
                    "incident_id": job["incident_id"],
                    "decision": "failed" if terminal else "retry_scheduled",
                    "reason": "Background investigation attempt did not complete.",
                    "details": json.dumps({
                        "job_id": str(job["job_id"]),
                        "attempt": attempts,
                        "max_attempts": MAX_ATTEMPTS,
                    }),
                })
                db.commit()
                logger.exception(
                    "GhostTrail job %s failed on attempt %s/%s",
                    job["job_id"], attempts, MAX_ATTEMPTS,
                )
        return len(jobs), completed
    finally:
        db.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting durable GhostTrail investigation worker")
    while True:
        try:
            scanned, completed = run_once()
            if scanned:
                logger.info("Processed %s GhostTrail jobs; completed %s", scanned, completed)
        except Exception:
            logger.exception("GhostTrail worker iteration failed")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
