import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { Badge, Button, Card, ErrorMessage } from "../components/ui";
import { formatInr, formatPercent } from "../utils/format";

const GREETING = {
  role: "assistant",
  content: "Hi! I can help you find a property. Tell me what you're looking for — location, type, bedrooms and budget.",
};
const MAX_HISTORY = 30; // matches the API limit on conversation length

/**
 * Customer-facing chat. The server is stateless: we send the whole conversation plus the profile it
 * collected so far on every turn. A lead is only created when the visitor ticks the consent box.
 */
export default function Chatbot() {
  const [messages, setMessages] = useState([GREETING]);
  const [collected, setCollected] = useState({});
  const [recommendations, setRecommendations] = useState([]);
  const [mode, setMode] = useState(null);
  const [consent, setConsent] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages, busy]);

  async function send(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    const next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      // The greeting is UI-only; the API expects the conversation to start with the visitor.
      const history = next.filter((m) => m !== GREETING).slice(-MAX_HISTORY);
      const reply = await api.chat({ messages: history, collected, consent_to_contact: consent });
      setMessages([...next, { role: "assistant", content: reply.reply }]);
      setCollected(reply.collected);
      setRecommendations(reply.recommendations);
      setMode(reply.mode);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setMessages([GREETING]);
    setCollected({});
    setRecommendations([]);
    setMode(null);
    setError(null);
  }

  const known = [
    collected.preferred_location && `Location: ${collected.preferred_location}`,
    collected.property_type && `Type: ${collected.property_type}`,
    collected.bedrooms != null && `${collected.bedrooms} BHK`,
    collected.budget_max && `Budget up to ${formatInr(collected.budget_max)}`,
  ].filter(Boolean);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">AI property assistant</h1>
        <p className="text-sm text-slate-500">
          Answers come only from the available listings. {mode && <Badge value="synthetic" label={mode === "llm" ? "LLM mode" : "Rules mode"} />}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="flex h-[32rem] flex-col lg:col-span-2">
          <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <p className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${m.role === "user" ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-800"}`}>
                  {m.content}
                </p>
              </div>
            ))}
            {busy && <p className="text-xs text-slate-400">Assistant is typing…</p>}
            <div ref={endRef} />
          </div>
          <ErrorMessage error={error} />
          <form onSubmit={send} className="mt-3 space-y-2 border-t border-slate-100 pt-3">
            <label className="flex items-start gap-2 text-xs text-slate-600">
              <input type="checkbox" className="mt-0.5" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>I agree that the sales team may contact me using the details I share in this chat. (Nothing is saved unless this is ticked.)</span>
            </label>
            <div className="flex gap-2">
              <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. 3BHK in Whitefield under 90 lakhs" maxLength={1500} aria-label="Message" />
              <Button type="submit" disabled={busy || !input.trim()}>Send</Button>
              <Button type="button" variant="secondary" onClick={reset}>New chat</Button>
            </div>
          </form>
        </Card>

        <div className="space-y-6">
          <Card title="What I understood">
            {known.length === 0 ? (
              <p className="text-sm text-slate-500">Nothing yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-slate-700">{known.map((k) => <li key={k}>{k}</li>)}</ul>
            )}
            {collected.lead_saved && <p className="mt-3 rounded-lg bg-emerald-50 p-2 text-xs text-emerald-700">Contact details saved — the team will reach out.</p>}
          </Card>
          <Card title="Matching properties">
            {recommendations.length === 0 ? (
              <p className="text-sm text-slate-500">Recommendations appear as the chat progresses.</p>
            ) : (
              <ul className="space-y-3">
                {recommendations.map((r) => (
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
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
