import React, { useEffect, useRef, useState } from "react";
import { ArrowLeft, BrainCircuit, CheckCircle2, Circle, Clock3, MessageCircle, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";

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

const STEPS = [
  ["detect", "Incident detected", "Aftermath AI has identified a failed order."],
  ["investigate", "GhostTrail evidence collection", "Reconciling the order, payment, inventory, shipment and event history."],
  ["diagnose", "AI diagnosis", "Preparing an evidence-based explanation and recommended next step."],
  ["plan", "Recovery plan prepared", "Creating a guarded recovery proposal for Discord review."],
  ["discord", "Handed off to Discord", "The Discord bot will handle the remaining review and recovery flow."]
];

export default function GhostTrail() {
  const [order, setOrder] = useState(null);
  const [step, setStep] = useState(-1);
  const [investigation, setInvestigation] = useState(null);
  const [diagnosis, setDiagnosis] = useState(null);
  const [plan, setPlan] = useState(null);
  const [handoff, setHandoff] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);
  const started = useRef(false);
  const customerSession = session();
  const requestedOrderId = new URLSearchParams(window.location.search).get("order");

  const request = async (path, options = {}) => {
    const response = await fetch(`${API}${path}`, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "The background workflow could not continue.");
    return body;
  };

  const runWorkflow = async (incident) => {
    if (started.current) return;
    started.current = true;
    setBusy(true);
    setError("");
    try {
      setStep(0);
      setOrder(incident);
      const incidentId = incident.incident_id;
      const sessionQuery = `customer_session=${encodeURIComponent(customerSession)}`;

      setStep(1);
      const evidence = await request(`/api/agent-tools/investigate/${incidentId}?${sessionQuery}`);
      setInvestigation(evidence);

      setStep(2);
      const diagnosisResult = await request(`/api/agent-tools/diagnose/${incidentId}?${sessionQuery}`, { method: "POST" });
      setDiagnosis(diagnosisResult);

      setStep(3);
      const planResult = await request(`/api/recovery/propose/${incidentId}?${sessionQuery}`, { method: "POST" });
      setPlan(planResult);

      // This records that GhostTrail has prepared the case for Discord.
      // The Discord CONFIRM command remains the explicit execution gate.
      await request(`/api/recovery/plans/${planResult.plan_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_session: customerSession,
          decided_by: "GhostTrail background workflow",
          decision: "approved",
          reason: "Evidence collection, advisory diagnosis and recovery proposal completed. Discord confirmation is still required before execution."
        })
      });

      const handoffResult = await request("/api/discord/recovery/handoffs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_session: customerSession,
          incident_id: incidentId,
          plan_id: planResult.plan_id
        })
      });
      setHandoff(handoffResult);
      setStep(4);
      setFinished(true);
    } catch (e) {
      setError(e.message || "Workflow failed.");
    } finally {
      setBusy(false);
    }
  };

  const loadAndRun = async () => {
    if (started.current) return;
    setBusy(true);
    setError("");
    try {
      const data = await request(`/api/agent-tools/list_shipments?customer_session=${encodeURIComponent(customerSession)}`);
      const incidents = (data.shipments || []).filter((item) => item.incident_id);
      const selected = (requestedOrderId && incidents.find((item) => item.order_id === requestedOrderId)) || incidents[0];
      if (!selected) {
        setBusy(false);
        setError("No incident is available yet. Create a test order with the seeded shipment failure, then refresh this page.");
        return;
      }
      await runWorkflow(selected);
    } catch (e) {
      setBusy(false);
      setError(e.message || "Could not detect an incident.");
    }
  };

  useEffect(() => { loadAndRun(); }, []);

  const retry = () => {
    started.current = false;
    setOrder(null); setStep(-1); setInvestigation(null); setDiagnosis(null);
    setPlan(null); setHandoff(null); setFinished(false); setError("");
    loadAndRun();
  };

  const copyCaseCode = async () => {
    if (!handoff?.case_code) return;
    try { await navigator.clipboard.writeText(handoff.case_code); }
    catch { setError("Clipboard access is unavailable. Copy the case code manually."); }
  };

  return (
    <main className="ghosttrail-page">
      <header className="ghosttrail-top">
        <a href="/shipments" className="ghosttrail-back"><ArrowLeft size={16} /> Shipment monitoring</a>
        <span className="eyebrow">AFTERMATH AI / GHOSTTRAIL</span>
        <h1>Incident <em>recovery pipeline.</em></h1>
        <p>Aftermath AI detects the failure, GhostTrail investigates and prepares the recovery case automatically. Discord takes over from there.</p>
      </header>

      <section className="ghosttrail-panel">
        <div className="ghosttrail-panel-head">
          <div><span className="eyebrow">AUTOMATED BACKGROUND WORKFLOW</span><h2>{order ? `Order ${order.order_id}` : "Detecting an incident…"}</h2></div>
          <span className="ghosttrail-tag">{finished ? "Handed to Discord" : busy ? "Running" : error ? "Needs attention" : "Waiting"}</span>
        </div>
        <div className="ghosttrail-pipeline">
          {STEPS.map(([id, title, description], index) => {
            const complete = step > index || (finished && step === index);
            const current = step === index && !finished;
            return (
              <div className={`ghosttrail-pipeline-step ${complete ? "complete" : current ? "current" : "pending"}`} key={id}>
                <span className="ghosttrail-pipeline-icon">{complete ? <CheckCircle2 size={19}/> : current ? <RefreshCw size={18} className="spin"/> : <Circle size={18}/>}</span>
                <div><b>{title}</b><p>{description}</p></div>
                <small>{complete ? "Complete" : current ? "Running" : "Pending"}</small>
              </div>
            );
          })}
        </div>
        {error && <div className="ghosttrail-error" role="alert">{error}</div>}
        {!busy && error && <button className="ghosttrail-secondary" onClick={retry}><RefreshCw size={15}/> Retry workflow</button>}
        {busy && <p className="ghosttrail-muted"><Clock3 size={14}/> This process runs automatically. Keep this page open until the Discord handoff is ready.</p>}
      </section>

      {investigation && (
        <section className="ghosttrail-panel">
          <div className="ghosttrail-panel-head"><div><span className="eyebrow">GHOSTTRAIL / EVIDENCE</span><h2><ShieldAlert size={18}/> Investigation summary</h2></div><span className="ghosttrail-tag">{investigation.findings?.length || 0} findings</span></div>
          <div className="ghosttrail-state-grid">
            {["order", "payment", "shipment"].map((key) => <div key={key}><small>{key.toUpperCase()}</small><b>{investigation.snapshot?.[key]?.status || "Record missing"}</b></div>)}
          </div>
          {(investigation.findings || []).map((finding) => <div className="ghosttrail-finding" key={finding.code}><ShieldAlert size={17}/><div><b>{finding.code.replaceAll("_", " ")}</b><p>{finding.message}</p></div><span>{finding.severity}</span></div>)}
          {diagnosis && <div className="ghosttrail-diagnosis"><span className="eyebrow"><Sparkles size={13}/> AI DIAGNOSIS · {diagnosis.provider}</span><h3>{diagnosis.diagnosis.summary}</h3><p>{diagnosis.diagnosis.likely_cause}</p><p><b>Recommended next step:</b> {diagnosis.diagnosis.recommended_next_step.replaceAll("_", " ")}</p><small>Advisory diagnosis based on persisted application evidence.</small></div>}
          {plan && <div className="ghosttrail-action-card"><b>Recovery proposal</b>{plan.plan.actions.map((action) => <div key={action.action_type}><p>{action.description}</p><p>Risk: {action.risk} · Confirmation required in Discord: Yes</p></div>)}</div>}
        </section>
      )}

      {handoff && (
        <section className="ghosttrail-panel ghosttrail-handoff-ready">
          <div className="ghosttrail-panel-head"><div><span className="eyebrow">NEXT STEP · DISCORD BOT</span><h2><MessageCircle size={19}/> GhostTrail handoff complete</h2></div><span className="ghosttrail-tag">Ready</span></div>
          <p>GhostTrail has completed detection, evidence collection, diagnosis and recovery planning. The existing Discord bot flow now takes over. Review the case there and send the confirmation command only when ready.</p>
          <div className="ghosttrail-handoff-code">
            <span className="eyebrow">ONE-TIME CASE CODE · EXPIRES IN 60 MINUTES</span>
            <code>{handoff.case_code}</code>
            <button className="ghosttrail-secondary" type="button" onClick={copyCaseCode}>Copy case code</button>
          </div>
          <p>In the configured Aftermath AI recovery channel, send:</p>
          <pre>CASE {handoff.case_code}</pre>
          <p>The bot will return the GhostTrail diagnosis and approved proposal. To continue the existing simulated recovery, explicitly send:</p>
          <pre>CONFIRM {handoff.case_code}</pre>
          {handoff.discord_invite_url && <a className="discord-help-button" href={handoff.discord_invite_url} target="_blank" rel="noopener noreferrer">Open Aftermath AI Discord <MessageCircle size={15}/></a>}
          <small>Case expires: {new Date(handoff.expires_at).toLocaleString()} · Existing Discord confirmation and execution flow retained.</small>
        </section>
      )}

      <p className="ghosttrail-disclaimer">The first three stages are automated in this page. Discord handles the remaining confirmation and recovery flow. Current recovery remains a simulation: no carrier API is contacted and no physical parcel is created or moved.</p>
    </main>
  );
}
