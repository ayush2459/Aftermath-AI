import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, AlertTriangle, ArrowLeft, CheckCircle2, Clock3, RefreshCw, ShieldCheck, Workflow } from "lucide-react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const date = (value) => value ? new Date(value).toLocaleString("en-IN") : "—";
const label = (value) => String(value || "unknown").replaceAll("_", " ").replaceAll(".", " ");

function OperationsDashboard() {
  const [data, setData] = useState({ metrics: {}, incidents: [] });
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(API + "/api/operations/overview");
      if (!response.ok) throw new Error("Operations data is unavailable.");
      const next = await response.json();
      setData(next);
      setError("");
      if (selected) {
        const current = await fetch(API + "/api/operations/incidents/" + encodeURIComponent(selected));
        if (current.ok) setDetail(await current.json());
      }
    } catch (e) { setError(e.message); }
  }, [selected]);

  const openIncident = async (id) => {
    setSelected(id);
    setBusy(true);
    try {
      const response = await fetch(API + "/api/operations/incidents/" + encodeURIComponent(id));
      if (!response.ok) throw new Error("Could not load incident details.");
      setDetail(await response.json());
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 5000); return () => window.clearInterval(timer); }, [refresh]);

  const metrics = data.metrics || {};
  const incident = detail?.incident;
  return <main className="ops-page">
    <header className="ops-header">
      <a href="/" className="ops-back"><ArrowLeft size={15}/> Storefront</a>
      <div className="ops-heading-row"><div><span className="ops-eyebrow">AFTERMATH AI · INTERNAL WORKSPACE</span><h1>Operations <em>control room.</em></h1><p>Monitor incidents, investigate evidence, review recovery proposals and follow execution events.</p></div><button onClick={refresh}><RefreshCw size={15}/> Refresh</button></div>
      <div className="ops-live"><span/> LIVE DATA · refreshes every 5 seconds</div>
    </header>
    {error && <div className="ops-error"><AlertTriangle size={16}/>{error}</div>}
    <section className="ops-kpis">
      {[["Open incidents",metrics.open_incidents ?? 0],["High severity",metrics.high_severity ?? 0],["Pending approvals",metrics.pending_approvals ?? 0],["Recovery plans",metrics.proposed_plans ?? 0],["Completed actions",metrics.completed_recoveries ?? 0]].map(([name,value])=><article key={name}><small>{name}</small><b>{value}</b></article>)}
    </section>
    <div className="ops-layout">
      <section className="ops-panel ops-incident-list"><div className="ops-panel-title"><div><span className="ops-eyebrow">INCIDENT QUEUE</span><h2>Active and recent cases</h2></div><span>{data.incidents.length} CASES</span></div>
        {data.incidents.length ? data.incidents.map((item)=><button className={"ops-incident "+(selected===item.incident_id?"selected":"")} key={item.incident_id} onClick={()=>openIncident(item.incident_id)}>
          <div className="ops-incident-top"><b>{item.title}</b><span className={"ops-severity "+String(item.severity).toLowerCase()}>{label(item.severity)}</span></div>
          <p>{item.summary}</p><div className="ops-incident-meta"><span>Order {String(item.order_id).slice(0,8)}…</span><span>{label(item.status)}</span><span>{date(item.updated_at)}</span></div>
          <div className="ops-state-row"><span>Payment: {label(item.payment_status)}</span><span>Shipment: {label(item.shipment_status)}</span></div>
        </button>) : <p className="ops-empty">No incidents have been recorded yet.</p>}
      </section>
      <section className="ops-panel ops-detail">
        {!selected || !incident ? <div className="ops-empty-state"><Workflow size={30}/><h2>Select an incident</h2><p>Its evidence, recovery proposals, approval state, event timeline and audit history will appear here.</p></div> : <>
          <div className="ops-panel-title"><div><span className="ops-eyebrow">CASE DETAIL</span><h2>{incident.title}</h2></div><span className="ops-status">{label(incident.status)}</span></div>
          <p className="ops-summary">{incident.summary}</p>
          <div className="ops-facts"><div><small>ORDER</small><b>{incident.order_id}</b></div><div><small>PAYMENT</small><b>{label(incident.payment_status)}</b></div><div><small>SHIPMENT</small><b>{label(incident.shipment_status)}</b></div><div><small>SEVERITY</small><b>{label(incident.severity)}</b></div></div>
          <section className="ops-subsection"><h3><ShieldCheck size={17}/> Recovery plan comparison</h3>
            {detail.plans?.length ? detail.plans.map((plan)=><article className="ops-plan" key={plan.plan_id}><div className="ops-plan-head"><b>Proposal · {String(plan.plan_id).slice(0,8)}</b><span>{label(plan.status)} · approval {label(plan.approval_status)}</span></div><small>Created {date(plan.created_at)}</small>{(plan.plan?.actions||[]).map((action,index)=><div className="ops-action" key={action.action_type}><b>{index+1}. {label(action.action_type)}</b><p>{action.description}</p><div>Risk: {label(action.risk)} · Approval required: {action.approval_required?"Yes":"No"}</div><small>Expected: {action.expected_effect}</small><small>Verify: {action.verification}</small></div>)}{plan.decision_reason&&<p className="ops-decision">Decision: {plan.decision_reason}</p>}</article>) : <p className="ops-empty">No recovery proposal exists yet. Open GhostTrail for this order to investigate and prepare one.</p>}
          </section>
          <section className="ops-subsection"><h3><Activity size={17}/> Live execution timeline</h3>{detail.events?.length ? detail.events.map(event=><div className="ops-timeline" key={event.event_id}><span/><div><b>{label(event.event_type)}</b><p>{event.message}</p><small>{event.source} · {date(event.created_at)}</small></div></div>) : <p className="ops-empty">No events recorded.</p>}</section>
          <section className="ops-subsection"><h3><Clock3 size={17}/> Audit trail</h3>{detail.audit?.length ? detail.audit.map((entry,index)=><div className="ops-audit" key={index}><b>{label(entry.action)} · {label(entry.decision)}</b><p>{entry.reason}</p><small>{entry.actor_type}/{entry.actor_id} · {date(entry.created_at)}</small></div>) : <p className="ops-empty">No audit records.</p>}</section>
          <div className="ops-note"><CheckCircle2 size={16}/> This workspace records current application state. Recovery execution remains simulated unless a real provider integration is explicitly configured.</div>
        </>}
        {busy && <div className="ops-loading">Loading incident…</div>}
      </section>
    </div>
    <footer className="ops-footer">Internal operations surface · Customer shipment pages remain simple and customer-focused.</footer>
  </main>;
}

if (window.location.pathname.replace(/\/+$/, "") === "/operations") {
  createRoot(document.getElementById("root")).render(<React.StrictMode><OperationsDashboard/></React.StrictMode>);
} else {
  const App = (await import("./App.jsx")).default;
  createRoot(document.getElementById("root")).render(<React.StrictMode><App/></React.StrictMode>);
}
