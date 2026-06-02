import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, setToken, User } from "../api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api<{ access_token: string; user: User }>("/auth/login/json", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.access_token);
      navigate("/rules");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-render-canvas p-6">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-white/[0.02] rounded-full blur-3xl" />
      </div>

      <form
        onSubmit={submit}
        className="relative w-full max-w-md panel-card p-8 animate-slide-up"
      >
        <div className="flex items-center gap-3 mb-8">
          <div className="h-10 w-10 rounded-xl bg-white flex items-center justify-center shadow-glow">
            <span className="text-black font-bold">W</span>
          </div>
          <div>
            <h1 className="text-xl font-semibold text-render-text">Sign in</h1>
            <p className="text-sm text-render-muted">Woccon language control panel</p>
          </div>
        </div>

        {error && (
          <p className="mb-4 rounded-xl border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}

        <label className="block text-xs font-medium text-render-muted mb-1.5 uppercase tracking-wide">
          Email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="input-field mb-4"
          required
        />

        <label className="block text-xs font-medium text-render-muted mb-1.5 uppercase tracking-wide">
          Password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="input-field mb-8"
          required
        />

        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Signing in…" : "Continue"}
        </button>
        <p className="mt-4 text-center">
          <Link to="/forgot-password" className="text-sm text-render-muted hover:text-white">
            Forgot password?
          </Link>
        </p>
      </form>
    </div>
  );
}
