
import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  CircleHelp,
  Headphones,
  LockKeyhole,
  Minus,
  Plus,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Truck,
  X,
  RefreshCw,
  AlertTriangle,
  Clock3
} from "lucide-react";

const API = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const money = (paise) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
  }).format((paise || 0) / 100);

const productImage = (product) => {
  const path =
    product.product_id === "aurora-headphones"
      ? "/static/products/aurora-headphones.jpg"
      : product.image_url || "";

  const isAbsolute =
    path.startsWith("http://") || path.startsWith("https://");

  const url = isAbsolute
    ? path
    : `${API}${path.startsWith("/") ? path : `/${path}`}`;

  return `${url}${url.includes("?") ? "&" : "?"}v=20261030-3`;
};

const formatDate = (value) => {
  if (!value) return "Time unavailable";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Time unavailable";
  }

  return date.toLocaleString("en-IN");
};

const readable = (value) =>
  (value || "unknown")
    .replaceAll("_", " ")
    .replaceAll(".", " ");

function App() {
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState({});
  const [loading, setLoading] = useState(true);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [result, setResult] = useState(null);

  const [customerSession] = useState(() => {
    const key = "aftermath_customer_session";
    let value = localStorage.getItem(key);

    if (!value) {
      value = "web-" + (crypto.randomUUID?.() || Date.now());
      localStorage.setItem(key, value);
    }

    return value;
  });

  // Shipment dashboard state
  const [shipments, setShipments] = useState([]);
  const [shipmentsLoading, setShipmentsLoading] = useState(true);
  const [shipmentError, setShipmentError] = useState("");
  const [timelines, setTimelines] = useState({});
  const [timelineErrors, setTimelineErrors] = useState({});

  // Fetch shipment records and their actual event timelines
  const refreshShipments = async () => {
    setShipmentsLoading(true);
    setShipmentError("");

    try {
      const response = await fetch(
        `${API}/api/agent-tools/list_shipments`
      );

      if (!response.ok) {
        throw new Error("Could not load shipment information.");
      }

      const data = await response.json();
      const records = data.shipments || [];

      setShipments(records);

      const timelineResults = await Promise.all(
        records.map(async (shipment) => {
          if (!shipment.order_id) {
            return {
              orderId: null,
              events: [],
              error: "Order reference unavailable."
            };
          }

          try {
            const timelineResponse = await fetch(
              `${API}/api/agent-tools/get_shipment_timeline?order_id=${encodeURIComponent(
                shipment.order_id
              )}`
            );

            if (!timelineResponse.ok) {
              throw new Error("Timeline could not be loaded.");
            }

            const timeline = await timelineResponse.json();

            return {
              orderId: shipment.order_id,
              events: timeline.events || [],
              error: ""
            };
          } catch (error) {
            return {
              orderId: shipment.order_id,
              events: [],
              error: error.message
            };
          }
        })
      );

      const nextTimelines = {};
      const nextErrors = {};

      timelineResults.forEach((item) => {
        if (!item.orderId) return;

        nextTimelines[item.orderId] = item.events;
        nextErrors[item.orderId] = item.error;
      });

      setTimelines(nextTimelines);
      setTimelineErrors(nextErrors);
    } catch (error) {
      setShipmentError(error.message);
    } finally {
      setShipmentsLoading(false);
    }
  };

  useEffect(() => {
    refreshShipments();
  }, []);

  // Fetch products
  useEffect(() => {
    fetch(`${API}/api/products`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Could not load products from the API.");
        }

        return response.json();
      })
      .then(setProducts)
      .catch((error) =>
        setNotice({
          type: "error",
          message:
            error.message + " Check that FastAPI is running."
        })
      )
      .finally(() => setLoading(false));
  }, []);

  // Cart calculations
  const items = useMemo(
    () =>
      products
        .filter((product) => cart[product.product_id] > 0)
        .map((product) => ({
          ...product,
          quantity: cart[product.product_id]
        })),
    [products, cart]
  );

  const count = items.reduce(
    (total, product) => total + product.quantity,
    0
  );

  const total = items.reduce(
    (amount, product) =>
      amount + product.price_paise * product.quantity,
    0
  );

  const changeQty = (id, delta) =>
    setCart((previous) => {
      const next = { ...previous };
      const value = (next[id] || 0) + delta;

      if (value <= 0) {
        delete next[id];
      } else {
        next[id] = Math.min(value, 25);
      }

      return next;
    });

  // Load Razorpay checkout script
  const loadCheckout = () =>
    new Promise((resolve, reject) => {
      if (window.Razorpay) {
        return resolve();
      }

      const existing = document.querySelector(
        'script[data-razorpay-checkout]'
      );

      if (existing) {
        existing.addEventListener("load", resolve, {
          once: true
        });
        existing.addEventListener("error", reject, {
          once: true
        });
        return;
      }

      const script = document.createElement("script");
      script.src =
        "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      script.dataset.razorpayCheckout = "true";
      script.onload = resolve;
      script.onerror = () =>
        reject(
          new Error(
            "Razorpay Checkout could not be loaded. Check your internet connection."
          )
        );

      document.body.appendChild(script);
    });

  // Start payment
  const startPayment = async () => {
    if (!items.length || checkoutBusy) return;

    setCheckoutBusy(true);
    setNotice(null);
    setResult(null);

    try {
      const orderResponse = await fetch(
        `${API}/api/payments/razorpay/orders`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            customer_session: customerSession,
            items: items.map((product) => ({
              product_id: product.product_id,
              quantity: product.quantity
            }))
          })
        }
      );

      const order = await orderResponse.json();

      if (!orderResponse.ok) {
        throw new Error(
          order.detail || "Unable to create payment order."
        );
      }

      await loadCheckout();

      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: order.name,
        description: order.description,
        order_id: order.razorpay_order_id,

        theme: {
          color: "#a3e635"
        },

        modal: {
          ondismiss: () => {
            setCheckoutBusy(false);
            setNotice({
              type: "info",
              message:
                "Checkout closed. Your order is still pending; you can try again."
            });
          }
        },

        handler: async (response) => {
          try {
            const verifyResponse = await fetch(
              `${API}/api/payments/razorpay/verify`,
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/json"
                },
                body: JSON.stringify({
                  order_id: order.order_id,
                  razorpay_order_id:
                    response.razorpay_order_id,
                  razorpay_payment_id:
                    response.razorpay_payment_id,
                  razorpay_signature:
                    response.razorpay_signature
                })
              }
            );

            const verified = await verifyResponse.json();

            if (!verifyResponse.ok) {
              throw new Error(
                verified.detail ||
                  "Payment verification failed."
              );
            }

            setResult({
              ...verified,
              localOrderId: order.order_id,
              paymentId: response.razorpay_payment_id,
              amount: order.amount
            });

            setCart({});

            setNotice({
              type: "success",
              message:
                "Payment verified by the Aftermath AI backend."
            });

            await refreshShipments();
          } catch (error) {
            setNotice({
              type: "error",
              message:
                error.message +
                " Do not retry payment blindly; check the order status first."
            });
          } finally {
            setCheckoutBusy(false);
          }
        }
      });

      checkout.on("payment.failed", (event) => {
        const description =
          event?.error?.description ||
          "Payment was not completed. You can retry checkout.";

        setNotice({
          type: "error",
          message: description
        });

        setCheckoutBusy(false);
      });

      checkout.open();
    } catch (error) {
      setNotice({
        type: "error",
        message: error.message
      });

      setCheckoutBusy(false);
    }
  };

  // Build a workflow view from the known demo incident.
  // These are explanatory stages, not independently recorded events.
  const getRecoveryStages = (shipment) => {
    const failed =
      shipment.shipment_status === "failed" ||
      shipment.order_status === "recovery_required";

    return [
      {
        title: "Payment verification",
        description:
          "Payment verification is handled by the backend.",
        status: "completed"
      },
      {
        title: "Carrier allocation",
        description: failed
          ? "Carrier allocation request timed out."
          : "Carrier allocation status depends on shipment data.",
        status: failed ? "failed" : "pending"
      },
      {
        title: "Shipment creation",
        description: failed
          ? "Shipment was not created after the allocation failure."
          : "Shipment creation status is not confirmed here.",
        status: failed ? "blocked" : "pending"
      },
      {
        title: "Recovery investigation",
        description: failed
          ? "Incident requires investigation and resolution."
          : "No active recovery requirement is confirmed.",
        status: failed ? "attention" : "pending"
      }
    ];
  };

  const getRootCause = (shipment) => {
    const events = timelines[shipment.order_id] || [];

    const failedEvent = events.find(
      (event) =>
        event.event_type === "shipment.failed" ||
        event.payload?.failure ===
          "carrier_allocation_timeout"
    );

    if (failedEvent) {
      return {
        title: "Carrier allocation timeout",
        description: failedEvent.message,
        source: failedEvent.source || "Unknown source"
      };
    }

    if (shipment.last_error) {
      return {
        title: shipment.incident_title || "Shipment issue",
        description: shipment.last_error,
        source: "Shipment record"
      };
    }

    return null;
  };

  return (
    <div className="app-shell">
      <div className="announcement">
        <Sparkles size={14} />
        A smarter way to shop — built for resilient commerce
        <span>TEST STORE</span>
      </div>

      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-mark">
            <span />
          </span>
          <span>
            aftermath<span className="brand-ai">.ai</span>
            <small>COMMERCE, WITH A PLAN B.</small>
          </span>
        </a>

        <nav>
          <a className="active" href="#shop">Shop</a>
          <a href="#story">How it works</a>
          <a href="#support">Support</a>
        </nav>

        <a className="cart-pill" href="#order-summary">
          <ShoppingBag size={17} />
          <span>Bag</span>
          <b>{count}</b>
        </a>
      </header>

      <main>
        {/* HERO */}
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <span /> THE EVERYDAY TECH EDIT
            </div>

            <h1>
              Good things.<br />
              <em>Thoughtfully</em> chosen.
            </h1>

            <p>
              Useful tech for the way you work, create and unwind.
              A smoother checkout, backed by a smarter recovery experience.
            </p>

            <a className="hero-link" href="#shop">
              Explore the collection <ArrowRight size={16} />
            </a>

            <div className="hero-proof">
              <div className="proof-icons">
                <span><ShieldCheck size={15} /></span>
                <span><LockKeyhole size={14} /></span>
              </div>
              <div>
                <b>Secure test checkout</b>
                <small>Payments verified server-side</small>
              </div>
            </div>
          </div>

          <div className="hero-art">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="hero-glow" />

            <div className="hero-product">
              <img
                src={`${API}/static/products/aurora-headphones.jpg`}
                alt="Aurora wireless headphones"
              />
            </div>

            <div className="floating-tag tag-top">
              <span className="tag-dot" />
              CURATED TECH <b>01 / 05</b>
            </div>

            <div className="floating-tag tag-bottom">
              <span><Sparkles size={15} /></span>
              <div>
                <b>Made for momentum</b>
                <small>Small upgrades. Better days.</small>
              </div>
            </div>

            <div className="hero-index">A—01</div>
          </div>
        </section>

        {/* TRUST STRIP */}
        <section className="trust-strip">
          <div>
            <ShieldCheck />
            <span>
              <b>Protected checkout</b>
              <small>Razorpay secure flow</small>
            </span>
          </div>

          <div>
            <Truck />
            <span>
              <b>Order visibility</b>
              <small>Track every key event</small>
            </span>
          </div>

          <div>
            <Headphones />
            <span>
              <b>Human support</b>
              <small>Help when you need it</small>
            </span>
          </div>

          <div>
            <Sparkles />
            <span>
              <b>Recovery ready</b>
              <small>Resilience built in</small>
            </span>
          </div>
        </section>

        {/* SHOP */}
        <section className="shop-section" id="shop">
          <div className="section-heading">
            <div>
              <div className="eyebrow">THE COLLECTION / 2026</div>
              <h2>Tools for <em>what's next.</em></h2>
              <p>Considered essentials. No unnecessary noise.</p>
            </div>

            <div className="collection-count">
              05 <span>PRODUCTS</span>
            </div>
          </div>

          {loading ? (
            <div className="loading-state">
              Preparing the collection
              <span className="loader" />
            </div>
          ) : (
            <div className="product-grid">
              {products.map((product, index) => (
                <article
                  className="product-card"
                  key={product.product_id}
                >
                  <div className="product-image">
                    <span className="product-number">
                      0{index + 1}
                    </span>

                    <img
                      src={productImage(product)}
                      alt={product.name}
                    />

                    <span className="image-label">
                      AFTER EFFECTS / OBJECTS
                    </span>
                  </div>

                  <div className="product-info">
                    <div>
                      <h3>{product.name}</h3>
                      <p>{product.description}</p>
                    </div>

                    <div className="product-bottom">
                      <b>{money(product.price_paise)}</b>

                      <div className="quantity-control">
                        <button
                          aria-label="Remove one"
                          onClick={() =>
                            changeQty(product.product_id, -1)
                          }
                          disabled={!cart[product.product_id]}
                        >
                          <Minus size={14} />
                        </button>

                        <span>
                          {cart[product.product_id] || 0}
                        </span>

                        <button
                          aria-label="Add one"
                          onClick={() =>
                            changeQty(product.product_id, 1)
                          }
                          disabled={
                            product.stock_quantity <=
                            (cart[product.product_id] || 0)
                          }
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    </div>

                    <div className="stock-line">
                      {product.stock_quantity} available
                      <span>·</span>
                      Inclusive of all taxes
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        {/* SHIPMENT DASHBOARD */}
        <section className="shipment-dashboard" id="tracking">
          <div className="section-heading">
            <div>
              <div className="eyebrow">
                AFTERMATH AI / LIVE OPERATIONS
              </div>
              <h2>Shipment <em>monitor.</em></h2>
              <p>
                Track order status, inspect recorded events and
                investigate shipment incidents.
              </p>
            </div>

            <button
              className="tracking-refresh"
              onClick={refreshShipments}
              disabled={shipmentsLoading}
            >
              <RefreshCw size={16} />
              {shipmentsLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          {shipmentsLoading ? (
            <div className="loading-state">
              Loading shipment records
              <span className="loader" />
            </div>
          ) : shipmentError ? (
            <div className="tracking-empty">
              <p>{shipmentError}</p>
              <button onClick={refreshShipments}>
                Try again
              </button>
            </div>
          ) : shipments.length === 0 ? (
            <div className="tracking-empty">
              No shipment records found yet.
            </div>
          ) : (
            <div className="shipment-list">
              {shipments.map((shipment) => {
                const events = [
                  ...(timelines[shipment.order_id] || [])
                ].sort(
                  (a, b) =>
                    new Date(a.occurred_at || 0) -
                    new Date(b.occurred_at || 0)
                );

                const stages = getRecoveryStages(shipment);
                const rootCause = getRootCause(shipment);

                return (
                  <article
                    className="shipment-card"
                    key={
                      shipment.shipment_id || shipment.order_id
                    }
                  >
                    <div className="shipment-card-top">
                      <div>
                        <span className="eyebrow">
                          ORDER REFERENCE
                        </span>
                        <h3>{shipment.order_id}</h3>
                      </div>

                      <span
                        className={`shipment-status ${
                          shipment.shipment_status || "unknown"
                        }`}
                      >
                        {readable(shipment.shipment_status)}
                      </span>
                    </div>

                    <div className="shipment-metrics">
                      <div>
                        <small>ORDER STATUS</small>
                        <b>{readable(shipment.order_status)}</b>
                      </div>

                      <div>
                        <small>INCIDENT</small>
                        <b>
                          {shipment.incident_status || "None"}
                        </b>
                      </div>

                      <div>
                        <small>SEVERITY</small>
                        <b>
                          {shipment.incident_severity || "—"}
                        </b>
                      </div>

                      <div>
                        <small>ORDER VALUE</small>
                        <b>{money(shipment.total_paise)}</b>
                      </div>
                    </div>

                    <div className="shipment-issue">
                      <AlertTriangle size={18} />

                      <div>
                        <b>
                          {shipment.incident_title ||
                            "No incident recorded"}
                        </b>

                        <p>
                          {shipment.last_error ||
                            shipment.incident_summary ||
                            "No shipment issue reported."}
                        </p>
                      </div>
                    </div>

                    {/* LATEST EVENT */}
                    <div className="shipment-event">
                      <span className="event-dot" />

                      <div>
                        <small>
                          LATEST EVENT ·{" "}
                          {shipment.latest_event_type || "No event"}
                        </small>

                        <p>
                          {shipment.latest_event_message ||
                            "No event message available."}
                        </p>

                        {shipment.latest_event_at && (
                          <time>
                            {formatDate(shipment.latest_event_at)}
                          </time>
                        )}
                      </div>
                    </div>

                    {/* ACTUAL RECORDED EVENT TIMELINE */}
                    <div className="incident-timeline">
                      <div className="timeline-heading">
                        <div>
                          <span className="eyebrow">
                            INVESTIGATION / EVENT LOG
                          </span>
                          <h4>Shipment timeline</h4>
                        </div>

                        <span className="timeline-count">
                          {events.length} EVENTS
                        </span>
                      </div>

                      {timelineErrors[shipment.order_id] ? (
                        <p className="timeline-empty">
                          {timelineErrors[shipment.order_id]}
                        </p>
                      ) : events.length > 0 ? (
                        <div className="timeline-list">
                          {events.map((event) => (
                            <div
                              className="timeline-entry"
                              key={event.event_id}
                            >
                              <span
                                className={`timeline-marker ${
                                  event.severity === "high"
                                    ? "high"
                                    : ""
                                }`}
                              />

                              <div className="timeline-entry-content">
                                <div className="timeline-entry-top">
                                  <b>
                                    {readable(event.event_type)}
                                  </b>

                                  <span>
                                    {event.severity || "info"}
                                  </span>
                                </div>

                                <p>{event.message}</p>

                                <small>
                                  {event.source || "Unknown source"}
                                  {" · "}
                                  {formatDate(event.occurred_at)}
                                </small>

                                {event.payload?.simulated && (
                                  <small className="simulated-label">
                                    SIMULATED DEMO EVENT
                                  </small>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="timeline-empty">
                          No recorded shipment events are available.
                        </p>
                      )}
                    </div>

                    {/* RECOVERY WORKFLOW */}
                    <div className="recovery-stages">
                      <div className="timeline-heading">
                        <div>
                          <span className="eyebrow">
                            RECOVERY / WORKFLOW
                          </span>
                          <h4>Recovery stages</h4>
                        </div>

                        <span className="timeline-count">
                          WORKFLOW VIEW
                        </span>
                      </div>

                      {stages.map((stage, index) => (
                        <div
                          className="recovery-stage"
                          key={stage.title}
                        >
                          <span
                            className={`stage-number ${stage.status}`}
                          >
                            {stage.status === "completed" ? (
                              <Check size={13} />
                            ) : (
                              index + 1
                            )}
                          </span>

                          <div>
                            <b>{stage.title}</b>
                            <p>{stage.description}</p>
                          </div>

                          <span
                            className={`stage-status ${stage.status}`}
                          >
                            {stage.status}
                          </span>
                        </div>
                      ))}

                      {rootCause && (
                        <div className="root-cause">
                          <span className="eyebrow">
                            IDENTIFIED ROOT CAUSE
                          </span>

                          <b>{rootCause.title}</b>

                          <p>{rootCause.description}</p>

                          <small>
                            Source: {rootCause.source}
                          </small>
                        </div>
                      )}
                    </div>

                    <div className="shipment-footer">
                      <span>
                        <Truck size={15} />
                        {shipment.carrier_name ||
                          "Carrier not assigned"}
                      </span>

                      <span>
                        {shipment.tracking_number ||
                          "Tracking number unavailable"}
                      </span>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        {/* CHECKOUT */}
        <section className="checkout-section" id="order-summary">
          <div className="checkout-intro">
            <div className="eyebrow">YOUR NEXT GOOD THING</div>

            <h2>
              Ready when<br />
              <em>you are.</em>
            </h2>

            <p>
              Your order is created securely on our server.
              Razorpay handles checkout; Aftermath verifies the result
              before starting the recovery workflow.
            </p>

            <div className="checkout-note">
              <LockKeyhole size={16} />
              Test mode · No real money is charged
            </div>
          </div>

          <div className="summary-card">
            <div className="summary-title">
              <div>
                <span className="eyebrow">THE DETAILS</span>
                <h3>Order summary</h3>
              </div>

              <span className="bag-count">{count} ITEMS</span>
            </div>

            {items.length ? (
              <div className="summary-items">
                {items.map((product) => (
                  <div
                    className="summary-item"
                    key={product.product_id}
                  >
                    <img
                      src={productImage(product)}
                      alt=""
                    />

                    <div className="summary-item-name">
                      <b>{product.name}</b>
                      <small>Qty {product.quantity}</small>
                    </div>

                    <strong>
                      {money(
                        product.price_paise * product.quantity
                      )}
                    </strong>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-cart">
                <ShoppingBag size={24} />
                <b>Your bag is taking a breather.</b>
                <span>
                  Add something from the collection to get started.
                </span>
              </div>
            )}

            <div className="summary-total">
              <span>Subtotal</span>
              <b>{money(total)}</b>
            </div>

            <div className="summary-total muted">
              <span>Shipping</span>
              <b>Complimentary</b>
            </div>

            <div className="grand-total">
              <span>Total due</span>
              <strong>{money(total)}</strong>
            </div>

            <button
              className="pay-button"
              disabled={!items.length || checkoutBusy}
              onClick={startPayment}
            >
              {checkoutBusy ? (
                "Preparing secure checkout…"
              ) : (
                <>
                  Continue to secure payment
                  <ArrowRight size={17} />
                </>
              )}
            </button>

            <div className="payment-foot">
              <LockKeyhole size={13} />
              Secured by Razorpay <span>·</span> INR
            </div>

            <div className="payment-brands">
              <span>UPI</span>
              <span>VISA</span>
              <span>mastercard</span>
              <span>RuPay</span>
              <span>Netbanking</span>
            </div>
          </div>
        </section>

        {/* NOTIFICATIONS */}
        {notice && (
          <div
            className={`notice ${notice.type}`}
            role="status"
          >
            <span>
              {notice.type === "success" ? (
                <Check size={18} />
              ) : (
                <CircleHelp size={18} />
              )}
            </span>

            <p>{notice.message}</p>

            <button
              onClick={() => setNotice(null)}
              aria-label="Dismiss"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* PAYMENT RESULT */}
        {result && (
          <section className="result-panel">
            <div className="result-icon">
              <Check size={24} />
            </div>

            <div className="eyebrow">PAYMENT VERIFIED</div>

            <h2>
              You're all set.<br />
              <em>We've got this.</em>
            </h2>

            <p>
              Your test payment was verified by the backend.
              The demo has now recorded a shipment allocation failure
              so you can explore Aftermath AI's recovery workflow.
            </p>

            <div className="result-details">
              <div>
                <small>ORDER REFERENCE</small>
                <b>{result.localOrderId}</b>
              </div>

              <div>
                <small>PAYMENT ID</small>
                <b>{result.paymentId}</b>
              </div>

              <div>
                <small>ORDER STATUS</small>
                <b>Recovery required</b>
              </div>
            </div>

            <div className="recovery-callout">
              <Sparkles size={18} />

              <span>
                <b>Recovery workflow started</b>
                <small>
                  Shipment failure incident created. Open the API docs
                  to inspect the shipment agent tools.
                </small>
              </span>

              <a
                href={`${API}/docs`}
                target="_blank"
                rel="noreferrer"
              >
                View API <ArrowRight size={14} />
              </a>
            </div>
          </section>
        )}

        {/* STORY */}
        <section className="story-section" id="story">
          <div className="story-mark">A.</div>

          <div>
            <div className="eyebrow">
              BUILT FOR THE UNEXPECTED
            </div>

            <h2>
              Commerce doesn't stop<br />
              at <em>checkout.</em>
            </h2>
          </div>

          <p>
            Aftermath AI helps teams understand what went wrong and
            coordinate what happens next. This storefront demonstrates
            the payment-to-recovery journey with a safe test transaction.
          </p>
        </section>
      </main>

      {/* FOOTER */}
      <footer id="support">
        <a className="brand footer-brand" href="#">
          <span className="brand-mark">
            <span />
          </span>
          <span>
            aftermath<span className="brand-ai">.ai</span>
            <small>COMMERCE, WITH A PLAN B.</small>
          </span>
        </a>

        <span>© 2026 AFTERMATH AI · DEMO EXPERIENCE</span>

        <a
          href={`${API}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          Developer API <ArrowRight size={13} />
        </a>
      </footer>
    </div>
  );
}

export default App;
