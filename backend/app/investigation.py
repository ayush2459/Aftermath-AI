"""Deterministic, evidence-led incident investigation for GhostTrail.

This module reads authoritative application records only. It does not call an
LLM, mutate business state, or infer that missing evidence proves an action
never happened.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db

router = APIRouter(prefix="/api/agent-tools", tags=["GhostTrail investigation"])


def _dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def reconcile_snapshot(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Return deterministic findings from a collected incident snapshot."""
    findings: list[dict[str, str]] = []
    order = snapshot.get("order") or {}
    payment = snapshot.get("payment")
    shipment = snapshot.get("shipment")
    reservations = snapshot.get("inventory_reservations") or []
    items = snapshot.get("order_items") or []

    if payment is None:
        findings.append({
            "code": "payment_record_missing",
            "severity": "warning",
            "message": "No payment record is linked to this order. Payment outcome is unknown.",
        })
    elif payment.get("status") == "captured" and shipment and shipment.get("status") == "failed":
        findings.append({
            "code": "payment_captured_shipment_failed",
            "severity": "high",
            "message": "Payment is recorded as captured while shipment creation is recorded as failed.",
        })

    if shipment is None:
        findings.append({
            "code": "shipment_record_missing",
            "severity": "warning",
            "message": "No shipment record is present. This does not prove that no external shipment exists.",
        })
    elif shipment.get("status") in {"failed", "unknown"}:
        findings.append({
            "code": "shipment_not_confirmed",
            "severity": "high" if shipment.get("status") == "failed" else "warning",
            "message": f"Shipment state is {shipment.get('status')}; successful fulfillment is not verified.",
        })

    reservation_by_product = {r.get("product_id"): r for r in reservations}
    for item in items:
        reservation = reservation_by_product.get(item.get("product_id"))
        if reservation is None:
            findings.append({
                "code": "inventory_reservation_missing",
                "severity": "warning",
                "message": f"No inventory reservation record was found for product {item.get('product_id')}.",
            })
        elif reservation.get("status") not in {"reserved", "consumed"}:
            findings.append({
                "code": "inventory_reservation_not_active",
                "severity": "high",
                "message": f"Inventory reservation for product {item.get('product_id')} is {reservation.get('status')}.",
            })

    if order.get("status") in {"needs_human", "recovery_required", "recovery_in_progress"}:
        findings.append({
            "code": "order_requires_recovery",
            "severity": "info",
            "message": f"Order status is {order.get('status')}; the order is not confirmed restored.",
        })

    return findings


@router.get("/investigate/{incident_id}")
def investigate_incident(
    incident_id: UUID,
    customer_session: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    """Collect an incident's evidence and reconcile its persisted business state."""
    incident = db.execute(text("""
        SELECT i.incident_id, i.order_id, i.status, i.severity, i.title,
               i.summary, i.correlation_id, i.created_at, i.updated_at
        FROM incidents i
        JOIN orders o ON o.order_id = i.order_id
        WHERE i.incident_id = :incident_id
          AND o.customer_session = :customer_session
    """), {"incident_id": incident_id, "customer_session": customer_session}).mappings().first()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found.")

    order_id = incident["order_id"]
    order = db.execute(text("""
        SELECT order_id, status, total_paise, currency, created_at, updated_at
        FROM orders WHERE order_id = :order_id
    """), {"order_id": order_id}).mappings().first()

    payment = db.execute(text("""
        SELECT payment_id, status, amount_paise, currency,
               simulated_provider_ref, idempotency_key, created_at, updated_at
        FROM payments WHERE order_id = :order_id
    """), {"order_id": order_id}).mappings().first()

    shipment = db.execute(text("""
        SELECT shipment_id, status, provider_ref, carrier_name, carrier_code,
               tracking_number, current_location, estimated_delivery_at,
               last_error, created_at, updated_at
        FROM shipments WHERE order_id = :order_id
    """), {"order_id": order_id}).mappings().first()

    items = db.execute(text("""
        SELECT product_id, quantity, unit_price_paise
        FROM order_items WHERE order_id = :order_id ORDER BY product_id
    """), {"order_id": order_id}).mappings().all()

    reservations = db.execute(text("""
        SELECT reservation_id, product_id, quantity, status,
               idempotency_key, created_at, updated_at
        FROM inventory_reservations
        WHERE order_id = :order_id ORDER BY product_id
    """), {"order_id": order_id}).mappings().all()

    events = db.execute(text("""
        SELECT event_id, source, event_type, severity, message, payload,
               correlation_id, created_at
        FROM events WHERE incident_id = :incident_id
        ORDER BY created_at ASC, event_id ASC
    """), {"incident_id": incident_id}).mappings().all()

    audit = db.execute(text("""
        SELECT audit_id, actor_type, actor_id, action, decision, reason,
               details, created_at
        FROM audit_log WHERE incident_id = :incident_id
        ORDER BY created_at ASC, audit_id ASC
    """), {"incident_id": incident_id}).mappings().all()

    notifications = db.execute(text("""
        SELECT delivery_id, channel, status, attempts, last_error,
               sent_at, created_at, updated_at
        FROM notification_deliveries WHERE incident_id = :incident_id
        ORDER BY created_at ASC, delivery_id ASC
    """), {"incident_id": incident_id}).mappings().all()

    snapshot = {
        "order": _dict(order),
        "payment": _dict(payment),
        "shipment": _dict(shipment),
        "order_items": [dict(row) for row in items],
        "inventory_reservations": [dict(row) for row in reservations],
    }
    findings = reconcile_snapshot(snapshot)

    evidence = [
        {"kind": "incident", "source": "postgresql.incidents", "record": _dict(incident)},
        {"kind": "order", "source": "postgresql.orders", "record": snapshot["order"]},
        {"kind": "payment", "source": "postgresql.payments", "record": snapshot["payment"]},
        {"kind": "shipment", "source": "postgresql.shipments", "record": snapshot["shipment"]},
        {"kind": "order_items", "source": "postgresql.order_items", "records": snapshot["order_items"]},
        {"kind": "inventory_reservations", "source": "postgresql.inventory_reservations", "records": snapshot["inventory_reservations"]},
        {"kind": "events", "source": "postgresql.events", "records": [dict(row) for row in events]},
        {"kind": "audit_log", "source": "postgresql.audit_log", "records": [dict(row) for row in audit]},
        {"kind": "notification_deliveries", "source": "postgresql.notification_deliveries", "records": [dict(row) for row in notifications]},
    ]

    return {
        "investigation": "ghosttrail",
        "mode": "deterministic",
        "incident": _dict(incident),
        "snapshot": snapshot,
        "findings": findings,
        "evidence": evidence,
        "limitations": [
            "Only persisted application records were inspected; external provider state was not queried.",
            "Missing records are reported as missing evidence, not proof that an external action did not occur.",
            "Seeded carrier allocation failures are simulated and do not represent live parcel movement.",
            "No business state was changed and no recovery action was executed.",
        ],
    }
