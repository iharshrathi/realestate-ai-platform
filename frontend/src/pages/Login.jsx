import { useState } from "react";
import { Button, ErrorMessage, Field } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-slate-100 p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-brand-700">EstateIQ</h1>
          <p className="text-sm text-slate-500">Sign in to the lead management platform</p>
        </div>
        <ErrorMessage error={error} />
        <Field label="Email">
          <input className="input" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className="input" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        {import.meta.env.DEV && (
          <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
            Development hint — after <code>make seed</code> use <code>manager@example.com</code> or{" "}
            <code>agent1@example.com</code> with the seed password (default <code>ChangeMe123!</code>).
          </p>
        )}
      </form>
    </div>
  );
}
