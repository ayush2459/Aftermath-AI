import React, { useEffect, useState } from "react";
import { ArrowLeft, BrainCircuit, ClipboardCheck, MessageCircle, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const session = () => {
  const key = "aftermath_customer_session";
  let value = localStorage.getItem(key);
  if (!value) {
    value = "web-" + (crypto.randomUUID?.() || Date.now());
    localStorage.setItem(key, value);
  }
  return value;
};
const pretty = (value) => JSON.stringify(value, null, 2);

export default function GhostTrail() {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState("");
  const [investigation, setInvestigation] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [plan, setPlan] = useState(null);
  const [operator, setOperator] = useState("Demo operator");
  const [reason, setReason] = useState("Reviewed the evidence and accepted the proposed next step.");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const customerSession = session();
  const requestedOrderId = new URLSearchParams(window.location.search).get("order");

  const request = async (path, options = {}) => {
    const response = await fetch(`${API}${path}`, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Request failed.");
    return body;
  };

  const loadOrders = async () => {
    setBusy("loading");
    setError("");
    try {
      const data = await request(`/api/agent-tools/list_shipments?customer_session=${encodeURIComponent(customerSession)}`);
      const available = (data.shipments || []).filter((item) => item.incident_id);
      setOrders(available);
      const requested = requestedOrderId && available.find((item) => item.order_id === requestedOrderId);
      if (requested) setSelected(requested.incident_id);
      else if (!selected && available.length) setSelected(available[0].incident_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  useEffect(() => { loadOrders(); }, []);

  const investigate = async () => {
    if (!selected) return;
    setBusy("investigate"); setError(""); setDiagnosis(null); setPlan(null);
    try {
      const data = await request(`/api/agent-tools/investigate/${selected}?customer_session=${encodeURIComponent(customerSession)}`);
      setInvestigation(data);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const diagnose = async () => {
    if (!selected) return;
    setBusy("diagnose"); setError("");
    try {
      const data = await request(`/api/agent-tools/diagnose/${selected}?customer_session=${encodeURIComponent(customerSession)}`, { method: "POST" });
      setDiagnosis(data);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const propose = async () => {
    if (!selected) return;
    setBusy("propose"); setError("");
    try {
      const data = await request(`/api/recovery/propose/${selected}?customer_session=${encodeURIComponent(customerSession)}`, { method: "POST" });
      setPlan(data);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const decide = async (decision) => {
    if (!plan) return;
    setBusy("decision"); setError("");
    try {
      const data = await request(`/api/recovery/plans/${plan.plan_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_session: customerSession, decided_by: operator, decision, reason })
      });
      setPlan((old) => ({ ...old, approval: { ...old.approval, status: data.decision }, decision: data }));
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const executeDemoRecovery = async () => {
    if (!plan?.plan_id || plan.approval?.status !== "approved") return;
    setBusy("execute"); setError("");
    try {
      const data = await request(`/api/recovery/plans/${plan.plan_id}/execute-demo`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_session: customerSession })
      });
      setPlan((old) => ({ ...old, execution: data }));
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };
  return (
    <div className="ghosttrail-page">
      <header className="ghosttrail-top">
        <a href="/shipments" className="ghosttrail-back"><ArrowLeft size={16} /> Shipment monitoring</a>
        <span className="eyebrow">AFTERMATH AI / GHOSTTRAIL</span>
        <h1>Incident <em>investigation.</em></h1>
        <p>Collect persisted evidence, reconcile system states, generate an advisory diagnosis and prepare a safe recovery proposal.</p>
      </header>

      <section className="ghosttrail-panel">
        <div className="ghosttrail-panel-head">
          <div><span className="eyebrow">CASE SELECTION</span><h2>Select an incident</h2></div>
          <button className="ghosttrail-secondary" onClick={loadOrders} disabled={!!busy}><RefreshCw size={15}/> Refresh</button>
        </div>
        {orders.length ? (
          <select value={selected} onChange={(e) => { setSelected(e.target.value); setInvestigation(null); setDiagnosis(null); setPlan(null); }}>
            {orders.map((order) => <option value={order.incident_id} key={order.incident_id}>{order.incident_title || "Incident"} · {order.order_id}</option>)}
          </select>
        ) : <p className="ghosttrail-muted">No incidents found for this browser session. Create a test order with the demo failure first.</p>}
        {error && <p className="ghosttrail-error" role="alert">{error}</p>}
        <div className="ghosttrail-actions">
          <button className="ghosttrail-primary" onClick={investigate} disabled={!selected || !!busy}> {busy === "investigate" ? "Collecting evidence…" : "1 · Investigate"} </button>
          <button className="ghosttrail-secondary" onClick={diagnose} disabled={!selected || !!busy}> <BrainCircuit size={15}/> 2 · Diagnose </button>
          <button className="ghosttrail-secondary" onClick={propose} disabled={!selected || !!busy}> <ClipboardCheck size={15}/> 3 · Recovery plan </button>
        </div>
      </section>

      {investigation && <section className="ghosttrail-panel">
        <div className="ghosttrail-panel-head"><div><span className="eyebrow">GHOSTTRAIL / RECONCILIATION</span><h2>Evidence & findings</h2></div><span className="ghosttrail-tag">{investigation.findings.length} findings</span></div>
        <div className="ghosttrail-state-grid">
          {["order","payment","shipment"].map((key) => <div key={key}><small>{key.toUpperCase()}</small><b>{investigation.snapshot?.[key]?.status || "Record missing"}</b></div>)}
        </div>
        {investigation.findings.length ? investigation.findings.map((finding) => <div className="ghosttrail-finding" key={finding.code}><ShieldAlert size={17}/><div><b>{finding.code.replaceAll("_"," ")}</b><p>{finding.message}</p></div><span>{finding.severity}</span></div>) : <p className="ghosttrail-muted">No inconsistencies detected in persisted application records.</p>}
        <details><summary>View collected evidence JSON</summary><pre>{pretty(investigation.evidence)}</pre></details>
      </section>}

      {diagnosis && <section className="ghosttrail-panel">
        <div className="ghosttrail-panel-head"><div><span className="eyebrow">AI / ADVISORY DIAGNOSIS</span><h2><Sparkles size={19}/> Likely cause</h2></div><span className="ghosttrail-tag">{diagnosis.provider}</span></div>
        <h3>{diagnosis.diagnosis.summary}</h3>
        <p>{diagnosis.diagnosis.likely_cause}</p>
        <div className="ghosttrail-confidence">Confidence · {Math.round(diagnosis.diagnosis.confidence * 100)}%</div>
        <p><b>Recommended next step:</b> {diagnosis.diagnosis.recommended_next_step.replaceAll("_"," ")}</p>
        <p><b>Unknowns:</b> {(diagnosis.diagnosis.unknowns || []).join(" · ")}</p>
        <small>Diagnosis is advisory only. It does not change business state.</small>
      </section>}

      {plan && <section className="ghosttrail-panel">
        <div className="ghosttrail-panel-head"><div><span className="eyebrow">RECOVERY / PROPOSAL</span><h2>Recommended actions</h2></div><span className="ghosttrail-tag">{plan.approval?.status || "pending"}</span></div>
        {plan.plan.actions.map((action) => <article className="ghosttrail-action-card" key={action.action_type}>
          <b>{action.description}</b><p>Risk: {action.risk} · Approval required: {action.approval_required ? "Yes" : "No"}</p>
          <p><b>Preconditions:</b> {action.preconditions.join("; ")}</p>
          <p><b>Verification:</b> {action.verification}</p>
          <p><b>Idempotency:</b> {action.idempotency_key_strategy}</p>
        </article>)}
        <div className="ghosttrail-approval">
          <b>Demo operator decision</b>
          <p>This records an operator attestation only. It does not authenticate the operator or execute any action.</p>
          <input value={operator} onChange={(e) => setOperator(e.target.value)} aria-label="Operator display name" placeholder="Operator display name"/>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Decision reason"/>
          <div className="ghosttrail-actions">
            <button className="ghosttrail-primary" disabled={!!busy || !!plan.decision} onClick={() => decide("approved")}>Record approval</button>
            <button className="ghosttrail-secondary" disabled={!!busy || !!plan.decision} onClick={() => decide("rejected")}>Reject proposal</button>
          </div>
        </div>
        {plan.approval?.status === "approved" && !plan.execution && (
          <div className="ghosttrail-approval">
            <b>Approval recorded</b>
            <p>This records a simulation only; no parcel, carrier, payment, inventory or fulfillment record is changed.</p>
            <button className="ghosttrail-primary" disabled={!!busy} onClick={executeDemoRecovery}>
              {busy === "execute" ? "Recording…" : "Execute demo recovery"}
            </button>
          </div>
        )}
        {plan.execution?.status === "completed" && (
          <div className="ghosttrail-approval" role="status">
            <b>Approved demo recovery recorded</b>
            <p>Simulation only. Real fulfillment remains unchanged.</p>
            <a href={plan.execution.customer_url}>Open customer shipment page</a>
            <div className="discord-help-card ghosttrail-discord-next">
              <div className="discord-help-icon"><MessageCircle size={21} /></div>
              <div className="discord-help-copy">
                <span className="eyebrow">CONTINUE CUSTOMER SUPPORT</span>
                <b>GhostTrail has completed its investigation and recorded the approved demo recovery.</b>
                <p>Continue in Discord for customer-facing explanations and support. Include order reference: {plan.execution.order_id}</p>
              </div>
              <a className="discord-help-button" href="https://discord.gg/6sCDwusbw" target="_blank" rel="noopener noreferrer">
                Continue with Aftermath AI on Discord <MessageCircle size={15} />
              </a>
            </div>
          </div>
        )}
      </section>}
      <p className="ghosttrail-disclaimer">Demo environment · Razorpay Test Mode · Carrier failures are simulated · No payment, inventory or shipment actions are executed by GhostTrail.</p>
    </div>
  );
}
