"""Deterministic recovery proposals and auditable demo approval records.

This module never executes payment, inventory, or carrier side effects.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db
from .investigation import investigate_incident

router = APIRouter(prefix="/api/recovery", tags=["Recovery planning"])


def build_recovery_plan(snapshot: dict[str, Any], findings: list[dict[str, str]]) -> dict[str, Any]:
    codes = {item["code"] for item in findings}
    actions: list[dict[str, Any]] = []
    if "payment_captured_shipment_failed" in codes or "shipment_not_confirmed" in codes:
        actions.append({
            "action_type": "reconcile_shipment_with_carrier",
            "category": "human_review",
            "description": "Check the carrier/provider directly before attempting shipment creation again.",
            "preconditions": ["Confirm whether a shipment exists externally", "Verify payment and inventory records"],
            "expected_effect": "Establish the authoritative shipment state; no shipment is created by this proposal.",
            "risk": "high",
            "approval_required": True,
            "idempotency_key_strategy": "Use the carrier's stable shipment reference or a persisted unique recovery key after external state is confirmed.",
            "verification": "Re-read carrier shipment reference and local shipment record; require matching confirmed states.",
        })
    if "inventory_reservation_missing" in codes or "inventory_reservation_not_active" in codes:
        actions.append({
            "action_type": "reconcile_inventory",
            "category": "human_review",
            "description": "Reconcile reserved quantities against stock ledger before any fulfillment retry.",
            "preconditions": ["Inspect inventory ledger", "Confirm payment capture", "Check for duplicate reservations"],
            "expected_effect": "Determine whether inventory can safely be fulfilled or requires compensation.",
            "risk": "high",
            "approval_required": True,
            "idempotency_key_strategy": "Use one stable recovery key per incident and product; never blindly insert a second reservation.",
            "verification": "Re-read reservation rows and stock ledger and compare quantities.",
        })
    if not actions:
        actions.append({
            "action_type": "continue_monitoring",
            "category": "read_only",
            "description": "No corrective mutation is proposed; continue monitoring and investigate any new contradictory evidence.",
            "preconditions": ["Review the latest investigation snapshot"],
            "expected_effect": "Keep the current business state unchanged.",
            "risk": "low",
            "approval_required": False,
            "idempotency_key_strategy": "No mutation; repeated proposal generation is read-only.",
            "verification": "Run GhostTrail investigation again and compare findings.",
        })
    return {
        "schema_version": "1.0",
        "strategy": "operator_review" if any(a["approval_required"] for a in actions) else "read_only",
        "actions": actions,
        "source_findings": sorted(codes),
        "business_state_changed": False,
        "execution_enabled": False,
    }


class RecoveryDecisionIn(BaseModel):
    customer_session: str = Field(min_length=1, max_length=128)
    decided_by: str = Field(min_length=1, max_length=120)
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/propose/{incident_id}")
def propose_recovery(
    incident_id: UUID,
    customer_session: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db),
):
    investigation = investigate_incident(
        incident_id=incident_id,
        customer_session=customer_session,
        db=db,
    )
    plan = build_recovery_plan(investigation["snapshot"], investigation["findings"])
    try:
        plan_row = db.execute(text("""
            INSERT INTO recovery_plans (incident_id, status, plan)
            VALUES (:incident_id, 'proposed', CAST(:plan AS JSONB))
            RETURNING plan_id, created_at
        """), {
            "incident_id": incident_id,
            "plan": json.dumps(plan),
        }).mappings().one()
        approval = db.execute(text("""
            INSERT INTO approvals (plan_id, status, requested_by)
            VALUES (:plan_id, 'pending', 'operator-review-required')
            RETURNING approval_id, created_at
        """), {"plan_id": plan_row["plan_id"]}).mappings().one()
        db.execute(text("""
            INSERT INTO audit_log (
                incident_id, actor_type, actor_id, action, decision, reason, details
            ) VALUES (
                :incident_id, 'system', 'recovery-planner', 'propose_recovery',
                'approval_required', 'A deterministic recovery proposal was created; no action was executed.',
                CAST(:details AS JSONB)
            )
        """), {
            "incident_id": incident_id,
            "details": json.dumps({
                "plan_id": str(plan_row["plan_id"]),
                "approval_id": str(approval["approval_id"]),
                "execution_enabled": False,
            }),
        })
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Recovery proposal could not be saved.")
    return {
        "plan_id": str(plan_row["plan_id"]),
        "approval_id": str(approval["approval_id"]),
        "created_at": plan_row["created_at"],
        "status": "proposed",
        "plan": plan,
        "approval": {"approval_id": str(approval["approval_id"]), "status": "pending"},
        "execution_enabled": False,
    }


@router.post("/plans/{plan_id}/decision")
def decide_recovery_plan(
    plan_id: UUID,
    payload: RecoveryDecisionIn,
    db: Session = Depends(get_db),
):
    """Record a demo approval decision; this endpoint never executes the plan."""
    row = db.execute(text("""
        SELECT rp.incident_id, rp.status AS plan_status, o.customer_session,
               a.approval_id, a.status AS approval_status
        FROM recovery_plans rp
        JOIN incidents i ON i.incident_id = rp.incident_id
        JOIN orders o ON o.order_id = i.order_id
        JOIN approvals a ON a.plan_id = rp.plan_id
        WHERE rp.plan_id = :plan_id
          AND o.customer_session = :customer_session
        ORDER BY a.created_at DESC
        LIMIT 1
        FOR UPDATE OF rp, a
    """), {
        "plan_id": plan_id,
        "customer_session": payload.customer_session,
    }).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Recovery plan not found.")
    if row["approval_status"] != "pending" or row["plan_status"] != "proposed":
        raise HTTPException(status_code=409, detail="This recovery plan already has a decision.")
    try:
        db.execute(text("""
            UPDATE approvals
            SET status = :decision, decided_by = :decided_by,
                decision_reason = :reason, decided_at = NOW()
            WHERE approval_id = :approval_id
        """), {
            "decision": payload.decision,
            "decided_by": payload.decided_by,
            "reason": payload.reason,
            "approval_id": row["approval_id"],
        })
        db.execute(text("""
            UPDATE recovery_plans SET status = :status WHERE plan_id = :plan_id
        """), {
            "status": payload.decision,
            "plan_id": plan_id,
        })
        db.execute(text("""
            INSERT INTO audit_log (
                incident_id, actor_type, actor_id, action, decision, reason, details
            ) VALUES (
                :incident_id, 'operator_demo_attestation', :actor,
                'decide_recovery_plan', :decision, :reason, CAST(:details AS JSONB)
            )
        """), {
            "incident_id": row["incident_id"],
            "actor": payload.decided_by,
            "decision": payload.decision,
            "reason": payload.reason,
            "details": json.dumps({
                "plan_id": str(plan_id),
                "approval_id": str(row["approval_id"]),
                "execution_enabled": False,
                "identity_verified": False,
            }),
        })
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Recovery decision could not be recorded.")
    return {
        "plan_id": str(plan_id),
        "approval_id": str(row["approval_id"]),
        "decision": payload.decision,
        "recorded": True,
        "execution_enabled": False,
        "note": "This demo records an operator attestation only. It does not authenticate the operator or execute recovery actions.",
    }

class RecoveryExecutionIn(BaseModel):
    customer_session: str = Field(min_length=1, max_length=128)

@router.post("/plans/{plan_id}/execute-demo")
def execute_approved_demo_recovery(plan_id: UUID, payload: RecoveryExecutionIn, db: Session = Depends(get_db)):
    """Record approved demo recovery without changing actual fulfillment."""
    try:
        row = db.execute(text("""
            SELECT rp.plan_id, rp.incident_id, rp.status AS plan_status, rp.plan,
                   a.status AS approval_status, o.order_id, p.status AS payment_status,
                   s.status AS shipment_status, s.last_error
            FROM recovery_plans rp JOIN incidents i ON i.incident_id = rp.incident_id
            JOIN orders o ON o.order_id = i.order_id JOIN approvals a ON a.plan_id = rp.plan_id
            LEFT JOIN payments p ON p.order_id = o.order_id LEFT JOIN shipments s ON s.order_id = o.order_id
            WHERE rp.plan_id = :plan_id AND o.customer_session = :customer_session
            ORDER BY a.created_at DESC LIMIT 1 FOR UPDATE OF rp, a, o
        """), {"plan_id": plan_id, "customer_session": payload.customer_session}).mappings().first()
        if not row: raise HTTPException(status_code=404, detail="Recovery plan not found.")
        if row["plan_status"] != "approved" or row["approval_status"] != "approved":
            raise HTTPException(status_code=409, detail="An approved recovery decision is required.")
        if row["payment_status"] != "captured": raise HTTPException(status_code=409, detail="Payment is not captured.")
        if row["shipment_status"] != "failed" or not (row["last_error"] or "").startswith("Seeded demo failure:"):
            raise HTTPException(status_code=409, detail="Order is not in the seeded demo failure state.")
        if not any(x.get("action_type") == "reconcile_shipment_with_carrier" and x.get("approval_required") for x in (row["plan"] or {}).get("actions", [])):
            raise HTTPException(status_code=409, detail="Plan has no eligible shipment recovery action.")
        key = f"ghosttrail-demo-recovery:{plan_id}"
        existing = db.execute(text("SELECT status, result FROM recovery_actions WHERE idempotency_key=:key FOR UPDATE"), {"key": key}).mappings().first()
        customer_url = f"/shipments?order={row['order_id']}&view=recovered"
        if existing:
            if existing["status"] != "completed": raise HTTPException(status_code=409, detail="Existing recovery action is incomplete.")
            db.commit()
            return {"plan_id": str(plan_id), "order_id": str(row["order_id"]), "status": "completed", "simulated": True, "idempotent_replay": True, "customer_url": (existing["result"] or {}).get("customer_url", customer_url)}
        result = {"recovery_status": "completed", "simulated": True, "real_fulfillment_unchanged": True, "customer_url": customer_url}
        db.execute(text("""INSERT INTO recovery_actions (incident_id, plan_id, action_type, status, idempotency_key, input, result)
            VALUES (:incident_id, :plan_id, 'ghosttrail_demo_recovery', 'completed', :key, CAST(:input AS JSONB), CAST(:result AS JSONB))"""),
            {"incident_id": row["incident_id"], "plan_id": plan_id, "key": key, "input": json.dumps({"customer_session": payload.customer_session, "simulated": True}), "result": json.dumps(result)})
        db.execute(text("""INSERT INTO events (incident_id, order_id, source, event_type, severity, message, payload)
            VALUES (:incident_id, :order_id, 'ghosttrail', 'demo_recovery_completed', 'info',
            'GhostTrail recorded approved simulated recovery. No carrier or fulfillment action occurred.', CAST(:payload AS JSONB))"""),
            {"incident_id": row["incident_id"], "order_id": row["order_id"], "payload": json.dumps(result)})
        db.execute(text("""INSERT INTO audit_log (incident_id, actor_type, actor_id, action, decision, reason, details)
            VALUES (:incident_id, 'operator_demo_attestation', 'GhostTrail demo operator', 'execute_demo_recovery', 'completed',
            'Approved simulated recovery recorded; real fulfillment unchanged.', CAST(:details AS JSONB))"""),
            {"incident_id": row["incident_id"], "details": json.dumps({"plan_id": str(plan_id), "order_id": str(row["order_id"]), "simulated": True, "real_fulfillment_unchanged": True})})
        db.commit()
        return {"plan_id": str(plan_id), "order_id": str(row["order_id"]), "status": "completed", "simulated": True, "idempotent_replay": False, "customer_url": customer_url}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Approved demo recovery could not be recorded.")
