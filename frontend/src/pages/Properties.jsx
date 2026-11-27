import { useState } from "react";
import { api } from "../api/client";
import { AsyncBoundary, Badge, Button, Card, EmptyState, Field, PROPERTY_TYPES, Pagination, SyntheticTag } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { formatInr, formatPercent, humanize, toRupees } from "../utils/format";

function Catalog() {
  const [filters, setFilters] = useState({ location: "", property_type: "", status: "available" });
  const [page, setPage] = useState(1);
  const list = useAsync(() => api.properties({ ...filters, page, page_size: 9 }), [filters.location, filters.property_type, filters.status, page]);
  const set = (key) => (e) => { setFilters((f) => ({ ...f, [key]: e.target.value })); setPage(1); };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <input className="input" placeholder="Location…" value={filters.location} onChange={set("location")} aria-label="Location" />
        <select className="input" value={filters.property_type} onChange={set("property_type")} aria-label="Property type">
          <option value="">All types</option>
          {PROPERTY_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
        </select>
        <select className="input" value={filters.status} onChange={set("status")} aria-label="Status">
          <option value="">Any status</option>
          <option value="available">Available</option>
          <option value="on_hold">On hold</option>
          <option value="sold">Sold</option>
        </select>
      </div>
      <AsyncBoundary state={list}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="No properties found" />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {data.items.map((p) => (
                  <article key={p.id} className="card space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-semibold text-slate-900">{p.title}</h3>
                      {p.is_synthetic && <SyntheticTag />}
                    </div>
                    <p className="text-lg font-semibold text-brand-700">{formatInr(p.price_inr)}</p>
                    <p className="text-xs text-slate-500">
                      {p.location} · {humanize(p.property_type)}
                      {p.bedrooms != null && ` · ${p.bedrooms} BHK`}
                      {p.area_sqft && ` · ${p.area_sqft} sq ft`}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {p.amenities.slice(0, 4).map((a) => (
                        <span key={a} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{a}</span>
                      ))}
                    </div>
                    {p.status !== "available" && <Badge value={p.status === "sold" ? "lost" : "draft"} label={humanize(p.status)} />}
                  </article>
                ))}
              </div>
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
            </>
          )
        }
      </AsyncBoundary>
    </div>
  );
}

function Finder() {
  const [form, setForm] = useState({ location: "", property_type: "", bedrooms: "", budget: "", unit: "lakh", text: "" });
  const [results, setResults] = useState(null);
  const [state, setState] = useState({ loading: false, error: null });
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function search(event) {
    event.preventDefault();
    setState({ loading: true, error: null });
    try {
      setResults(
        await api.searchProperties({
          location: form.location,
          property_type: form.property_type,
          bedrooms: form.bedrooms,
          budget_max: toRupees(form.budget, form.unit) ?? "",
          text: form.text,
          limit: 6,
        }),
      );
      setState({ loading: false, error: null });
    } catch (error) {
      setState({ loading: false, error });
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={search} className="card grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Location"><input className="input" value={form.location} onChange={set("location")} /></Field>
        <Field label="Type">
          <select className="input" value={form.property_type} onChange={set("property_type")}>
            <option value="">Any</option>
            {PROPERTY_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </select>
        </Field>
        <Field label="Bedrooms"><input className="input" type="number" min="0" max="20" value={form.bedrooms} onChange={set("bedrooms")} /></Field>
        <Field label="Max budget">
          <div className="flex gap-2">
            <input className="input" type="number" min="0" step="any" value={form.budget} onChange={set("budget")} />
            <select className="input w-24" value={form.unit} onChange={set("unit")} aria-label="Budget unit">
              <option value="lakh">Lakh</option>
              <option value="cr">Crore</option>
            </select>
          </div>
        </Field>
        <div className="sm:col-span-2 lg:col-span-3">
          <Field label="Describe what they want (optional)">
            <input className="input" value={form.text} onChange={set("text")} placeholder="near a metro, gated community with a gym…" />
          </Field>
        </div>
        <div className="flex items-end"><Button type="submit" className="w-full" disabled={state.loading}>{state.loading ? "Searching…" : "Find matches"}</Button></div>
      </form>
      {state.error && <p className="text-sm text-rose-600">{state.error.message}</p>}
      {results && (results.length === 0 ? (
        <EmptyState title="No matching properties" hint="Try widening the budget or location." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((r) => (
            <article key={r.property.id} className="card space-y-1">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold">{r.property.title}</h3>
                <span className="text-xs font-semibold text-brand-600">{formatPercent(r.match_score)} match</span>
              </div>
              <p className="text-sm font-semibold text-brand-700">{formatInr(r.property.price_inr)}</p>
              <p className="text-xs text-slate-500">{r.property.location}</p>
              <p className="text-xs text-slate-400">{r.reasons.join(" · ")}</p>
            </article>
          ))}
        </div>
      ))}
    </div>
  );
}

export default function Properties() {
  const [tab, setTab] = useState("catalog");
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Properties</h1>
      <div className="flex gap-2">
        {[["catalog", "Catalog"], ["finder", "Match finder"]].map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${tab === value ? "bg-brand-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "catalog" ? <Catalog /> : <Finder />}
    </div>
  );
}
