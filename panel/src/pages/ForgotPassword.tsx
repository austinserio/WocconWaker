import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const res = await api<{ detail: string }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setMessage(res.detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-render-canvas p-6">
      <form onSubmit={submit} className="relative w-full max-w-md panel-card p-8">
        <h1 className="text-xl font-semibold text-render-text mb-2">Forgot password</h1>
        <p className="text-sm text-render-muted mb-6">
          Enter your email and we will send a reset link if an account exists.
        </p>
        {message && (
          <p className="mb-4 rounded-xl border border-emerald-900/50 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">
            {message}
          </p>
        )}
        {error && (
          <p className="mb-4 rounded-xl border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="input-field mb-6"
          required
        />
        <button type="submit" className="btn-primary w-full mb-4" disabled={loading}>
          {loading ? "Sending…" : "Send reset link"}
        </button>
        <Link to="/login" className="text-sm text-render-muted hover:text-white">
          Back to sign in
        </Link>
      </form>
    </div>
  );
}
