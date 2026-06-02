import { useState } from "react";
import { CitationOut, getToken } from "../api";

function StatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  const styles: Record<string, string> = {
    verified: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
    inferred: "bg-amber-500/15 text-amber-200 border-amber-500/25",
    missing: "bg-red-500/15 text-red-300 border-red-500/25",
    manual: "bg-blue-500/15 text-blue-200 border-blue-500/25",
  };
  return (
    <span
      className={`badge border text-[10px] uppercase tracking-wider ${styles[status] ?? "bg-white/5 text-render-muted border-render-border"}`}
    >
      {status}
    </span>
  );
}

export function SourceCitation({ citation }: { citation?: CitationOut | null }) {
  const [open, setOpen] = useState(false);
  if (!citation?.short && !citation?.full) return null;

  const openFile = async () => {
    if (!citation.file_url) {
      if (citation.source_url) window.open(citation.source_url, "_blank");
      return;
    }
    const token = getToken();
    let url = citation.file_url;
    if (citation.page != null) url += `#page=${citation.page}`;
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.redirected) {
      window.open(res.url, "_blank");
      return;
    }
    const blob = await res.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  };

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs text-render-muted hover:text-white transition-colors flex items-center gap-1"
      >
        <span>{citation.short}</span>
        <span className="text-render-subtle">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-2 pl-3 border-l border-render-border space-y-2 animate-slide-up">
          <p className="text-xs text-render-text leading-relaxed italic">{citation.full}</p>
          {citation.excerpt && (
            <pre className="text-[11px] text-render-subtle bg-black/20 rounded-lg p-2 whitespace-pre-wrap font-mono">
              {citation.excerpt}
            </pre>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={citation.provenance_status} />
            {citation.page != null && (
              <span className="text-[10px] text-render-subtle">
                p. {citation.page}
                {citation.page_end != null && citation.page_end !== citation.page
                  ? `–${citation.page_end}`
                  : ""}
              </span>
            )}
            {citation.file_url && (
              <button type="button" onClick={openFile} className="text-[10px] text-render-muted hover:text-white">
                Open document
              </button>
            )}
            {citation.source_url && (
              <a
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-[10px] text-render-muted hover:text-white"
              >
                External link
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
