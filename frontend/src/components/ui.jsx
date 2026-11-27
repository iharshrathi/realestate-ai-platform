// Small reusable building blocks used across every page.
import { humanize } from "../utils/format";

const BUTTON_STYLES = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-500/50",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50",
  danger: "bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50",
  success: "bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50",
  ghost: "text-brand-600 hover:bg-brand-50 disabled:opacity-50",
};

export function Button({ variant = "primary", size = "md", className = "", ...props }) {
  const sizes = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed ${sizes} ${BUTTON_STYLES[variant]} ${className}`}
      {...props}
    />
  );
}

const BADGE_COLORS = {
  // lead status
  new: "bg-sky-100 text-sky-700",
  contacted: "bg-indigo-100 text-indigo-700",
  qualified: "bg-violet-100 text-violet-700",
  site_visit: "bg-amber-100 text-amber-700",
  negotiation: "bg-orange-100 text-orange-700",
  converted: "bg-emerald-100 text-emerald-700",
  lost: "bg-slate-200 text-slate-600",
  // score bands
  hot: "bg-rose-100 text-rose-700",
  warm: "bg-amber-100 text-amber-700",
  cold: "bg-sky-100 text-sky-700",
  // priority / follow-up status
  high: "bg-rose-100 text-rose-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
  draft: "bg-amber-100 text-amber-700",
  approved: "bg-sky-100 text-sky-700",
  sent: "bg-emerald-100 text-emerald-700",
  completed: "bg-emerald-100 text-emerald-700",
  rejected: "bg-slate-200 text-slate-600",
  // misc
  synthetic: "bg-fuchsia-100 text-fuchsia-700",
  success: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
};

export function Badge({ value, label, className = "" }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_COLORS[value] || "bg-slate-100 text-slate-600"} ${className}`}>
      {label ?? humanize(value)}
    </span>
  );
}

export function Card({ title, action, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" />
      {label}
    </div>
  );
}

export function ErrorMessage({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">
      <span>{error.message || String(error)}</span>
      {onRetry && (
        <button onClick={onRetry} className="shrink-0 font-medium underline">
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="py-10 text-center">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

/** Wrap async content: spinner while loading, error box on failure, children when ready. */
export function AsyncBoundary({ state, children }) {
  if (state.loading && !state.data) return <Spinner />;
  if (state.error) return <ErrorMessage error={state.error} onRetry={state.reload} />;
  return children(state.data);
}

export function KpiCard({ label, value, hint, tone = "slate" }) {
  const tones = { slate: "text-slate-900", rose: "text-rose-600", emerald: "text-emerald-600", amber: "text-amber-600", brand: "text-brand-600" };
  return (
    <div className="card">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-3xl font-semibold ${tones[tone]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 pt-16" onMouseDown={onClose}>
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <header className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            ✕
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function Pagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(Math.ceil(total / pageSize), 1);
  return (
    <div className="flex items-center justify-between pt-4 text-sm text-slate-500">
      <span>
        {total} result{total === 1 ? "" : "s"}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </Button>
        <span>
          Page {page} of {pages}
        </span>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  );
}

export function SyntheticTag() {
  return <Badge value="synthetic" label="Synthetic" />;
}

export const LEAD_STATUSES = ["new", "contacted", "qualified", "site_visit", "negotiation", "converted", "lost"];
export const LEAD_SOURCES = ["website", "facebook_ads", "newspaper", "direct"];
export const PROPERTY_TYPES = ["apartment", "villa", "plot", "commercial"];
