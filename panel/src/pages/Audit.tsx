import { useEffect, useState } from "react";
import { api } from "../api";
import { EmptyState, PageHeader } from "../components/ui";

interface AuditEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  user_id?: string;
  created_at: string;
}

export default function Audit() {
  const [rows, setRows] = useState<AuditEntry[]>([]);

  useEffect(() => {
    api<AuditEntry[]>("/admin/audit").then(setRows);
  }, []);

  return (
    <div>
      <PageHeader title="Audit log" subtitle="Recent admin actions on the control panel." />

      {rows.length === 0 ? (
        <EmptyState message="No audit entries yet." />
      ) : (
        <div className="panel-card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-render-border text-left text-xs uppercase tracking-wide text-render-muted">
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Entity</th>
                <th className="px-4 py-3 font-medium">User</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-render-border/50 transition-colors hover:bg-white/[0.03]"
                >
                  <td className="px-4 py-3 whitespace-nowrap text-render-muted">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className="badge bg-white/10 text-render-text border border-render-border">
                      {r.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-render-muted font-mono text-xs">
                    {r.entity_type} / {r.entity_id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3 text-render-subtle font-mono text-xs">
                    {r.user_id?.slice(0, 8) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
