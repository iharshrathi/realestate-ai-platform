import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import FollowUpCard from "../components/FollowUpCard";
import { AsyncBoundary, Badge, Button, Card, EmptyState, ErrorMessage, LEAD_STATUSES, SyntheticTag } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { formatDate, formatInr, formatPercent, humanize } from "../utils/format";

const INTERACTION_TYPES = ["note", "call", "email", "whatsapp", "sms", "meeting", "site_visit", "enquiry"];
const DIRECTION_ICON = { inbound: "←", outbound: "→", internal: "•" };

function ScorePanel({ prediction, onScore, busy }) {
  if (!prediction) {
    return (
      <div className="space-y-3">
        <EmptyState title="Not scored yet" />
        <Button onClick={onScore} disabled={busy} className="w-full">{busy ? "Scoring…" : "Score this lead"}</Button>
      </div>
    );
  }
  const maxImpact = Math.max(...prediction.factors.map((f) => Math.abs(f.impact)), 0.01);
  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-4xl font-semibold text-slate-900">{formatPercent(prediction.probability)}</p>
          <p className="text-xs text-slate-500">conversion probability</p>
        </div>
        <Badge value={prediction.band} className="text-sm" />
      </div>
      <div>
        <p className="label">Why this score</p>
        <ul className="space-y-2">
          {prediction.factors.map((f) => {
            const positive = f.direction === "increases";
            return (
              <li key={f.factor} className="text-xs">
                <div className="mb-0.5 flex justify-between">
                  <span className="font-medium text-slate-700">{f.factor}: <span className="font-normal text-slate-500">{f.value}</span></span>
                  <span className={positive ? "text-emerald-600" : "text-rose-600"}>
                    {positive ? "+" : "−"}{(Math.abs(f.impact) * 100).toFixed(1)} pts
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-100">
                  <div className={`h-1.5 rounded-full ${positive ? "bg-emerald-500" : "bg-rose-500"}`} style={{ width: `${(Math.abs(f.impact) / maxImpact) * 100}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="text-xs text-slate-400">Model {prediction.model_version} · scored {formatDate(prediction.created_at, true)}</p>
      <Button variant="secondary" size="sm" onClick={onScore} disabled={busy}>{busy ? "Scoring…" : "Re-score"}</Button>
    </div>
  );
}

function RequirementPanel({ requirement }) {
  if (!requirement) return <EmptyState title="No requirement captured" hint="Add an enquiry note and run the AI pipeline to extract one." />;
  const budget = requirement.budget_min || requirement.budget_max
    ? `${formatInr(requirement.budget_min)} – ${formatInr(requirement.budget_max)}`
    : "—";
  const rows = [
    ["Budget", budget],
    ["Location", requirement.preferred_location || "—"],
    ["Type", humanize(requirement.property_type)],
    ["Bedrooms", requirement.bedrooms ?? "—"],
    ["Timeline", requirement.purchase_timeline_days != null ? `${requirement.purchase_timeline_days} days` : "—"],
    ["Urgency", humanize(requirement.urgency)],
    ["Intent", humanize(requirement.intent)],
    ["Loan pre-approved", requirement.loan_preapproved == null ? "—" : requirement.loan_preapproved ? "Yes" : "No"],
  ];
  return (
    <>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-slate-500">{k}</dt>
            <dd className="font-medium text-slate-800">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-slate-400">Source: {humanize(requirement.source)} · {formatDate(requirement.created_at)}</p>
    </>
  );
}

function Timeline({ leadId }) {
  const interactions = useAsync(() => api.interactions(leadId), [leadId]);
  const [form, setForm] = useState({ type: "note", content: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function add(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.addInteraction(leadId, form);
      setForm((f) => ({ ...f, content: "" }));
      interactions.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Interaction timeline">
      <form onSubmit={add} className="mb-4 flex flex-col gap-2 sm:flex-row">
        <select className="input sm:w-36" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} aria-label="Interaction type">
          {INTERACTION_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
        </select>
        <input className="input" required placeholder="What happened?" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
        <Button type="submit" disabled={busy || !form.content.trim()}>Add</Button>
      </form>
      <ErrorMessage error={error} />
      <AsyncBoundary state={interactions}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="No interactions yet" />
          ) : (
            <ol className="space-y-3 border-l-2 border-slate-100 pl-4">
              {items.map((i) => (
                <li key={i.id} className="relative">
                  <span className="absolute -left-[1.4rem] top-1 flex h-4 w-4 items-center justify-center rounded-full bg-white text-[10px] text-brand-600 ring-2 ring-slate-200">
                    {DIRECTION_ICON[i.direction]}
                  </span>
                  <p className="text-xs text-slate-500">{humanize(i.type)} · {i.direction} · {formatDate(i.occurred_at, true)}</p>
                  <p className="whitespace-pre-wrap text-sm text-slate-700">{i.content || "—"}</p>
                </li>
              ))}
            </ol>
          )
        }
      </AsyncBoundary>
    </Card>
  );
}

function AgentResult({ result }) {
  return (
    <div className="space-y-2 rounded-lg border border-brand-100 bg-brand-50 p-3 text-xs text-slate-700">
      <p className="font-medium text-brand-700">AI pipeline finished — {result.follow_up ? "a follow-up draft was created for your review." : "no follow-up needed."}</p>
      <ul className="space-y-0.5">
        {result.steps.map((s, i) => (
          <li key={i}>
            {s.status === "success" ? "✓" : "✗"} {humanize(s.agent)} · {humanize(s.action)} <span className="text-slate-400">({s.duration_ms} ms)</span>
            {s.error && <span className="text-rose-600"> — {s.error}</span>}
          </li>
        ))}
      </ul>
      <p className="text-slate-500">{result.note}</p>
    </div>
  );
}

export default function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isManager } = useAuth();
  const lead = useAsync(() => api.lead(id), [id]);
  const recs = useAsync(() => api.leadRecommendations(id), [id]);
  const followUps = useAsync(() => api.leadFollowUps(id), [id]);
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState(null);
  const [agentResult, setAgentResult] = useState(null);

  const refreshAll = () => {
    lead.reload();
    recs.reload();
    followUps.reload();
  };

  async function run(name, fn) {
    setBusy(name);
    setActionError(null);
    try {
      return await fn();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy("");
    }
  }

  const score = () => run("score", async () => { await api.scoreLead(id); lead.reload(); });
  const suggest = () => run("suggest", async () => { await api.suggestFollowUp(id); followUps.reload(); });
  const runAgents = () => run("agents", async () => { setAgentResult(await api.runAgents(id)); refreshAll(); });
  const changeStatus = (status) => run("status", async () => { await api.updateLead(id, { status }); lead.reload(); });
  const remove = () => {
    if (!window.confirm("Delete this lead and all its history?")) return;
    return run("delete", async () => { await api.deleteLead(id); navigate("/leads"); });
  };

  return (
    <AsyncBoundary state={lead}>
      {(l) => (
        <div className="space-y-6">
          <Link to="/leads" className="text-sm text-brand-600 hover:underline">← All leads</Link>

          <header className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="flex items-center gap-3 text-2xl font-semibold text-slate-900">
                {l.full_name} {l.is_synthetic && <SyntheticTag />}
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                {[l.email, l.phone].filter(Boolean).join(" · ")} · via {humanize(l.source)} · owner {l.assigned_to?.full_name || "unassigned"} · created {formatDate(l.created_at)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select className="input w-40" value={l.status} onChange={(e) => changeStatus(e.target.value)} disabled={busy === "status"} aria-label="Lead status">
                {LEAD_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
              </select>
              <Button onClick={runAgents} disabled={Boolean(busy)}>{busy === "agents" ? "Running…" : "✦ Run AI pipeline"}</Button>
              {isManager && <Button variant="danger" onClick={remove} disabled={Boolean(busy)}>Delete</Button>}
            </div>
          </header>

          <ErrorMessage error={actionError} />
          {agentResult && <AgentResult result={agentResult} />}

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              <Card title="Requirement"><RequirementPanel requirement={l.requirement} /></Card>
              <Timeline leadId={id} />
              <Card
                title="Follow-ups"
                action={<Button variant="secondary" size="sm" onClick={suggest} disabled={Boolean(busy)}>{busy === "suggest" ? "Drafting…" : "Suggest follow-up"}</Button>}
              >
                <AsyncBoundary state={followUps}>
                  {(items) =>
                    items.length === 0 ? (
                      <EmptyState title="No follow-ups yet" />
                    ) : (
                      <div className="space-y-4">
                        {items.map((f) => <FollowUpCard key={f.id} followUp={f} showLead={false} onChanged={followUps.reload} />)}
                      </div>
                    )
                  }
                </AsyncBoundary>
              </Card>
            </div>

            <div className="space-y-6">
              <Card title="Lead score">
                <ScorePanel prediction={l.latest_prediction} onScore={score} busy={busy === "score"} />
              </Card>
              <Card title="Recommended properties">
                <AsyncBoundary state={recs}>
                  {(items) =>
                    items.length === 0 ? (
                      <EmptyState title="No matching properties" hint="Capture a requirement to get recommendations." />
                    ) : (
                      <ul className="space-y-3">
                        {items.map((r) => (
                          <li key={r.property.id} className="text-sm">
                            <div className="flex justify-between gap-2">
                              <span className="font-medium">{r.property.title}</span>
                              <span className="shrink-0 text-xs font-semibold text-brand-600">{formatPercent(r.match_score)}</span>
                            </div>
                            <p className="text-xs text-slate-500">{r.property.location} · {formatInr(r.property.price_inr)}</p>
                            <p className="text-xs text-slate-400">{r.reasons.join(" · ")}</p>
                          </li>
                        ))}
                      </ul>
                    )
                  }
                </AsyncBoundary>
              </Card>
            </div>
          </div>
        </div>
      )}
    </AsyncBoundary>
  );
}
