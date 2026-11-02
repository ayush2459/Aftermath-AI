"""Unified customer-support intake and deterministic issue routing.

Customer-provided text is untrusted input. This router records a redacted
support case and chooses a specialist workflow; it never executes code or
changes orders, payments, inventory, shipments, or customer accounts.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db

router = APIRouter(prefix="/api/support", tags=["Unified customer support"])
AGENT_SECRET = os.getenv("DISCORD_RECOVERY_AGENT_KEY", "").strip()

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|rzp_(?:test|live)_[A-Za-z0-9]+)\b")


class SupportIntake(BaseModel):
    message: str = Field(min_length=5, max_length=5000)
    room_id: str = Field(min_length=1, max_length=128)
    source_event_id: str | None = Field(default=None, max_length=160)
    page_url: str | None = Field(default=None, max_length=1000)


def classify_issue(message: str) -> str:
    """Route by explicit customer vocabulary; an LLM never chooses permissions."""
    value = (message or "").lower()
    if any(term in value for term in ("shipment", "delivery", "tracking", "parcel", "courier", "carrier", "order not")):
        return "shipment_recovery"
    if any(term in value for term in ("payment", "charged", "refund", "checkout", "transaction")):
        return "payment_support"
    if any(term in value for term in ("login", "log in", "sign in", "password", "account", "verification code")):
        return "account_support"
    if any(term in value for term in ("bug", "broken", "crash", "error", "not loading", "doesn't work", "does not work", "button", "blank page", "page is")):
        return "software_bug"
    return "general_support"


def _redact(message: str) -> str:
    value = _EMAIL.sub("[redacted email]", message)
    value = _BEARER.sub("Bearer [redacted]", value)
    value = _SECRET.sub("[redacted credential]", value)
    return value[:5000]


def _reply(category: str, page_url: str | None) -> str:
    if category == "shipment_recovery":
        return (
            "I can help with your shipment. If GhostTrail has already given you a case code, "
            "send CASE followed by that code here. Otherwise, share the shipment page link so I can guide you."
        )
    if category == "payment_support":
        return (
            "Thanks for flagging the payment issue. I've saved your report for review. "
            "Please don't retry the payment until we've checked what happened, and don't share card details or verification codes."
        )
    if category == "account_support":
        return (
            "Thanks for letting me know. I've saved your report. Please share the page link and what you were trying to do; "
            "never send your password or verification codes."
        )
    if category == "software_bug":
        if page_url:
            return (
                "Thanks for reporting this. I've saved the details and will have the team check the page. "
                "If you can, also share a screenshot of what you saw. Please hide any personal or payment information."
            )
        return (
            "Thanks for reporting this. I've saved the details so we can look into it. "
            "Could you share the page link and, if possible, a screenshot of what you saw? Please hide personal or payment information."
        )
    return (
        "Thanks for contacting Aftermath AI. I've saved your message so we can help. "
        "Which page were you using, and what were you trying to do?"
    )


def _require_agent_key(value: str | None) -> None:
    if not AGENT_SECRET:
        raise HTTPException(status_code=503, detail="Support agent is not configured.")
    if not value or not hmac.compare_digest(value, AGENT_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized support agent.")


@router.post("/cases", status_code=201)
def create_support_case(
    payload: SupportIntake,
    x_aftermath_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Persist an addressed customer report and return a customer-safe next step."""
    _require_agent_key(x_aftermath_agent_key)
    message = payload.message.strip()
    if len(message) < 5:
        raise HTTPException(status_code=422, detail="Please provide a little more detail.")

    page_url = payload.page_url
    if page_url:
        parsed = urlparse(page_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Page link must be a valid HTTP or HTTPS URL.")

    category = classify_issue(message)
    safe_message = _redact(message)
    event_id = payload.source_event_id.strip() if payload.source_event_id else None
    room_id_hash = hashlib.sha256(payload.room_id.encode("utf-8")).hexdigest()

    try:
        row = db.execute(text("""
            INSERT INTO support_cases (
                source, room_id_hash, source_event_id, category,
                status, customer_message, page_url
            )
            VALUES (
                'switch_room', :room_id_hash, :source_event_id, :category,
                'triaged', :customer_message, :page_url
            )
            ON CONFLICT (source, source_event_id) DO NOTHING
            RETURNING case_id, category, status, created_at
        """), {
            "room_id_hash": room_id_hash,
            "source_event_id": event_id,
            "category": category,
            "customer_message": safe_message,
            "page_url": page_url,
        }).mappings().first()

        if row is None and event_id:
            row = db.execute(text("""
                SELECT case_id, category, status, created_at
                FROM support_cases
                WHERE source = 'switch_room' AND source_event_id = :source_event_id
            """), {"source_event_id": event_id}).mappings().first()
        if row is None:
            raise RuntimeError("Support case could not be persisted.")
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Your report could not be saved right now.") from exc

    return {
        "case_id": str(row["case_id"]),
        "category": row["category"],
        "status": row["status"],
        "created_at": row["created_at"],
        "reply": _reply(row["category"], page_url),
        "customer_safe": True,
    }
