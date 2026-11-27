import { useState } from "react";
import { api } from "../api/client";
import { toRupees } from "../utils/format";
import { Button, ErrorMessage, Field, LEAD_SOURCES, PROPERTY_TYPES } from "./ui";

const INITIAL = {
  full_name: "", email: "", phone: "", source: "website", message: "",
  location: "", property_type: "", bedrooms: "", budget_max: "", budget_unit: "lakh",
};

/** Create-lead form. Requirement fields are optional; the free-text message is analysed by the AI later. */
export default function LeadForm({ onCreated, onCancel }) {
  const [form, setForm] = useState(INITIAL);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const budgetMax = toRupees(form.budget_max, form.budget_unit);
    const requirement = {
      preferred_location: form.location.trim() || null,
      property_type: form.property_type || null,
      bedrooms: form.bedrooms === "" ? null : Number(form.bedrooms),
      budget_max: budgetMax,
    };
    const hasRequirement = Object.values(requirement).some((v) => v !== null);

    try {
      const lead = await api.createLead({
        full_name: form.full_name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        source: form.source,
        message: form.message.trim() || null,
        requirement: hasRequirement ? requirement : null,
      });
      onCreated(lead);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <ErrorMessage error={error} />
      <Field label="Full name">
        <input className="input" required value={form.full_name} onChange={set("full_name")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Email">
          <input className="input" type="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Phone">
          <input className="input" value={form.phone} onChange={set("phone")} placeholder="+91…" />
        </Field>
      </div>
      <p className="-mt-2 text-xs text-slate-500">Provide at least an email or a phone number.</p>
      <Field label="Source">
        <select className="input" value={form.source} onChange={set("source")}>
          {LEAD_SOURCES.map((s) => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </select>
      </Field>
      <Field label="Enquiry message (optional)">
        <textarea className="input" rows={3} value={form.message} onChange={set("message")} placeholder="Looking for a 3BHK in Whitefield under 90 lakhs, want to buy within a month" />
      </Field>
      <fieldset className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 p-3">
        <legend className="px-1 text-xs font-medium text-slate-500">Requirement (optional)</legend>
        <Field label="Location">
          <input className="input" value={form.location} onChange={set("location")} />
        </Field>
        <Field label="Property type">
          <select className="input" value={form.property_type} onChange={set("property_type")}>
            <option value="">Any</option>
            {PROPERTY_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="Bedrooms">
          <input className="input" type="number" min="0" max="20" value={form.bedrooms} onChange={set("bedrooms")} />
        </Field>
        <Field label="Max budget">
          <div className="flex gap-2">
            <input className="input" type="number" min="0" step="any" value={form.budget_max} onChange={set("budget_max")} />
            <select className="input w-24" value={form.budget_unit} onChange={set("budget_unit")} aria-label="Budget unit">
              <option value="lakh">Lakh</option>
              <option value="cr">Crore</option>
            </select>
          </div>
        </Field>
      </fieldset>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create lead"}</Button>
      </div>
    </form>
  );
}
