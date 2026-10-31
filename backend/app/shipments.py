from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db

router = APIRouter(
    prefix="/api/agent-tools",
    tags=["Agent business tools"],
)


class CompleteSampleRecoveryIn(BaseModel):
    order_id: UUID
    customer_session: str = Field(min_length=1, max_length=128)


class CustomerSessionQuery(BaseModel):
    customer_session: str = Field(min_length=1, max_length=128)


def _shipment(db: Session, order_id: UUID):
    """Fetch the shipment and associated order details."""
    row = db.execute(
        text("""
            SELECT
                s.shipment_id,
                s.order_id,
                s.status,
                s.provider_ref,
                s.carrier_name,
                s.carrier_code,
                s.tracking_number,
                s.current_location,
                s.estimated_delivery_at,
                s.last_error,
                s.created_at,
                s.updated_at,
                o.status AS order_status
            FROM shipments s
            JOIN orders o ON o.order_id = s.order_id
            WHERE s.order_id = :order_id
        """),
        {"order_id": order_id},
    ).mappings().first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Shipment not found for this order.",
        )

    return dict(row)


@router.get("/get_shipment")
def get_shipment(
    order_id: UUID,
    customer_session: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    """Return the business-level shipment record for an order."""
    return _shipment(db, order_id)


@router.get("/get_shipment_status")
def get_shipment_status(
    order_id: UUID,
    customer_session: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    """Return the current shipment and order status."""
    shipment = _shipment(db, order_id)

    return {
        "order_id": str(order_id),
        "shipment_id": str(shipment["shipment_id"]),
        "status": shipment["status"],
        "order_status": shipment["order_status"],
        "last_updated_at": shipment["updated_at"],
    }


@router.get("/get_shipment_timeline")
def get_shipment_timeline(
    order_id: UUID,
    customer_session: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    """Return the chronological event history for an order."""
    shipment = _shipment(db, order_id)
    owner = db.execute(
        text("SELECT customer_session FROM orders WHERE order_id = :order_id"),
        {"order_id": order_id},
    ).scalar_one_or_none()
    if owner != customer_session:
        raise HTTPException(status_code=404, detail="Shipment not found for this customer.")

    rows = db.execute(
        text("""
            SELECT
                event_id,
                source,
                event_type,
                severity,
                message,
                payload,
                correlation_id,
                created_at AS occurred_at
            FROM events
            WHERE order_id = :order_id
            ORDER BY created_at ASC, event_id ASC
        """),
        {"order_id": order_id},
    ).mappings().all()

    return {
        "order_id": str(order_id),
        "events": [dict(row) for row in rows],
    }


@router.get("/get_shipment_location")
def get_shipment_location(
    order_id: UUID,
    db: Session = Depends(get_db),
):
    """Return the latest known shipment location."""
    shipment = _shipment(db, order_id)

    location = shipment["current_location"]

    return {
        "order_id": str(order_id),
        "location": location,
        "last_updated_at": (
            shipment["updated_at"] if location else None
        ),
        "available": location is not None,
    }


@router.get("/get_shipment_eta")
def get_shipment_eta(
    order_id: UUID,
    db: Session = Depends(get_db),
):
    """Return the estimated shipment delivery time."""
    shipment = _shipment(db, order_id)

    eta = shipment["estimated_delivery_at"]

    return {
        "order_id": str(order_id),
        "estimated_delivery_at": eta,
        "available": eta is not None,
        "note": (
            None if eta else "Carrier ETA has not been provided."
        ),
    }


@router.get("/get_carrier_details")
def get_carrier_details(
    order_id: UUID,
    db: Session = Depends(get_db),
):
    """Return carrier and tracking information."""
    shipment = _shipment(db, order_id)

    carrier_fields = (
        shipment["carrier_name"],
        shipment["carrier_code"],
        shipment["tracking_number"],
        shipment["provider_ref"],
    )

    return {
        "order_id": str(order_id),
        "carrier_name": shipment["carrier_name"],
        "carrier_code": shipment["carrier_code"],
        "tracking_number": shipment["tracking_number"],
        "provider_reference": shipment["provider_ref"],
        "available": any(carrier_fields),
    }


@router.get("/get_shipment_issues")
def get_shipment_issues(
    order_id: UUID,
    db: Session = Depends(get_db),
):
    """Return shipment-related failures and unresolved issues."""
    shipment = _shipment(db, order_id)

    rows = db.execute(
        text("""
            SELECT
                event_id,
                source,
                event_type,
                severity,
                message,
                payload,
                created_at AS occurred_at
            FROM events
            WHERE order_id = :order_id
              AND (
                    LOWER(severity) IN ('high', 'critical')
                    OR LOWER(event_type) LIKE '%fail%'
                    OR LOWER(event_type) LIKE '%delay%'
                    OR LOWER(event_type) LIKE '%exception%'
              )
            ORDER BY created_at DESC, event_id DESC
        """),
        {"order_id": order_id},
    ).mappings().all()

    issues = [dict(row) for row in rows]

    # Include the shipment error if it is not already represented
    # in the events table.
    if shipment["last_error"] and not any(
        issue.get("message") == shipment["last_error"]
        for issue in issues
    ):
        issues.insert(
            0,
            {
                "source": "shipment-service",
                "event_type": "shipment.last_error",
                "severity": (
                    "high"
                    if shipment["status"] == "failed"
                    else "warning"
                ),
                "message": shipment["last_error"],
                "occurred_at": shipment["updated_at"],
            },
        )

    return {
        "order_id": str(order_id),
        "shipment_status": shipment["status"],
        "has_unresolved_issue": (
            shipment["status"] in ("failed", "unknown")
            or bool(issues)
        ),
        "issues": issues,
    }


@router.get("/list_shipments")
def list_shipments(
    customer_session: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    """Return shipment records belonging only to the supplied customer session."""
    rows = db.execute(
        text("""
            SELECT
                o.order_id,
                o.status AS order_status,
                o.total_paise,
                o.created_at AS order_created_at,
                COALESCE(ordered_items.products, '[]'::json) AS ordered_products,
                s.shipment_id,
                s.status AS shipment_status,
                s.carrier_name,
                s.carrier_code,
                s.tracking_number,
                s.current_location,
                s.estimated_delivery_at,
                s.last_error,
                s.updated_at AS shipment_updated_at,
                demo_recovery.status AS demo_recovery_status,
                i.incident_id,
                i.status AS incident_status,
                i.severity AS incident_severity,
                i.title AS incident_title,
                i.summary AS incident_summary,
                latest.event_type AS latest_event_type,
                latest.message AS latest_event_message,
                latest.severity AS latest_event_severity,
                latest.created_at AS latest_event_at
            FROM orders o
            LEFT JOIN shipments s ON s.order_id = o.order_id
            LEFT JOIN incidents i ON i.order_id = o.order_id
            LEFT JOIN LATERAL (
                SELECT ra.status, ra.created_at
                FROM recovery_actions ra
                WHERE ra.incident_id = i.incident_id
                  AND ra.action_type = 'sample_delivery_simulation'
                ORDER BY ra.created_at DESC
                LIMIT 1
            ) demo_recovery ON TRUE
            LEFT JOIN LATERAL (
                SELECT json_agg(
                    json_build_object(
                        'product_id', p.product_id,
                        'product_name', p.name,
                        'quantity', oi.quantity,
                        'unit_price_paise', oi.unit_price_paise,
                        'line_total_paise', oi.quantity * oi.unit_price_paise
                    )
                    ORDER BY p.name
                ) AS products
                FROM order_items oi
                JOIN products p ON p.product_id = oi.product_id
                WHERE oi.order_id = o.order_id
            ) ordered_items ON TRUE
            LEFT JOIN LATERAL (
                SELECT event_type, message, severity, created_at
                FROM events e
                WHERE e.order_id = o.order_id
                ORDER BY e.created_at DESC, e.event_id DESC
                LIMIT 1
            ) latest ON TRUE
            WHERE o.customer_session = :customer_session
            ORDER BY o.created_at DESC
            LIMIT 100
        """),
        {"customer_session": customer_session},
    ).mappings().all()

    return {
        "count": len(rows),
        "shipments": [dict(row) for row in rows],
    }


@router.post("/complete_sample_recovery")
def complete_sample_recovery(
    payload: CompleteSampleRecoveryIn,
    db: Session = Depends(get_db),
):
    """Record a customer-authorized sample resolution without changing real fulfillment."""
    try:
        row = db.execute(
            text("""
                SELECT o.customer_session, o.incident_id,
                       p.status AS payment_status,
                       s.status AS shipment_status, s.last_error
                FROM orders o
                JOIN payments p ON p.order_id = o.order_id
                JOIN shipments s ON s.order_id = o.order_id
                WHERE o.order_id = :order_id
                FOR UPDATE OF o
            """),
            {"order_id": payload.order_id},
        ).mappings().first()

        if not row or row["customer_session"] != payload.customer_session:
            raise HTTPException(status_code=404, detail="Sample order not found.")
        if (
            row["payment_status"] != "captured"
            or row["shipment_status"] != "failed"
            or not (row["last_error"] or "").startswith("Seeded demo failure:")
            or not row["incident_id"]
        ):
            raise HTTPException(status_code=409, detail="This order has no eligible sample recovery.")

        existing_event = db.execute(
            text("""
                SELECT event_id FROM events
                WHERE order_id = :order_id
                  AND event_type = 'sample_delivery_simulation'
                LIMIT 1
            """),
            {"order_id": payload.order_id},
        ).first()
        if not existing_event:
            db.execute(
                text("""
                    INSERT INTO events (
                        incident_id, order_id, source, event_type,
                        severity, message, payload
                    ) VALUES (
                        :incident_id, :order_id, 'aftermath-demo',
                        'sample_delivery_simulation', 'info',
                        'Customer confirmed an illustrative delivery view; no parcel was shipped.',
                        CAST(:event_payload AS JSONB)
                    )
                """),
                {
                    "incident_id": row["incident_id"],
                    "order_id": payload.order_id,
                    "event_payload": '{"customer_confirmed": true, "simulated": true}',
                },
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Sample recovery could not be recorded.")

    return {"order_id": str(payload.order_id), "demo_recovery_status": "completed"}

