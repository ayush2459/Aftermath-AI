from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .db import get_db

router = APIRouter(prefix="/api/operations", tags=["Internal operations"])

@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    metrics = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM incidents WHERE status NOT IN ('resolved','closed')) AS open_incidents,
          (SELECT COUNT(*) FROM incidents WHERE severity='high' AND status NOT IN ('resolved','closed')) AS high_severity,
          (SELECT COUNT(*) FROM approvals WHERE status='pending') AS pending_approvals,
          (SELECT COUNT(*) FROM recovery_plans WHERE status='proposed') AS proposed_plans,
          (SELECT COUNT(*) FROM recovery_actions WHERE status='completed') AS completed_recoveries
    """)).mappings().one()
    rows = db.execute(text("SELECT i.incident_id, i.order_id, i.status, i.severity, i.title, i.summary, i.created_at, i.updated_at, o.status AS order_status, p.status AS payment_status, s.status AS shipment_status FROM incidents i JOIN orders o ON o.order_id=i.order_id LEFT JOIN payments p ON p.order_id=o.order_id LEFT JOIN shipments s ON s.order_id=o.order_id ORDER BY i.updated_at DESC LIMIT 100")).mappings().all()
    return {"metrics": dict(metrics), "incidents": [dict(row) for row in rows]}

@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, db: Session = Depends(get_db)):
    incident = db.execute(text("""
        SELECT i.incident_id, i.order_id, i.status, i.severity, i.title, i.summary,
               i.correlation_id, i.created_at, i.updated_at, o.status AS order_status,
               o.total_paise, o.currency, p.status AS payment_status,
               s.status AS shipment_status, s.last_error, s.provider_ref,
               s.tracking_number, s.carrier_name
        FROM incidents i JOIN orders o ON o.order_id=i.order_id
        LEFT JOIN payments p ON p.order_id=o.order_id
        LEFT JOIN shipments s ON s.order_id=o.order_id
        WHERE i.incident_id=:incident_id
    """), {"incident_id": incident_id}).mappings().first()
    if not incident:
        return {"incident": None, "plans": [], "events": [], "audit": []}
    plans = db.execute(text("""
        SELECT rp.plan_id, rp.status, rp.plan, rp.created_at,
               a.approval_id, a.status AS approval_status, a.requested_by,
               a.decided_by, a.decision_reason, a.decided_at
        FROM recovery_plans rp LEFT JOIN approvals a ON a.plan_id=rp.plan_id
        WHERE rp.incident_id=:incident_id ORDER BY rp.created_at DESC
    """), {"incident_id": incident_id}).mappings().all()
    events = db.execute(text("""
        SELECT event_id, source, event_type, severity, message, payload, created_at
        FROM events WHERE incident_id=:incident_id
        ORDER BY created_at DESC, event_id DESC LIMIT 100
    """), {"incident_id": incident_id}).mappings().all()
    audit = db.execute(text("""
        SELECT actor_type, actor_id, action, decision, reason, details, created_at
        FROM audit_log WHERE incident_id=:incident_id
        ORDER BY created_at DESC, audit_id DESC LIMIT 100
    """), {"incident_id": incident_id}).mappings().all()
    return {"incident": dict(incident), "plans": [dict(row) for row in plans],
            "events": [dict(row) for row in events], "audit": [dict(row) for row in audit]}
