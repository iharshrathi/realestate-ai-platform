import { Link } from "react-router-dom";
import { CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { AsyncBoundary, Badge, Card, EmptyState, KpiCard } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { formatPercent, humanize } from "../utils/format";

const BAND_COLORS = { hot: "#e11d48", warm: "#f59e0b", cold: "#0ea5e9" };
const SEVERITY_STYLES = {
  positive: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  info: "border-slate-200 bg-slate-50 text-slate-700",
};

export default function Dashboard() {
  const { isManager } = useAuth();
  const overview = useAsync(() => api.overview(), []);
  const monthly = useAsync(() => api.monthly(12), []);
  const hot = useAsync(() => api.leads({ band: "hot", sort_by: "latest_probability", order: "desc", page_size: 5 }), []);
  const warm = useAsync(() => api.leads({ band: "warm", page_size: 1 }), []);
  const cold = useAsync(() => api.leads({ band: "cold", page_size: 1 }), []);
  const insights = useAsync(() => (isManager ? api.insights() : Promise.resolve(null)), [isManager]);

  const bandData = [
    { name: "Hot", key: "hot", value: hot.data?.total ?? 0 },
    { name: "Warm", key: "warm", value: warm.data?.total ?? 0 },
    { name: "Cold", key: "cold", value: cold.data?.total ?? 0 },
  ].filter((d) => d.value > 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>

      <AsyncBoundary state={overview}>
        {(o) => (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KpiCard label="Total leads" value={o.total_leads} hint={`${o.new_leads} new`} />
            <KpiCard label="Hot leads" value={o.hot_leads} tone="rose" hint="Probability ≥ hot threshold" />
            <KpiCard label="Converted" value={o.converted_customers} tone="emerald" hint={`${formatPercent(o.conversion_rate, 1)} conversion`} />
            <KpiCard
              label="Pending follow-ups"
              value={o.pending_follow_ups}
              tone={o.overdue_follow_ups ? "amber" : "slate"}
              hint={`${o.overdue_follow_ups} overdue`}
            />
          </div>
        )}
      </AsyncBoundary>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Leads vs. conversions (monthly)" className="lg:col-span-2">
          <AsyncBoundary state={monthly}>
            {(rows) => (
              <div className="h-64">
                <ResponsiveContainer>
                  <LineChart data={rows}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="leads" name="Leads" stroke="#4f46e5" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="converted" name="Converted" stroke="#10b981" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </AsyncBoundary>
        </Card>

        <Card title="Lead quality">
          {bandData.length === 0 ? (
            <EmptyState title="No scored leads yet" hint="Score leads from the lead page." />
          ) : (
            <div className="h-64">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={bandData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                    {bandData.map((d) => (
                      <Cell key={d.key} fill={BAND_COLORS[d.key]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Top hot leads" action={<Link to="/leads?band=hot" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>}>
          <AsyncBoundary state={hot}>
            {(page) =>
              page.items.length === 0 ? (
                <EmptyState title="No hot leads right now" />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {page.items.map((lead) => (
                    <li key={lead.id}>
                      <Link to={`/leads/${lead.id}`} className="flex items-center justify-between py-2.5 hover:bg-slate-50">
                        <div>
                          <p className="text-sm font-medium">{lead.full_name}</p>
                          <p className="text-xs text-slate-500">{humanize(lead.source)} · {humanize(lead.status)}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-rose-600">{formatPercent(lead.latest_probability)}</span>
                          <Badge value="hot" />
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )
            }
          </AsyncBoundary>
        </Card>

        {isManager ? (
          <Card title="Sales insights">
            <AsyncBoundary state={insights}>
              {(data) =>
                data && (
                  <div className="space-y-3">
                    {data.narrative && <p className="rounded-lg bg-brand-50 p-3 text-sm text-brand-700">{data.narrative}</p>}
                    {data.insights.length === 0 && <EmptyState title="Not enough data for insights yet" />}
                    {data.insights.map((insight) => (
                      <div key={insight.key} className={`rounded-lg border p-3 text-sm ${SEVERITY_STYLES[insight.severity]}`}>
                        <p className="font-medium">{insight.title}</p>
                        <p className="mt-0.5 text-xs opacity-90">{insight.detail}</p>
                      </div>
                    ))}
                  </div>
                )
              }
            </AsyncBoundary>
          </Card>
        ) : (
          <Card title="Your day">
            <p className="text-sm text-slate-600">
              Start with the hot leads on the left, then review AI-drafted <Link to="/follow-ups" className="font-medium text-brand-600 hover:underline">follow-ups</Link> waiting for your approval.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
