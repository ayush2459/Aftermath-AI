"""Discord handoff and simulated shipment restoration.

The Switch-hosted Discord agent is the only caller of inspect/execute. Customers
receive a short-lived opaque case code from GhostTrail and must explicitly
confirm the recovery in the private Discord support room.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import (
    DISCORD_RECOVERY_AGENT_KEY,
    DISCORD_SUPPORT_INVITE_URL,
    PUBLIC_FRONTEND_URL,
)
from .db import get_db

router = APIRouter(prefix="/api/discord/recovery", tags=["Discord recovery"])


class CreateHandoffIn(BaseModel):
    customer_session: str = Field(min_length=1, max_length=128)
    incident_id: UUID
    plan_id: UUID


class CaseCodeIn(BaseModel):
    case_code: str = Field(min_length=24, max_length=100)


class ExecuteHandoffIn(CaseCodeIn):
    confirmation: str = Field(min_length=1, max_length=40)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_agent_key(agent_key: str | None) -> None:
    if not DISCORD_RECOVERY_AGENT_KEY:
        raise HTTPException(status_code=503, detail="Discord recovery agent is not configured.")
    if not agent_key or not hmac.compare_digest(agent_key, DISCORD_RECOVERY_AGENT_KEY):
        raise HTTPException(status_code=401, detail="Invalid recovery agent credentials.")


def _share_token(handoff_id: UUID) -> str:
    """Derive a stable, opaque, read-only share token without storing it in plaintext."""
    if not DISCORD_RECOVERY_AGENT_KEY:
        raise HTTPException(status_code=503, detail="Discord recovery agent is not configured.")
    message = f"aftermath-shipment-share:{handoff_id}".encode("utf-8")
    return hmac.new(DISCORD_RECOVERY_AGENT_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _case_row(db: Session, case_code: str, *, lock: bool = False):
    suffix = " FOR UPDATE OF h, rp, a, o, s" if lock else ""
    return db.execute(text(f"""
        SELECT
            h.handoff_id, h.incident_id, h.plan_id, h.order_id,
            h.expires_at, h.previewed_at, h.consumed_at,
            rp.status AS plan_status, rp.plan,
            a.status AS approval_status,
            i.status AS incident_status, i.title AS incident_title,
            o.status AS order_status, o.total_paise, o.currency,
            p.status AS payment_status,
            s.status AS shipment_status, s.last_error,
            s.tracking_number, s.carrier_name, s.carrier_code,
            diagnosis.content AS diagnosis
        FROM discord_recovery_handoffs h
        JOIN recovery_plans rp ON rp.plan_id = h.plan_id
        JOIN approvals a ON a.plan_id = rp.plan_id
        JOIN incidents i ON i.incident_id = h.incident_id
        JOIN orders o ON o.order_id = h.order_id
        LEFT JOIN payments p ON p.order_id = o.order_id
        JOIN shipments s ON s.order_id = o.order_id
        LEFT JOIN LATERAL (
            SELECT content FROM evidence
            WHERE incident_id = h.incident_id
              AND evidence_type = 'ghosttrail_diagnosis'
            ORDER BY created_at DESC LIMIT 1
        ) diagnosis ON TRUE
        WHERE h.code_hash = :code_hash
        ORDER BY a.created_at DESC
        LIMIT 1
        {suffix}
    """), {"code_hash": _digest(case_code)}).mappings().first()


@router.post("/handoffs")
def create_handoff(payload: CreateHandoffIn, db: Session = Depends(get_db)):
    """Create a short-lived case code for a prepared GhostTrail plan."""
    if not DISCORD_RECOVERY_AGENT_KEY:
        raise HTTPException(status_code=503, detail="Discord recovery agent is not configured on the backend.")
    if not DISCORD_SUPPORT_INVITE_URL:
        raise HTTPException(status_code=503, detail="Discord support invite is not configured.")
    row = db.execute(text("""
        SELECT rp.plan, rp.status AS plan_status, a.status AS approval_status,
               i.order_id, i.status AS incident_status,
               s.status AS shipment_status, s.last_error,
               diagnosis.content AS diagnosis
        FROM recovery_plans rp
        JOIN incidents i ON i.incident_id = rp.incident_id
        JOIN orders o ON o.order_id = i.order_id
        JOIN approvals a ON a.plan_id = rp.plan_id
        JOIN shipments s ON s.order_id = o.order_id
        LEFT JOIN LATERAL (
            SELECT content FROM evidence
            WHERE incident_id = i.incident_id
              AND evidence_type = 'ghosttrail_diagnosis'
            ORDER BY created_at DESC LIMIT 1
        ) diagnosis ON TRUE
        WHERE rp.plan_id = :plan_id
          AND rp.incident_id = :incident_id
          AND o.customer_session = :customer_session
        ORDER BY a.created_at DESC LIMIT 1
    """), {
        "plan_id": payload.plan_id,
        "incident_id": payload.incident_id,
        "customer_session": payload.customer_session,
    }).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Approved recovery case not found.")
    if row["plan_status"] not in {"proposed", "approved"} or row["approval_status"] not in {"pending", "approved"}:
        raise HTTPException(status_code=409, detail="The recovery plan is not ready for Discord review.")
    if row["shipment_status"] != "failed" or not (row["last_error"] or "").startswith("Seeded demo failure:"):
        raise HTTPException(status_code=409, detail="This simulated shipment failure is no longer eligible.")
    if not row["diagnosis"]:
        raise HTTPException(status_code=409, detail="GhostTrail diagnosis must be saved before Discord handoff.")
    actions = (row["plan"] or {}).get("actions", [])
    if not any(
        action.get("action_type") == "reconcile_shipment_with_carrier"
        and action.get("approval_required") is True
        for action in actions
    ):
        raise HTTPException(status_code=409, detail="The prepared plan has no eligible shipment recovery action.")

    case_code = secrets.token_urlsafe(24)
    handoff = db.execute(text("""
        INSERT INTO discord_recovery_handoffs (
            incident_id, plan_id, order_id, code_hash, expires_at
        )
        VALUES (
            :incident_id, :plan_id, :order_id, :code_hash,
            NOW() + INTERVAL '60 minutes'
        )
        RETURNING handoff_id, expires_at
    """), {
        "incident_id": payload.incident_id,
        "plan_id": payload.plan_id,
        "order_id": row["order_id"],
        "code_hash": _digest(case_code),
    }).mappings().one()
    db.execute(text("""
        INSERT INTO audit_log (
            incident_id, actor_type, actor_id, action, decision, reason, details
        ) VALUES (
            :incident_id, 'customer_session', 'ghosttrail',
            'create_discord_recovery_handoff', 'created',
            'GhostTrail diagnosis and proposed recovery plan were handed to Discord for review and explicit confirmation.',
            CAST(:details AS JSONB)
        )
    """), {
        "incident_id": payload.incident_id,
        "details": json.dumps({
            "handoff_id": str(handoff["handoff_id"]),
            "plan_id": str(payload.plan_id),
            "expires_at": handoff["expires_at"].isoformat(),
            "simulation_only": True,
        }),
    })
    db.commit()

    return {
        "handoff_id": str(handoff["handoff_id"]),
        "case_code": case_code,
        "expires_at": handoff["expires_at"],
        "discord_invite_url": DISCORD_SUPPORT_INVITE_URL,
        "discord_command": f"CASE {case_code}",
        "instructions": "Open the private Aftermath AI Discord support room, mention @Aftermath Recovery, and send the CASE command. Review the diagnosis and explicitly confirm with CONFIRM <case_code>.",
        "simulation_only": True,
    }


@router.post("/handoffs/inspect")
def inspect_handoff(
    payload: CaseCodeIn,
    x_aftermath_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Read a GhostTrail-approved case for the authenticated Switch agent."""
    _require_agent_key(x_aftermath_agent_key)
    row = _case_row(db, payload.case_code)
    if not row:
        raise HTTPException(status_code=404, detail="Recovery case code is invalid.")
    if row["expires_at"] <= db.execute(text("SELECT NOW()")).scalar_one():
        raise HTTPException(status_code=410, detail="Recovery case code has expired.")
    if row["consumed_at"]:
        raise HTTPException(status_code=409, detail="This recovery case has already been completed.")
    if row["plan_status"] not in {"proposed", "approved"} or row["approval_status"] not in {"pending", "approved"}:
        raise HTTPException(status_code=409, detail="The recovery plan is not ready for review.")
    if not row["diagnosis"]:
        raise HTTPException(status_code=409, detail="GhostTrail diagnosis is unavailable.")

    db.execute(text("""
        UPDATE discord_recovery_handoffs
        SET previewed_at = COALESCE(previewed_at, NOW())
        WHERE handoff_id = :handoff_id
    """), {"handoff_id": row["handoff_id"]})
    db.commit()

    diagnosis = row["diagnosis"] or {}
    if isinstance(diagnosis, str):
        diagnosis = json.loads(diagnosis)
    return {
        "handoff_id": str(row["handoff_id"]),
        "incident_id": str(row["incident_id"]),
        "order_id": str(row["order_id"]),
        "order_status": row["order_status"],
        "payment_status": row["payment_status"],
        "shipment_status": row["shipment_status"],
        "incident_title": row["incident_title"],
        "diagnosis": diagnosis.get("diagnosis", diagnosis),
        "plan": row["plan"],
        "approval_status": row["approval_status"],
        "simulation_only": True,
        "confirmation_required": True,
    }



