import { FormEvent, useEffect, useState } from "react";
import { api, User } from "../api";
import { PageHeader } from "../components/ui";
import { normalizeRole, ROLE_LABELS } from "../utils/roles";

interface Invitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
  invite_url?: string | null;
}

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [emailMode, setEmailMode] = useState("log");
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("worker");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [lastInviteUrl, setLastInviteUrl] = useState<string | null>(null);

  const load = () => {
    api<{ users: User[]; invitations: Invitation[]; email_mode: string; email_delivery_configured: boolean }>(
      "/users"
    ).then((r) => {
      setUsers(r.users);
      setInvitations(r.invitations);
      setEmailMode(r.email_mode);
      setEmailConfigured(r.email_delivery_configured);
    });
  };

  useEffect(() => {
    load();
  }, []);

  const invite = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setLastInviteUrl(null);
    try {
      const res = await api<Invitation>("/users/invite", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), role: inviteRole }),
      });
      setEmail("");
      if (res.invite_url) {
        setLastInviteUrl(res.invite_url);
        setMessage("No email server configured — copy the invite link below and send it to them.");
      } else {
        setMessage("Invitation email sent.");
      }
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed");
    }
  };

  const changeRole = async (userId: string, role: string) => {
    setError("");
    try {
      await api(`/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  };

  const deactivate = async (userId: string) => {
    if (!confirm("Deactivate this user? They will not be able to sign in.")) return;
    try {
      await api(`/users/${userId}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deactivate failed");
    }
  };

  const resend = async (id: string) => {
    try {
      const res = await api<Invitation>(`/users/invitations/${id}/resend`, { method: "POST" });
      if (res.invite_url) {
        setLastInviteUrl(res.invite_url);
        setMessage("No email server configured — copy the invite link below.");
      } else {
        setMessage("Invitation resent.");
      }
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resend failed");
    }
  };

  const revoke = async (id: string) => {
    try {
      await api(`/users/invitations/${id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revoke failed");
    }
  };

  return (
    <div>
      <PageHeader
        title="Team"
        subtitle="Invite new members or change roles for existing users (including Admin)."
      />
      {!emailConfigured && (
        <p className="text-sm text-amber-200/90 mb-4 rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-3">
          Email is in <strong>log mode</strong> ({emailMode}): invites are not sent to inboxes. After inviting,
          copy the signup link shown below (or check the terminal where <code className="text-xs">python app.py</code>{" "}
          is running). For real email, set <code className="text-xs">EMAIL_MODE=smtp</code> and SMTP variables in{" "}
          <code className="text-xs">.env</code>.
        </p>
      )}
      {error && <p className="text-sm text-red-300 mb-4">{error}</p>}
      {message && <p className="text-sm text-emerald-300 mb-4">{message}</p>}
      {lastInviteUrl && (
        <div className="mb-6 panel-card p-4 border border-amber-500/30">
          <p className="text-xs text-render-muted uppercase tracking-wide mb-2">Invite link (share manually)</p>
          <div className="flex gap-2 flex-wrap items-center">
            <input readOnly value={lastInviteUrl} className="input-field text-xs flex-1 min-w-[200px] font-mono" />
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={() => navigator.clipboard.writeText(lastInviteUrl)}
            >
              Copy
            </button>
            <a href={lastInviteUrl} target="_blank" rel="noreferrer" className="btn-ghost text-xs">
              Open
            </a>
          </div>
        </div>
      )}

      <form onSubmit={invite} className="panel-card p-6 mb-8 flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs text-render-muted mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input-field w-full"
            required
          />
        </div>
        <div>
          <label className="block text-xs text-render-muted mb-1">Role</label>
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value)}
            className="input-field"
          >
            <option value="admin">Admin</option>
            <option value="worker">Community language worker</option>
            <option value="member">Community member (read only)</option>
          </select>
        </div>
        <button type="submit" className="btn-primary">
          Send invitation
        </button>
      </form>

      {invitations.length > 0 && (
        <section className="mb-8">
          <h2 className="text-sm font-medium text-render-muted uppercase tracking-wide mb-3">
            Pending invitations
          </h2>
          <div className="panel-card overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-render-border text-left text-xs uppercase text-render-muted">
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Expires</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv) => (
                  <tr key={inv.id} className="border-b border-render-border/50">
                    <td className="px-4 py-3">{inv.email}</td>
                    <td className="px-4 py-3">{ROLE_LABELS[inv.role] || inv.role}</td>
                    <td className="px-4 py-3 text-render-muted">
                      {new Date(inv.expires_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 space-x-2">
                      <button type="button" className="btn-ghost text-xs" onClick={() => resend(inv.id)}>
                        Resend
                      </button>
                      <button type="button" className="btn-ghost text-xs text-red-300" onClick={() => revoke(inv.id)}>
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-medium text-render-muted uppercase tracking-wide mb-3">Users</h2>
        <div className="panel-card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-render-border text-left text-xs uppercase text-render-muted">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-render-border/50">
                  <td className="px-4 py-3">{u.display_name || u.email}</td>
                  <td className="px-4 py-3 text-render-muted">{u.email}</td>
                  <td className="px-4 py-3">
                    <select
                      value={normalizeRole(u.role)}
                      onChange={(e) => changeRole(u.id, e.target.value)}
                      className="input-field text-xs py-1"
                      disabled={u.is_active === false}
                      title={u.is_active === false ? "Reactivate user to change role" : undefined}
                    >
                      <option value="admin">Admin</option>
                      <option value="worker">Community language worker</option>
                      <option value="member">Community member (read only)</option>
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active === false ? (
                      <span className="text-red-300">Inactive</span>
                    ) : (
                      <span className="text-emerald-300">Active</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active !== false && (
                      <button
                        type="button"
                        className="btn-ghost text-xs text-red-300"
                        onClick={() => deactivate(u.id)}
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
