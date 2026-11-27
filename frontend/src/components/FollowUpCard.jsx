import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatDate, humanize } from "../utils/format";
import { Badge, Button, ErrorMessage } from "./ui";

const AUTHOR_LABEL = { human: "Written by a person", template: "Template draft", llm: "AI-personalised draft" };

/**
 * One follow-up with its human-approval workflow:
 * draft -> (edit) -> approve -> complete (a person confirms it was actually sent), or reject.
 * Nothing is ever sent by the platform itself.
 */
export default function FollowUpCard({ followUp, showLead = true, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState(followUp.message);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function act(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setEditing(false);
      onChanged?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const { status } = followUp;
  const pendingReview = status === "draft";
  const awaitingSend = status === "approved";

  return (
    <article className="card space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        {showLead && (
          <Link to={`/leads/${followUp.lead_id}`} className="font-medium text-slate-900 hover:text-brand-600">
            {followUp.lead_name}
          </Link>
        )}
        <Badge value={status} />
        <Badge value={followUp.priority} label={`${humanize(followUp.priority)} priority`} />
        <span className="text-xs text-slate-500">{humanize(followUp.channel)}</span>
        <span className="ml-auto text-xs text-slate-400">{AUTHOR_LABEL[followUp.generated_by]}</span>
      </header>

      {followUp.rationale && <p className="text-xs text-slate-500">Why: {followUp.rationale}</p>}

      {editing ? (
        <textarea className="input" rows={6} value={message} onChange={(e) => setMessage(e.target.value)} aria-label="Follow-up message" />
      ) : (
        <p className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{followUp.message || "(no message)"}</p>
      )}

      <ErrorMessage error={error} />

      <footer className="flex flex-wrap items-center gap-2">
        {pendingReview && !editing && (
          <>
            <Button variant="success" size="sm" disabled={busy} onClick={() => act(() => api.approveFollowUp(followUp.id))}>Approve</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setEditing(true)}>Edit</Button>
            <Button variant="danger" size="sm" disabled={busy} onClick={() => act(() => api.rejectFollowUp(followUp.id))}>Reject</Button>
          </>
        )}
        {editing && (
          <>
            <Button size="sm" disabled={busy || !message.trim()} onClick={() => act(() => api.editFollowUp(followUp.id, { message }))}>Save changes</Button>
            <Button variant="secondary" size="sm" onClick={() => { setEditing(false); setMessage(followUp.message); }}>Cancel</Button>
          </>
        )}
        {awaitingSend && (
          <>
            <Button size="sm" disabled={busy} onClick={() => act(() => api.completeFollowUp(followUp.id))}>
              {followUp.channel === "call" ? "Mark call done" : "I sent this"}
            </Button>
            <span className="text-xs text-slate-500">Approved — send it from your own channel, then confirm here.</span>
          </>
        )}
        <span className="ml-auto text-xs text-slate-400">
          {followUp.sent_at ? `Sent ${formatDate(followUp.sent_at, true)}` : followUp.due_at ? `Due ${formatDate(followUp.due_at)}` : `Created ${formatDate(followUp.created_at)}`}
        </span>
      </footer>
    </article>
  );
}
