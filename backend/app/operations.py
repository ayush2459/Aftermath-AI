from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .db import get_db

router = APIRouter(prefix="/api/operations", tags=["Internal operations"])

@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    metrics = db.execute(text("SELECT COUNT(*) FILTER (WHERE status NOT IN ('resolved','closed')) AS open_incidents, COUNT(*) FILTER (WHERE severity='high' AND status NOT IN ('resolved','closed')) AS high_severity FROM incidents")).mappings().one()
    rows = db.execute(text("SELECT i.incident_id, i.order_id, i.status, i.severity, i.title, i.summary, i.created_at, i.updated_at, o.status AS order_status, p.status AS payment_status, s.status AS shipment_status FROM incidents i JOIN orders o ON o.order_id=i.order_id LEFT JOIN payments p ON p.order_id=o.order_id LEFT JOIN shipments s ON s.order_id=o.order_id ORDER BY i.updated_at DESC LIMIT 100")).mappings().all()
    return {"metrics": dict(metrics), "incidents": [dict(row) for row in rows]}
