import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { AsyncBoundary, Card, EmptyState, KpiCard } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { formatInr, formatPercent, humanize } from "../utils/format";

function ModelCard({ info }) {
  if (!info.available) return <EmptyState title="No model trained" hint="Run `make train` on the backend." />;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3 text-center">
        <div><p className="text-2xl font-semibold">{info.roc_auc?.toFixed(2)}</p><p className="text-xs text-slate-500">ROC-AUC</p></div>
        <div><p className="text-2xl font-semibold">{info.pr_auc?.toFixed(2)}</p><p className="text-xs text-slate-500">PR-AUC</p></div>
        <div><p className="text-2xl font-semibold">{info.brier_score?.toFixed(3)}</p><p className="text-xs text-slate-500">Brier score</p></div>
      </div>
      <table className="w-full text-left text-xs">
        <thead className="text-slate-500"><tr><th className="py-1">Threshold</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
        <tbody>
          {info.thresholds.map((t) => (
            <tr key={t.threshold} className="border-t border-slate-100">
              <td className="py-1">{t.threshold}</td>
              <td>{formatPercent(t.precision)}</td>
              <td>{formatPercent(t.recall)}</td>
              <td>{t.f1.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-500">{info.algorithm} · version {info.version} · data: {info.data_source}</p>
      {info.disclaimer && <p className="rounded-lg bg-fuchsia-50 p-2 text-xs text-fuchsia-800">{info.disclaimer}</p>}
    </div>
  );
}

export default function Analytics() {
  const channels = useAsync(() => api.channels(), []);
  const forecast = useAsync(() => api.forecast(), []);
  const model = useAsync(() => api.modelInfo(), []);
  const monthly = useAsync(() => api.monthly(12), []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Analytics</h1>

      <AsyncBoundary state={forecast}>
        {(f) => (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <KpiCard label="Open leads" value={f.open_leads} hint={`${f.scored_open_leads} scored`} />
              <KpiCard label="Expected conversions" value={f.expected_conversions_open_leads.toFixed(1)} tone="emerald" hint="From open leads" />
              <KpiCard label="Next-month leads" value={f.next_month_leads?.toFixed(0) ?? "—"} hint="Linear trend" tone="brand" />
              <KpiCard label="Next-month conversions" value={f.next_month_conversions?.toFixed(1) ?? "—"} hint="Trend × conversion rate" tone="brand" />
            </div>
            <p className="text-xs text-slate-500">{f.method} {f.caveat}</p>
          </div>
        )}
      </AsyncBoundary>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Leads by source (monthly)">
          <AsyncBoundary state={monthly}>
            {(rows) => {
              const sources = [...new Set(rows.flatMap((r) => Object.keys(r.by_source)))];
              const palette = ["#4f46e5", "#10b981", "#f59e0b", "#e11d48", "#0ea5e9"];
              const data = rows.map((r) => ({ month: r.month, ...r.by_source }));
              return (
                <div className="h-64">
                  <ResponsiveContainer>
                    <BarChart data={data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend />
                      {sources.map((s, i) => <Bar key={s} dataKey={s} name={humanize(s)} stackId="a" fill={palette[i % palette.length]} />)}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              );
            }}
          </AsyncBoundary>
        </Card>

        <Card title="Conversion rate by channel">
          <AsyncBoundary state={channels}>
            {(rows) => (
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={rows.map((r) => ({ ...r, name: humanize(r.source), rate: +(r.conversion_rate * 100).toFixed(1) }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis unit="%" tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="rate" name="Conversion rate (%)" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </AsyncBoundary>
        </Card>
      </div>

      <Card title="Channel performance" className="overflow-x-auto">
        <AsyncBoundary state={channels}>
          {(rows) => (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="py-2">Channel</th><th>Leads</th><th>Converted</th><th>Conv. rate</th><th>Avg score</th><th>Spend</th><th>Cost / lead</th><th>Cost / conversion</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.source}>
                    <td className="py-2 font-medium">{humanize(r.source)}</td>
                    <td>{r.leads}</td>
                    <td>{r.converted}</td>
                    <td>{formatPercent(r.conversion_rate, 1)}</td>
                    <td>{formatPercent(r.avg_score)}</td>
                    <td>{r.spend_inr ? formatInr(r.spend_inr) : "—"}</td>
                    <td>{r.cost_per_lead != null ? formatInr(r.cost_per_lead) : "—"}</td>
                    <td>{r.cost_per_conversion != null ? formatInr(r.cost_per_conversion) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncBoundary>
      </Card>

      <Card title="Lead-scoring model">
        <AsyncBoundary state={model}>{(info) => <ModelCard info={info} />}</AsyncBoundary>
      </Card>
    </div>
  );
}
