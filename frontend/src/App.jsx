import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleHelp, CreditCard, Headphones, LockKeyhole, Minus, Plus, ShieldCheck, ShoppingBag, Sparkles, Truck, X } from "lucide-react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const money = (paise) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format((paise || 0) / 100);

// Use a stable, explicit asset URL for the headphones and cache-bust static images
// so browsers do not keep an earlier corrupted response.
const productImage = (product) => {
  const path = product.product_id === "aurora-headphones"
    ? "/static/products/aurora-headphones.jpg"
    : (product.image_url || "");
  const isAbsolute = path.startsWith("http://") || path.startsWith("https://");
  const url = isAbsolute ? path : `${API}${path.startsWith("/") ? path : `/${path}`}`;
  return `${url}${url.includes("?") ? "&" : "?"}v=20261030-2`;
};

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
    if (!value) { value = "web-" + (crypto.randomUUID?.() || Date.now()); localStorage.setItem(key, value); }
    return value;
  });

  useEffect(() => {
    fetch(`${API}/api/products`)
      .then(async (r) => { if (!r.ok) throw new Error("Could not load products from the API."); return r.json(); })
      .then(setProducts)
      .catch((e) => setNotice({ type: "error", message: e.message + " Check that FastAPI is running." }))
      .finally(() => setLoading(false));
  }, []);

  const items = useMemo(() => products.filter(p => cart[p.product_id] > 0).map(p => ({ ...p, quantity: cart[p.product_id] })), [products, cart]);
  const count = items.reduce((n, p) => n + p.quantity, 0);
  const total = items.reduce((n, p) => n + p.price_paise * p.quantity, 0);

  const changeQty = (id, delta) => setCart(prev => {
    const next = { ...prev };
    const value = (next[id] || 0) + delta;
    if (value <= 0) delete next[id]; else next[id] = Math.min(value, 25);
    return next;
  });

  const loadCheckout = () => new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve();
    const existing = document.querySelector('script[data-razorpay-checkout]');
    if (existing) { existing.addEventListener("load", resolve, { once: true }); existing.addEventListener("error", reject, { once: true }); return; }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.dataset.razorpayCheckout = "true";
    script.onload = resolve;
    script.onerror = () => reject(new Error("Razorpay Checkout could not be loaded. Check your internet connection."));
    document.body.appendChild(script);
  });

  const startPayment = async () => {
    if (!items.length || checkoutBusy) return;
    setCheckoutBusy(true); setNotice(null); setResult(null);
    try {
      const orderResponse = await fetch(`${API}/api/payments/razorpay/orders`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_session: customerSession, items: items.map(p => ({ product_id: p.product_id, quantity: p.quantity })) })
      });
      const order = await orderResponse.json();
      if (!orderResponse.ok) throw new Error(order.detail || "Unable to create payment order.");
      await loadCheckout();
      const checkout = new window.Razorpay({
        key: order.key_id, amount: order.amount, currency: order.currency, name: order.name,
        description: order.description, order_id: order.razorpay_order_id,
        theme: { color: "#a3e635" },
        modal: { ondismiss: () => { setCheckoutBusy(false); setNotice({ type: "info", message: "Checkout closed. Your order is still pending; you can try again." }); } },
        handler: async (response) => {
          try {
            const verifyResponse = await fetch(`${API}/api/payments/razorpay/verify`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                order_id: order.order_id,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature
              })
            });
            const verified = await verifyResponse.json();
            if (!verifyResponse.ok) throw new Error(verified.detail || "Payment verification failed.");
            setResult({ ...verified, localOrderId: order.order_id, paymentId: response.razorpay_payment_id, amount: order.amount });
            setCart({});
            setNotice({ type: "success", message: "Payment verified by the Aftermath AI backend." });
          } catch (e) {
            setNotice({ type: "error", message: e.message + " Do not retry payment blindly; check the order status first." });
          } finally { setCheckoutBusy(false); }
        }
      });
      checkout.on("payment.failed", (event) => {
        const description = event?.error?.description || "Payment was not completed. You can retry checkout.";
        setNotice({ type: "error", message: description });
        setCheckoutBusy(false);
      });
      checkout.open();
    } catch (e) {
      setNotice({ type: "error", message: e.message });
      setCheckoutBusy(false);
    }
  };

  return <div className="app-shell">
    <div className="announcement"><Sparkles size={14}/> A smarter way to shop — built for resilient commerce <span>TEST STORE</span></div>
    <header className="topbar">
      <a className="brand" href="#"><span className="brand-mark"><span/></span><span>aftermath<span className="brand-ai">.ai</span><small>COMMERCE, WITH A PLAN B.</small></span></a>
      <nav><a className="active" href="#shop">Shop</a><a href="#story">How it works</a><a href="#support">Support</a></nav>
      <a className="cart-pill" href="#order-summary"><ShoppingBag size={17}/><span>Bag</span><b>{count}</b></a>
    </header>

    <main>
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><span/> THE EVERYDAY TECH EDIT</div>
          <h1>Good things.<br/><em>Thoughtfully</em> chosen.</h1>
          <p>Useful tech for the way you work, create and unwind. A smoother checkout, backed by a smarter recovery experience.</p>
          <a className="hero-link" href="#shop">Explore the collection <ArrowRight size={16}/></a>
          <div className="hero-proof"><div className="proof-icons"><span><ShieldCheck size={15}/></span><span><LockKeyhole size={14}/></span></div><div><b>Secure test checkout</b><small>Payments verified server-side</small></div></div>
        </div>
        <div className="hero-art">
          <div className="orbit orbit-one"/><div className="orbit orbit-two"/>
          <div className="hero-glow"/>
          <div className="hero-product"><img src={`${API}/static/products/aurora-headphones.jpg`} alt="Aurora wireless headphones"/></div>
          <div className="floating-tag tag-top"><span className="tag-dot"/> CURATED TECH <b>01 / 05</b></div>
          <div className="floating-tag tag-bottom"><span><Sparkles size={15}/></span><div><b>Made for momentum</b><small>Small upgrades. Better days.</small></div></div>
          <div className="hero-index">A—01</div>
        </div>
      </section>

      <section className="trust-strip">
        <div><ShieldCheck/><span><b>Protected checkout</b><small>Razorpay secure flow</small></span></div>
        <div><Truck/><span><b>Order visibility</b><small>Track every key event</small></span></div>
        <div><Headphones/><span><b>Human support</b><small>Help when you need it</small></span></div>
        <div><Sparkles/><span><b>Recovery ready</b><small>Resilience built in</small></span></div>
      </section>

      <section className="shop-section" id="shop">
        <div className="section-heading"><div><div className="eyebrow">THE COLLECTION / 2026</div><h2>Tools for <em>what's next.</em></h2><p>Considered essentials. No unnecessary noise.</p></div><div className="collection-count">05 <span>PRODUCTS</span></div></div>
        {loading ? <div className="loading-state">Preparing the collection<span className="loader"/></div> :
          <div className="product-grid">{products.map((p, i) => <article className="product-card" key={p.product_id}>
            <div className="product-image"><span className="product-number">0{i + 1}</span><img src={productImage(p)} alt={p.name}/><span className="image-label">AFTER EFFECTS / OBJECTS</span></div>
            <div className="product-info"><div><h3>{p.name}</h3><p>{p.description}</p></div><div className="product-bottom"><b>{money(p.price_paise)}</b><div className="quantity-control"><button aria-label="Remove one" onClick={() => changeQty(p.product_id, -1)} disabled={!cart[p.product_id]}><Minus size={14}/></button><span>{cart[p.product_id] || 0}</span><button aria-label="Add one" onClick={() => changeQty(p.product_id, 1)} disabled={p.stock_quantity <= (cart[p.product_id] || 0)}><Plus size={14}/></button></div></div><div className="stock-line">{p.stock_quantity} available <span>·</span> Inclusive of all taxes</div></div>
          </article>)}</div>}
      </section>

      <section className="checkout-section" id="order-summary">
        <div className="checkout-intro"><div className="eyebrow">YOUR NEXT GOOD THING</div><h2>Ready when<br/><em>you are.</em></h2><p>Your order is created securely on our server. Razorpay handles checkout; Aftermath verifies the result before starting the recovery workflow.</p><div className="checkout-note"><LockKeyhole size={16}/> Test mode · No real money is charged</div></div>
        <div className="summary-card">
          <div className="summary-title"><div><span className="eyebrow">THE DETAILS</span><h3>Order summary</h3></div><span className="bag-count">{count} ITEMS</span></div>
          {items.length ? <div className="summary-items">{items.map(p => <div className="summary-item" key={p.product_id}><img src={p.image_url?.startsWith("http") ? p.image_url : `${API}${p.image_url || ""}`} alt=""/><div className="summary-item-name"><b>{p.name}</b><small>Qty {p.quantity}</small></div><strong>{money(p.price_paise * p.quantity)}</strong></div>)}</div> : <div className="empty-cart"><ShoppingBag size={24}/><b>Your bag is taking a breather.</b><span>Add something from the collection to get started.</span></div>}
          <div className="summary-total"><span>Subtotal</span><b>{money(total)}</b></div><div className="summary-total muted"><span>Shipping</span><b>Complimentary</b></div><div className="grand-total"><span>Total due</span><strong>{money(total)}</strong></div>
          <button className="pay-button" disabled={!items.length || checkoutBusy} onClick={startPayment}>{checkoutBusy ? "Preparing secure checkout…" : <>Continue to secure payment <ArrowRight size={17}/></>}</button>
          <div className="payment-foot"><LockKeyhole size={13}/> Secured by Razorpay <span>·</span> INR</div>
          <div className="payment-brands"><span>UPI</span><span>VISA</span><span>mastercard</span><span>RuPay</span><span>Netbanking</span></div>
        </div>
      </section>

      {notice && <div className={`notice ${notice.type}`} role="status"><span>{notice.type === "success" ? <Check size={18}/> : <CircleHelp size={18}/>}</span><p>{notice.message}</p><button onClick={() => setNotice(null)} aria-label="Dismiss"><X size={16}/></button></div>}

      {result && <section className="result-panel"><div className="result-icon"><Check size={24}/></div><div className="eyebrow">PAYMENT VERIFIED</div><h2>You're all set.<br/><em>We've got this.</em></h2><p>Your test payment was verified by the backend. The demo has now recorded a shipment allocation failure so you can explore Aftermath AI's recovery workflow.</p><div className="result-details"><div><small>ORDER REFERENCE</small><b>{result.localOrderId}</b></div><div><small>PAYMENT ID</small><b>{result.paymentId}</b></div><div><small>ORDER STATUS</small><b>Recovery required</b></div></div><div className="recovery-callout"><Sparkles size={18}/><span><b>Recovery workflow started</b><small>Shipment failure incident created. Open the API docs to inspect the shipment agent tools.</small></span><a href={`${API}/docs`} target="_blank" rel="noreferrer">View API <ArrowRight size={14}/></a></div></section>}

      <section className="story-section" id="story"><div className="story-mark">A.</div><div><div className="eyebrow">BUILT FOR THE UNEXPECTED</div><h2>Commerce doesn't stop<br/>at <em>checkout.</em></h2></div><p>Aftermath AI helps teams understand what went wrong and coordinate what happens next. This storefront demonstrates the payment-to-recovery journey with a safe test transaction.</p></section>
    </main>
    <footer id="support"><a className="brand footer-brand" href="#"><span className="brand-mark"><span/></span><span>aftermath<span className="brand-ai">.ai</span><small>COMMERCE, WITH A PLAN B.</small></span></a><span>© 2026 AFTERMATH AI · DEMO EXPERIENCE</span><a href={`${API}/docs`} target="_blank" rel="noreferrer">Developer API <ArrowRight size={13}/></a></footer>
  </div>;
}

export default App;