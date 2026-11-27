// Small, pure formatting helpers (unit-tested in format.test.js).

/** Format rupees the way Indian real estate talks: lakh / crore. */
export function formatInr(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(n % 1e5 === 0 ? 0 : 1)} L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function formatPercent(value, digits = 0) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDate(iso, withTime = false) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return withTime
    ? date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
    : date.toLocaleDateString("en-IN", { dateStyle: "medium" });
}

/** "snake_case" -> "Snake case" */
export function humanize(text) {
  if (!text) return "—";
  const spaced = String(text).replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Convert a lakh/crore text field ("85", "1.2") + unit to rupees; "" -> null. */
export function toRupees(amount, unit) {
  if (amount === "" || amount === null || amount === undefined) return null;
  const n = Number(amount);
  if (Number.isNaN(n) || n < 0) return null;
  return Math.round(n * (unit === "cr" ? 1e7 : 1e5));
}