@router.post("/handoffs/status")
def handoff_status(
    payload: CaseCodeIn,
    x_aftermath_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Read the persisted recovery state without previewing or changing the case."""
    _require_agent_key(x_aftermath_agent_key)
    row = _case_row(db, payload.case_code)
    if not row:
        raise HTTPException(status_code=404, detail="Recovery case code is invalid.")
    action = db.execute(text("""
        SELECT status, result, created_at
        FROM recovery_actions
        WHERE plan_id = :plan_id
        ORDER BY created_at DESC
        LIMIT 1
    """), {"plan_id": row["plan_id"]}).mappings().first()
    result = (action or {}).get("result") or {}
    return {
        "incident_id": str(row["incident_id"]),
        "order_id": str(row["order_id"]),
        "incident_status": row["incident_status"],
        "plan_status": row["plan_status"],
        "approval_status": row["approval_status"],
        "order_status": row["order_status"],
        "payment_status": row["payment_status"],
        "shipment_status": row["shipment_status"],
        "recovery_status": (action or {}).get("status") or "not_started",
        "recovery_result": result,
        "recovery_created_at": (action or {}).get("created_at"),
        "expires_at": row["expires_at"],
        "consumed": bool(row["consumed_at"]),
        "simulation_only": True,
    }


@router.post("/handoffs/execute")
def execute_handoff(
    payload: ExecuteHandoffIn,
    x_aftermath_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Approve and execute only after Discord receives explicit CONFIRM RECOVERY."""
    _require_agent_key(x_aftermath_agent_key)
    if payload.confirmation.strip().upper() != "CONFIRM RECOVERY":
        raise HTTPException(status_code=400, detail="Explicit CONFIRM RECOVERY confirmation is required.")

    row = _case_row(db, payload.case_code, lock=True)
    if not row:
        raise HTTPException(status_code=404, detail="Recovery case code is invalid.")
    if row["expires_at"] <= db.execute(text("SELECT NOW()")).scalar_one():
        raise HTTPException(status_code=410, detail="Recovery case code has expired.")
    if not row["previewed_at"]:
        raise HTTPException(status_code=409, detail="Inspect the recovery case before confirming it.")
    if row["plan_status"] not in {"proposed", "approved"} or row["approval_status"] not in {"pending", "approved"}:
        raise HTTPException(status_code=409, detail="The recovery plan is not ready for confirmation.")
    if row["payment_status"] != "captured":
        raise HTTPException(status_code=409, detail="Payment is not captured; recovery is blocked.")
    if row["shipment_status"] != "failed" or not (row["last_error"] or "").startswith("Seeded demo failure:"):
        # An already completed idempotent replay is handled below.
        existing = db.execute(text("""
            SELECT status, result FROM recovery_actions
            WHERE idempotency_key = :key
        """), {"key": f"discord-simulated-shipment-restore:{row['plan_id']}"}).mappings().first()
        if not existing or existing["status"] != "completed":
            raise HTTPException(status_code=409, detail="Shipment is not in the expected seeded failure state.")

    reservation_problem = db.execute(text("""
        SELECT COUNT(*)
        FROM order_items oi
        LEFT JOIN inventory_reservations ir
          ON ir.order_id = oi.order_id AND ir.product_id = oi.product_id
        WHERE oi.order_id = :order_id
          AND (
              ir.reservation_id IS NULL
              OR ir.quantity <> oi.quantity
              OR ir.status NOT IN ('reserved', 'consumed')
          )
    """), {"order_id": row["order_id"]}).scalar_one()
    if reservation_problem:
        raise HTTPException(status_code=409, detail="Inventory reservation reconciliation is required before restoration.")

    # GhostTrail proposes only. The Discord CONFIRM command is the decision point.
    if row["approval_status"] == "pending":
        db.execute(text("""
            UPDATE approvals
            SET status = 'approved',
                decided_by = 'discord-confirmation',
                decision_reason = 'Explicit Discord CONFIRM command received after case preview.',
                decided_at = NOW()
            WHERE plan_id = :plan_id AND status = 'pending'
        """), {"plan_id": row["plan_id"]})
        db.execute(text("""
            UPDATE recovery_plans SET status = 'approved'
            WHERE plan_id = :plan_id AND status = 'proposed'
        """), {"plan_id": row["plan_id"]})

    action_key = f"discord-simulated-shipment-restore:{row['plan_id']}"
    existing = db.execute(text("""
        SELECT status, result FROM recovery_actions
        WHERE idempotency_key = :key
        FOR UPDATE
    """), {"key": action_key}).mappings().first()

    share_token = _share_token(row["handoff_id"])
    share_token_hash = _digest(share_token)
    if existing and existing["status"] == "completed":
        result = existing["result"] or {}
        customer_url = result.get("customer_url") or (
            f"{PUBLIC_FRONTEND_URL}/shipments?order={row['order_id']}&view=recovered&share={share_token}"
        )
        db.execute(text("""
            INSERT INTO shipment_share_tokens (token_hash, order_id, plan_id, expires_at)
            VALUES (:token_hash, :order_id, :plan_id, NOW() + INTERVAL '7 days')
            ON CONFLICT (token_hash) DO UPDATE
            SET expires_at = EXCLUDED.expires_at, revoked_at = NULL
        """), {
            "token_hash": share_token_hash,
            "order_id": row["order_id"],
            "plan_id": row["plan_id"],
        })
        db.execute(text("""
            UPDATE discord_recovery_handoffs SET consumed_at = COALESCE(consumed_at, NOW())
            WHERE handoff_id = :handoff_id
        """), {"handoff_id": row["handoff_id"]})
        db.commit()
        verified = db.execute(text("""
            SELECT o.status AS order_status, s.status AS shipment_status,
                   i.status AS incident_status, s.tracking_number,
                   s.carrier_code
            FROM orders o
            JOIN shipments s ON s.order_id = o.order_id
            JOIN incidents i ON i.order_id = o.order_id
            WHERE o.order_id = :order_id AND i.incident_id = :incident_id
        """), {"order_id": row["order_id"], "incident_id": row["incident_id"]}).mappings().first()
        if (
            not verified
            or verified["order_status"] != "restored"
            or verified["shipment_status"] != "created"
            or verified["incident_status"] != "resolved"
            or verified["carrier_code"] != "AFTERMATH-DEMO"
        ):
            raise HTTPException(status_code=500, detail="Previously completed recovery no longer matches the verified shipment state.")
        return {
            "status": "completed",
            "simulated": True,
            "idempotent_replay": True,
            "order_id": str(row["order_id"]),
            "customer_url": customer_url,
            "verification": {
                "order_status": verified["order_status"],
                "shipment_status": verified["shipment_status"],
                "incident_status": verified["incident_status"],
                "tracking_number": verified["tracking_number"],
                "carrier_code": verified["carrier_code"],
            },
        }

    action = next((
        item for item in (row["plan"] or {}).get("actions", [])
        if item.get("action_type") == "reconcile_shipment_with_carrier"
        and item.get("approval_required") is True
    ), None)
    if not action:
        raise HTTPException(status_code=409, detail="Approved plan does not authorize shipment reconciliation.")

    tracking_number = f"AFTER-{UUID(str(row['order_id'])).hex[:10].upper()}"
    provider_ref = f"AFTERMATH-DEMO-{row['order_id']}"
    db.execute(text("""
        UPDATE shipments
        SET status = 'created',
            provider_ref = :provider_ref,
            carrier_name = 'Aftermath AI Simulated Carrier',
            carrier_code = 'AFTERMATH-DEMO',
            tracking_number = :tracking_number,
            current_location = 'Simulated recovery staging',
            estimated_delivery_at = NULL,
            last_error = NULL,
            updated_at = NOW()
        WHERE order_id = :order_id
    """), {
        "provider_ref": provider_ref,
        "tracking_number": tracking_number,
        "order_id": row["order_id"],
    })
    db.execute(text("""
        UPDATE orders SET status = 'restored', updated_at = NOW()
        WHERE order_id = :order_id
    """), {"order_id": row["order_id"]})
    db.execute(text("""
        UPDATE incidents SET status = 'resolved', updated_at = NOW()
        WHERE incident_id = :incident_id
    """), {"incident_id": row["incident_id"]})

    customer_url = (
        f"{PUBLIC_FRONTEND_URL}/shipments?order={row['order_id']}"
        f"&view=recovered&share={share_token}"
    )
    action_result = {
        "status": "completed",
        "simulated": True,
        "real_fulfillment_unchanged": True,
        "order_status": "restored",
        "shipment_status": "created",
        "incident_status": "resolved",
        "tracking_number": tracking_number,
        "carrier_name": "Aftermath AI Simulated Carrier",
    }
    db.execute(text("""
        INSERT INTO recovery_actions (
            incident_id, plan_id, action_type, status, idempotency_key, input, result
        ) VALUES (
            :incident_id, :plan_id, 'discord_simulated_shipment_restore',
            'completed', :idempotency_key, CAST(:input AS JSONB), CAST(:result AS JSONB)
        )
    """), {
        "incident_id": row["incident_id"],
        "plan_id": row["plan_id"],
        "idempotency_key": action_key,
        "input": json.dumps({
            "handoff_id": str(row["handoff_id"]),
            "confirmation": "CONFIRM RECOVERY",
            "simulation_only": True,
        }),
        "result": json.dumps(action_result),
    })
    db.execute(text("""
        INSERT INTO events (
            incident_id, order_id, source, event_type, severity, message, payload
        ) VALUES (
            :incident_id, :order_id, 'discord-recovery',
            'discord_simulated_shipment_restored', 'info',
            'Discord recovery agent restored the order and created a simulated shipment record. No carrier API or real fulfillment was called.',
            CAST(:payload AS JSONB)
        )
    """), {
        "incident_id": row["incident_id"],
        "order_id": row["order_id"],
        "payload": json.dumps(action_result),
    })
    db.execute(text("""
        INSERT INTO audit_log (
            incident_id, actor_type, actor_id, action, decision, reason, details
        ) VALUES (
            :incident_id, 'discord_recovery_agent', 'switch-discord-agent',
            'restore_simulated_shipment', 'completed',
            'Explicit customer confirmation received in Discord; approved demo recovery executed.',
            CAST(:details AS JSONB)
        )
    """), {
        "incident_id": row["incident_id"],
        "details": json.dumps({
            "handoff_id": str(row["handoff_id"]),
            "plan_id": str(row["plan_id"]),
            "order_id": str(row["order_id"]),
            "tracking_number": tracking_number,
            "simulated": True,
            "real_fulfillment_unchanged": True,
        }),
    })
    db.execute(text("""
        INSERT INTO shipment_share_tokens (token_hash, order_id, plan_id, expires_at)
        VALUES (:token_hash, :order_id, :plan_id, NOW() + INTERVAL '7 days')
        ON CONFLICT (token_hash) DO UPDATE
        SET expires_at = EXCLUDED.expires_at, revoked_at = NULL
    """), {
        "token_hash": share_token_hash,
        "order_id": row["order_id"],
        "plan_id": row["plan_id"],
    })
    db.execute(text("""
        UPDATE discord_recovery_handoffs
        SET consumed_at = NOW()
        WHERE handoff_id = :handoff_id
    """), {"handoff_id": row["handoff_id"]})
    db.commit()

    # Verify the committed state before returning a success link to Discord.
    verified = db.execute(text("""
        SELECT o.status AS order_status, s.status AS shipment_status,
               i.status AS incident_status, s.tracking_number, s.carrier_code
        FROM orders o
        JOIN shipments s ON s.order_id = o.order_id
        JOIN incidents i ON i.order_id = o.order_id
        WHERE o.order_id = :order_id AND i.incident_id = :incident_id
    """), {"order_id": row["order_id"], "incident_id": row["incident_id"]}).mappings().first()
    if (
        not verified
        or verified["order_status"] != "restored"
        or verified["shipment_status"] != "created"
        or verified["incident_status"] != "resolved"
        or verified["tracking_number"] != tracking_number
        or verified["carrier_code"] != "AFTERMATH-DEMO"
    ):
        raise HTTPException(status_code=500, detail="Recovery was written but its committed state could not be verified.")

    return {
        "status": "completed",
        "simulated": True,
        "idempotent_replay": False,
        "order_id": str(row["order_id"]),
        "customer_url": customer_url,
        "verification": {
            "order_status": verified["order_status"],
            "shipment_status": verified["shipment_status"],
            "incident_status": verified["incident_status"],
            "tracking_number": verified["tracking_number"],
            "carrier_code": verified["carrier_code"],
        },
        "message": "Order restored and simulated shipment record verified. No real carrier or fulfillment action occurred.",
    }
