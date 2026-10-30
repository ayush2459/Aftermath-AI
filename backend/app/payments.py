import json
from uuid import UUID, uuid4

import razorpay
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_MODE
from .db import get_db
from .schemas import OrderCreateIn

router = APIRouter(prefix="/api/payments/razorpay", tags=["Razorpay payments"])


def get_client():
    if RAZORPAY_MODE != "test":
        raise HTTPException(status_code=503, detail="This integration is configured for Test Mode only.")
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=503, detail="Razorpay test keys are not configured on the server.")
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


class VerifyPaymentIn(BaseModel):
    order_id: UUID
    razorpay_order_id: str = Field(min_length=5, max_length=80)
    razorpay_payment_id: str = Field(min_length=5, max_length=80)
    razorpay_signature: str = Field(min_length=32, max_length=256)


@router.post("/orders", status_code=201)
def create_razorpay_order(payload: OrderCreateIn, db: Session = Depends(get_db)):
    client = get_client()
    requested = {}
    for item in payload.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    rows = db.execute(text("""
        SELECT product_id, name, price_paise, stock_quantity
        FROM products
        WHERE product_id = ANY(:ids) AND is_active = TRUE
    """), {"ids": list(requested)}).mappings().all()
    products = {r["product_id"]: dict(r) for r in rows}
    missing = set(requested) - set(products)
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown product(s): {', '.join(sorted(missing))}")
    for pid, qty in requested.items():
        if products[pid]["stock_quantity"] < qty:
            raise HTTPException(status_code=409, detail=f"Insufficient stock for {pid}")

    total_paise = sum(products[pid]["price_paise"] * qty for pid, qty in requested.items())
    local_order_id = uuid4()
    receipt = f"af-{local_order_id.hex[:24]}"
    try:
        rz_order = client.order.create(data={
            "amount": total_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": {"aftermath_order_id": str(local_order_id), "environment": "test"},
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Razorpay could not create a test order.") from exc

    try:
        with db.begin():
            db.execute(text("""
                INSERT INTO orders(order_id, customer_session, status, total_paise, currency)
                VALUES (:id, :session, 'payment_pending', :amount, 'INR')
            """), {"id": local_order_id, "session": payload.customer_session, "amount": total_paise})
            for pid, qty in requested.items():
                db.execute(text("""
                    INSERT INTO order_items(order_id, product_id, quantity, unit_price_paise)
                    VALUES (:oid, :pid, :qty, :price)
                """), {"oid": local_order_id, "pid": pid, "qty": qty, "price": products[pid]["price_paise"]})
            db.execute(text("""
                INSERT INTO payments(order_id, status, amount_paise, currency, idempotency_key,
                                     provider, razorpay_order_id)
                VALUES (:oid, 'pending', :amount, 'INR', :key, 'razorpay_test', :rzid)
            """), {"oid": local_order_id, "amount": total_paise,
                  "key": f"razorpay:{local_order_id}", "rzid": rz_order["id"]})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not save the pending payment order.") from exc

    return {
        "order_id": str(local_order_id),
        "razorpay_order_id": rz_order["id"],
        "amount": total_paise,
        "currency": "INR",
        "key_id": RAZORPAY_KEY_ID,
        "mode": "test",
        "name": "Aftermath AI",
        "description": "Test payment for your demo order",
    }


@router.post("/verify")
def verify_razorpay_payment(payload: VerifyPaymentIn, db: Session = Depends(get_db)):
    client = get_client()
    payment = db.execute(text("""
        SELECT p.payment_id, p.status, p.amount_paise, p.razorpay_order_id,
               o.status AS order_status, o.total_paise
        FROM payments p JOIN orders o ON o.order_id = p.order_id
        WHERE p.order_id = :oid
        FOR UPDATE
    """), {"oid": payload.order_id}).mappings().first()
    if not payment:
        raise HTTPException(status_code=404, detail="Pending order not found.")
    if payment["razorpay_order_id"] != payload.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Razorpay order does not match this order.")
    if payment["status"] == "captured":
        return {"verified": True, "status": "captured", "order_id": str(payload.order_id),
                "message": "Payment was already verified."}
    if payment["status"] != "pending":
        raise HTTPException(status_code=409, detail="This payment is not pending.")

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature,
        })
        remote_payment = client.payment.fetch(payload.razorpay_payment_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payment signature or Razorpay payment could not be verified.") from exc

    if remote_payment.get("order_id") != payload.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Payment is not linked to the expected Razorpay order.")
    if int(remote_payment.get("amount", -1)) != int(payment["amount_paise"]):
        raise HTTPException(status_code=400, detail="Verified payment amount does not match the order.")
    if remote_payment.get("currency") != "INR":
        raise HTTPException(status_code=400, detail="Unexpected payment currency.")
    if remote_payment.get("status") != "captured":
        raise HTTPException(status_code=409, detail="Payment is verified but not captured. Enable automatic capture in Razorpay Test Mode and retry.")

    incident_id, correlation_id = uuid4(), uuid4()
    try:
        with db.begin():
            # Lock inventory and re-check stock after the customer completes checkout.
            items = db.execute(text("""
                SELECT oi.product_id, oi.quantity, oi.unit_price_paise, p.stock_quantity
                FROM order_items oi JOIN products p ON p.product_id = oi.product_id
                WHERE oi.order_id = :oid FOR UPDATE OF p
            """), {"oid": payload.order_id}).mappings().all()
            if not items:
                raise HTTPException(status_code=409, detail="Order has no items.")
            for item in items:
                if item["stock_quantity"] < item["quantity"]:
                    db.execute(text("UPDATE payments SET status='unknown' WHERE order_id=:oid"), {"oid": payload.order_id})
                    raise HTTPException(status_code=409, detail="Payment captured but inventory is insufficient; manual reconciliation is required.")

            db.execute(text("""
                UPDATE payments SET status='captured', razorpay_payment_id=:pid,
                    razorpay_signature=:sig, captured_at=NOW()
                WHERE order_id=:oid
            """), {"pid": payload.razorpay_payment_id, "sig": payload.razorpay_signature, "oid": payload.order_id})
            db.execute(text("UPDATE orders SET status='recovery_required', incident_id=:iid WHERE order_id=:oid"),
                       {"iid": incident_id, "oid": payload.order_id})
            for item in items:
                db.execute(text("UPDATE products SET stock_quantity=stock_quantity-:qty WHERE product_id=:pid"),
                           {"qty": item["quantity"], "pid": item["product_id"]})
                db.execute(text("""
                    INSERT INTO inventory_reservations(order_id, product_id, quantity, status, idempotency_key)
                    VALUES (:oid, :pid, :qty, 'reserved', :key)
                    ON CONFLICT (order_id, product_id) DO NOTHING
                """), {"oid": payload.order_id, "pid": item["product_id"], "qty": item["quantity"],
                       "key": f"reserve:{payload.order_id}:{item['product_id']}"})
            db.execute(text("""
                INSERT INTO shipments(order_id, status, idempotency_key, last_error)
                VALUES (:oid, 'failed', :key, 'Seeded demo failure: carrier allocation timeout')
            """), {"oid": payload.order_id, "key": f"shipment:{payload.order_id}"})
            db.execute(text("""
                INSERT INTO incidents(incident_id, order_id, status, severity, title, summary, correlation_id)
                VALUES (:iid, :oid, 'open', 'high', 'Shipment creation failed',
                  'Razorpay test payment captured; seeded carrier allocation timeout created for recovery demo.', :cid)
            """), {"iid": incident_id, "oid": payload.order_id, "cid": correlation_id})
            db.execute(text("""
                INSERT INTO events(incident_id, order_id, source, event_type, severity, message, payload, correlation_id)
                VALUES (:iid, :oid, 'shipping-service', 'shipment.failed', 'high',
                  'Carrier allocation timed out after verified test payment.',
                  CAST(:payload AS JSONB), :cid)
            """), {"iid": incident_id, "oid": payload.order_id,
                   "payload": json.dumps({"failure":"carrier_allocation_timeout","payment_provider":"razorpay_test","payment_id":payload.razorpay_payment_id}),
                   "cid": correlation_id})
            db.execute(text("""
                INSERT INTO audit_log(incident_id, actor_type, actor_id, action, decision, reason, details)
                VALUES (:iid, 'system', 'razorpay-verifier', 'verify_test_payment', 'accepted',
                  'Razorpay signature, order, amount, currency and captured status verified.',
                  CAST(:details AS JSONB))
            """), {"iid": incident_id, "details": json.dumps({"order_id":str(payload.order_id),"razorpay_payment_id":payload.razorpay_payment_id,"mode":"test"})})
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Payment verified with Razorpay, but local finalization failed; reconcile before retrying.") from exc

    return {"verified": True, "status": "captured", "order_id": str(payload.order_id),
            "incident_id": str(incident_id),
            "message": "Test payment verified. Order entered the Aftermath AI recovery workflow."}
