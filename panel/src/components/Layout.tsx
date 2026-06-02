import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, clearToken, User } from "../api";
import { useEffect, useState } from "react";
import { AuthProvider } from "../context/AuthContext";
import { isAdmin, canWrite, ROLE_LABELS, normalizeRole } from "../utils/roles";

const nav = [
  { to: "/rules", label: "Grammar rules", minAccess: "member" as const },
  { to: "/dictionary", label: "Dictionary", minAccess: "member" as const },
  { to: "/pending", label: "Pending review", minAccess: "worker" as const },
  { to: "/upload", label: "Upload", minAccess: "worker" as const },
  { to: "/library", label: "Library", minAccess: "member" as const },
  { to: "/commit", label: "Commit", minAccess: "admin" as const },
  { to: "/audit", label: "Audit log", minAccess: "admin" as const },
  { to: "/users", label: "Team", minAccess: "admin" as const },
];

function canSeeNav(item: (typeof nav)[0], role: string) {
  if (item.minAccess === "admin") return isAdmin(role);
  if (item.minAccess === "worker") return canWrite(role);
  return true;
}

export default function Layout() {
  const [user, setUser] = useState<User | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api<User>("/auth/me").then(setUser).catch(() => navigate("/login"));
  }, [navigate]);

  const logout = () => {
    clearToken();
    navigate("/login");
  };

  const role = user ? normalizeRole(user.role) : "member";

  return (
    <AuthProvider user={user}>
      <div className="min-h-screen flex bg-render-canvas">
        <aside className="w-60 shrink-0 flex flex-col border-r border-render-border bg-render-surface px-4 py-6">
          <div className="mb-8 px-2">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-lg bg-white flex items-center justify-center shadow-glow">
                <span className="text-black text-xs font-bold">W</span>
              </div>
              <div>
                <h1 className="text-sm font-semibold text-render-text tracking-tight">Woccon</h1>
                <p className="text-[10px] text-render-muted uppercase tracking-wider">
                  Control Panel
                </p>
              </div>
            </div>
          </div>

          <nav className="flex flex-col gap-0.5 flex-1">
            {nav.map((item) => {
              if (!user || !canSeeNav(item, user.role)) return null;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? "nav-link-active" : ""}`
                  }
                >
                  {item.label}
                </NavLink>
              );
            })}
          </nav>

          <div className="mt-6 pt-4 border-t border-render-border px-2">
            <p className="text-xs text-render-text truncate" title={user?.email}>
              {user?.display_name || user?.email}
            </p>
            <p className="text-[10px] text-render-subtle mt-0.5">
              {ROLE_LABELS[role] || role}
            </p>
            <button type="button" onClick={logout} className="btn-ghost mt-3 w-full justify-start">
              Log out
            </button>
          </div>
        </aside>

        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-5xl px-8 py-10 animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </AuthProvider>
  );
}
