import { useEffect, useState } from "react";
import { api, getToken, SourceDocument } from "../api";
import { EmptyState, PageHeader } from "../components/ui";

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    ready: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
    processing: "bg-amber-500/15 text-amber-200 border-amber-500/25 animate-pulse-soft",
    failed: "bg-red-500/15 text-red-300 border-red-500/25",
  };
  return (
    <span
      className={`badge border capitalize ${styles[status] ?? "bg-white/5 text-render-muted border-render-border"}`}
    >
      {status}
    </span>
  );
}

export default function Library() {
  const [docs, setDocs] = useState<SourceDocument[]>([]);

  useEffect(() => {
    api<SourceDocument[]>("/documents").then(setDocs);
  }, []);

  return (
    <div>
      <PageHeader
        title="Source library"
        subtitle="Uploaded and ingested scholarship documents."
      />

      {docs.length === 0 ? (
        <EmptyState message="No documents yet. Upload from the Upload page." />
      ) : (
        <ul className="space-y-3">
          {docs.map((d) => (
            <li
              key={d.id}
              className="panel-card p-5 flex justify-between items-start gap-4 transition-all duration-200"
            >
              <div className="min-w-0">
                <h3 className="font-medium text-render-text truncate">{d.title}</h3>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <StatusPill status={d.status} />
                  <span className="text-xs text-render-subtle">{d.source_type}</span>
                  <span className="text-xs text-render-subtle">
                    {new Date(d.created_at).toLocaleString()}
                  </span>
                </div>
                {d.error_message && (
                  <p className="text-xs text-red-400 mt-2">{d.error_message}</p>
                )}
              </div>
              <div className="flex gap-2 shrink-0">
                {d.source_url && (
                  <a
                    href={d.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-secondary text-xs py-1.5 px-3"
                  >
                    Drive
                  </a>
                )}
                <button
                  type="button"
                  className="btn-secondary text-xs py-1.5 px-3"
                  onClick={async () => {
                    const token = getToken();
                    const res = await fetch(`/api/documents/${d.id}/file`, {
                      headers: token ? { Authorization: `Bearer ${token}` } : {},
                    });
                    if (res.redirected) {
                      window.open(res.url, "_blank");
                      return;
                    }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    window.open(url, "_blank");
                  }}
                >
                  File
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
