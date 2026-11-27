import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import LeadForm from "../components/LeadForm";
import { AsyncBoundary, Badge, Button, Card, EmptyState, LEAD_SOURCES, LEAD_STATUSES, Modal, Pagination, SyntheticTag } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { formatDate, formatPercent, humanize } from "../utils/format";

const PAGE_SIZE = 15;
const SORTS = [
  { value: "created_at", label: "Newest" },
  { value: "latest_probability", label: "Score" },
  { value: "full_name", label: "Name" },
  { value: "status", label: "Status" },
];

export default function Leads() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(false);

  // Filters live in the URL so a filtered view can be bookmarked or linked (e.g. from the dashboard).
  const filters = {
    q: searchParams.get("q") || "",
    status: searchParams.get("status") || "",
    source: searchParams.get("source") || "",
    band: searchParams.get("band") || "",
    sort_by: searchParams.get("sort_by") || "created_at",
    order: searchParams.get("order") || "desc",
    page: Number(searchParams.get("page") || 1),
  };
  const update = (changes) => {
    const next = { ...filters, page: 1, ...changes };
    const clean = Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== "" && !(k === "page" && v === 1)));
    setSearchParams(clean, { replace: true });
  };

  const leads = useAsync(
    () => api.leads({ ...filters, page_size: PAGE_SIZE }),
    [filters.q, filters.status, filters.source, filters.band, filters.sort_by, filters.order, filters.page],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Leads</h1>
        <Button onClick={() => setCreating(true)}>+ New lead</Button>
      </div>

      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <input className="input lg:col-span-2" placeholder="Search name, email or phone…" value={filters.q} onChange={(e) => update({ q: e.target.value })} aria-label="Search leads" />
          <select className="input" value={filters.status} onChange={(e) => update({ status: e.target.value })} aria-label="Status">
            <option value="">All statuses</option>
            {LEAD_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
          <select className="input" value={filters.source} onChange={(e) => update({ source: e.target.value })} aria-label="Source">
            <option value="">All sources</option>
            {LEAD_SOURCES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
          <select className="input" value={filters.band} onChange={(e) => update({ band: e.target.value })} aria-label="Score band">
            <option value="">All scores</option>
            <option value="hot">Hot</option>
            <option value="warm">Warm</option>
            <option value="cold">Cold</option>
          </select>
          <div className="flex gap-2">
            <select className="input" value={filters.sort_by} onChange={(e) => update({ sort_by: e.target.value })} aria-label="Sort by">
              {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <Button variant="secondary" onClick={() => update({ order: filters.order === "desc" ? "asc" : "desc", page: filters.page })} aria-label="Toggle sort order" title="Toggle sort order">
              {filters.order === "desc" ? "↓" : "↑"}
            </Button>
          </div>
        </div>
      </Card>

      <Card className="overflow-x-auto p-0">
        <AsyncBoundary state={leads}>
          {(page) =>
            page.items.length === 0 ? (
              <EmptyState title="No leads match these filters" />
            ) : (
              <>
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Lead</th>
                      <th className="px-4 py-3">Source</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Score</th>
                      <th className="px-4 py-3">Owner</th>
                      <th className="px-4 py-3">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {page.items.map((lead) => (
                      <tr key={lead.id} className="cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/leads/${lead.id}`)}>
                        <td className="px-4 py-3">
                          <Link to={`/leads/${lead.id}`} className="font-medium text-slate-900 hover:text-brand-600" onClick={(e) => e.stopPropagation()}>
                            {lead.full_name}
                          </Link>
                          {lead.is_synthetic && <span className="ml-2"><SyntheticTag /></span>}
                          <p className="text-xs text-slate-500">{lead.email || lead.phone}</p>
                        </td>
                        <td className="px-4 py-3 text-slate-600">{humanize(lead.source)}</td>
                        <td className="px-4 py-3"><Badge value={lead.status} /></td>
                        <td className="px-4 py-3">
                          {lead.latest_band ? (
                            <span className="flex items-center gap-2">
                              <Badge value={lead.latest_band} />
                              <span className="text-xs text-slate-500">{formatPercent(lead.latest_probability)}</span>
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">Not scored</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600">{lead.assigned_to?.full_name || "Unassigned"}</td>
                        <td className="px-4 py-3 text-slate-500">{formatDate(lead.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="px-4 pb-4">
                  <Pagination page={page.page} pageSize={page.page_size} total={page.total} onChange={(p) => update({ page: p })} />
                </div>
              </>
            )
          }
        </AsyncBoundary>
      </Card>

      {creating && (
        <Modal title="New lead" onClose={() => setCreating(false)}>
          <LeadForm onCancel={() => setCreating(false)} onCreated={(lead) => navigate(`/leads/${lead.id}`)} />
        </Modal>
      )}
    </div>
  );
}
