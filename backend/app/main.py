import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import CORS_ORIGINS
from .db import get_db
from .schemas import OrderCreateIn, OrderCreatedOut, ProductOut

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Aftermath AI API",
    description="Hackathon demo API for order failure investigation and recovery.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def root():
    return {"name": "Aftermath AI API", "docs": "/docs", "health": "/health"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc

@app.get("/api/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT product_id, name, description, price_paise, currency,
               stock_quantity, image_url
        FROM products WHERE is_active = TRUE ORDER BY name
    """)).mappings().all()
    return [dict(row) for row in rows]

@app.post("/api/orders", response_model=OrderCreatedOut, status_code=201)
def create_order(payload: OrderCreateIn, db: Session = Depends(get_db)):
    requested = {}
    for item in payload.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    try:
        with db.begin():
            product_rows = db.execute(
                text("""
                    SELECT product_id, name, price_paise, stock_quantity
                    FROM products
                    WHERE product_id = ANY(:product_ids) AND is_active = TRUE
                    FOR UPDATE
                """),
                {"product_ids": list(requested.keys())},
            ).mappings().all()
            products = {row["product_id"]: dict(row) for row in product_rows}
            missing = set(requested) - set(products)
            if missing:
                raise HTTPException(status_code=404, detail=f"Unknown product(s): {', '.join(sorted(missing))}")
            for product_id, quantity in requested.items():
                if products[product_id]["stock_quantity"] < quantity:
                    raise HTTPException(status_code=409, detail=f"Insufficient stock for {product_id}")

            total_paise = sum(products[pid]["price_paise"] * qty for pid, qty in requested.items())
            order_id = uuid4()
            correlation_id = uuid4()
            incident_id = uuid4()
            db.execute(text("""
                INSERT INTO orders (order_id, customer_session, status, total_paise, currency, incident_id)
                VALUES (:order_id, :session, 'recovery_required', :total, 'INR', :incident_id)
            """), {"order_id": order_id, "session": payload.customer_session, "total": total_paise, "incident_id": incident_id})

            for product_id, quantity in requested.items():
                product = products[product_id]
                db.execute(text("""
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price_paise)
                    VALUES (:order_id, :product_id, :quantity, :price)
                """), {"order_id": order_id, "product_id": product_id, "quantity": quantity, "price": product["price_paise"]})
                db.execute(text("UPDATE products SET stock_quantity = stock_quantity - :qty WHERE product_id = :pid"), {"qty": quantity, "pid": product_id})
                db.execute(text("""
                    INSERT INTO inventory_reservations (order_id, product_id, quantity, status, idempotency_key)
                    VALUES (:order_id, :product_id, :quantity, 'reserved', :key)
                """), {"order_id": order_id, "product_id": product_id, "quantity": quantity, "key": f"reserve:{order_id}:{product_id}"})

            db.execute(text("""
                INSERT INTO payments (order_id, status, amount_paise, currency, simulated_provider_ref, idempotency_key)
                VALUES (:order_id, 'captured', :amount, 'INR', :provider_ref, :key)
            """), {"order_id": order_id, "amount": total_paise, "provider_ref": f"SIM-{order_id}", "key": f"payment:{order_id}"})
            db.execute(text("""
                INSERT INTO shipments (order_id, status, idempotency_key, last_error)
                VALUES (:order_id, 'failed', :key, 'Seeded demo failure: carrier allocation timeout')
            """), {"order_id": order_id, "key": f"shipment:{order_id}"})
            db.execute(text("""
                INSERT INTO incidents (incident_id, order_id, status, severity, title, summary, correlation_id)
                VALUES (:incident_id, :order_id, 'open', 'high', 'Shipment creation failed',
                        'The simulated carrier allocation request timed out after payment capture.', :correlation_id)
            """), {"incident_id": incident_id, "order_id": order_id, "correlation_id": correlation_id})
            event_payload = json.dumps({"failure": "carrier_allocation_timeout", "simulated": True})
            db.execute(text("""
                INSERT INTO events (incident_id, order_id, source, event_type, severity, message, payload, correlation_id)
                VALUES (:incident_id, :order_id, 'shipping-service', 'shipment.failed', 'high',
                        'Carrier allocation timed out; shipment was not created.', CAST(:payload AS JSONB), :correlation_id)
            """), {"incident_id": incident_id, "order_id": order_id, "payload": event_payload, "correlation_id": correlation_id})
            db.execute(text("""
                INSERT INTO audit_log (incident_id, actor_type, actor_id, action, decision, reason, details)
                VALUES (:incident_id, 'system', 'order-api', 'create_demo_order', 'recorded',
                        'Simulated payment succeeded; seeded shipping failure created for recovery demo.', CAST(:details AS JSONB))
            """), {"incident_id": incident_id, "details": json.dumps({"order_id": str(order_id), "correlation_id": str(correlation_id), "simulated": True})})

        return OrderCreatedOut(
            order_id=order_id,
            status="recovery_required",
            total_paise=total_paise,
            payment_status="captured",
            shipment_status="failed",
            incident_id=incident_id,
            message="Order created. Simulated payment captured; shipment failure recorded for recovery.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        # Keep internal database details out of the API response.
        raise HTTPException(status_code=500, detail="Could not create demo order; inspect backend logs.") from exc

@app.get("/api/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT o.order_id, o.customer_session, o.status, o.total_paise, o.currency,
               o.created_at, o.incident_id, p.status AS payment_status,
               s.status AS shipment_status, s.last_error
        FROM orders o
        LEFT JOIN payments p ON p.order_id = o.order_id
        LEFT JOIN shipments s ON s.order_id = o.order_id
        WHERE o.order_id = :order_id
    """), {"order_id": order_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return dict(row)
