import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, setToken } from "../api";
import { ROLE_LABELS } from "../utils/roles";

export default function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");

  useEffect(() => {
    if (!token) {
      setPreviewError("Missing invitation link.");
      return;
    }
    api<{ email: string; role: string }>(`/auth/invite?token=${encodeURIComponent(token)}`)
      .then((p) => {
        setEmail(p.email);
        setRole(p.role);
      })
      .catch((e) => setPreviewError(e instanceof Error ? e.message : "Invalid invitation"));
  }, [token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api<{ access_token: string }>("/auth/accept-invite", {
        method: "POST",
        body: JSON.stringify({
          token,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          password,
        }),
      });
      setToken(res.access_token);
      navigate("/rules");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account");
    } finally {
      setLoading(false);
    }
  };

  if (previewError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-render-canvas p-6">
        <div className="panel-card p-8 max-w-md w-full text-center">
          <p className="text-red-300 mb-4">{previewError}</p>
          <Link to="/login" className="text-sm text-render-muted hover:text-white">
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-render-canvas p-6">
      <form onSubmit={submit} className="relative w-full max-w-md panel-card p-8 animate-slide-up">
        <h1 className="text-xl font-semibold text-render-text mb-1">Create your account</h1>
        <p className="text-sm text-render-muted mb-6">
          {email} · {ROLE_LABELS[role] || role}
        </p>
        {error && (
          <p className="mb-4 rounded-xl border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        )}
        <label className="block text-xs font-medium text-render-muted mb-1.5 uppercase tracking-wide">
          First name
        </label>
        <input
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
          className="input-field mb-4"
          required
        />
        <label className="block text-xs font-medium text-render-muted mb-1.5 uppercase tracking-wide">
          Last name
        </label>
        <input
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
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
          minLength={8}
          required
        />
        <button type="submit" className="btn-primary w-full" disabled={loading || !email}>
          {loading ? "Creating account…" : "Continue"}
        </button>
      </form>
    </div>
  );
}
