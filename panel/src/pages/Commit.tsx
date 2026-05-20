import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, PageHeader, Spinner } from "../components/ui";

export default function Commit() {
  const [preview, setPreview] = useState<{ pending_lexicon: number; pending_rules: number } | null>(
    null
  );
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api<{ pending_lexicon: number; pending_rules: number }>("/admin/commit/preview").then(
      setPreview
    );
  }, [result]);

  const commit = async () => {
    if (!confirm("Commit all approved/modified pending items to canonical JSON and reload RAG?"))
      return;
    setLoading(true);
    try {
      const res = await api<Record<string, unknown>>("/admin/commit", { method: "POST" });
      setResult(res);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-xl">
      <PageHeader
        title="Commit to production"
        subtitle="Writes unified JSON files and reloads the assistant RAG corpus."
      />

      {preview && (
        <Card className="p-6 mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl bg-render-surface border border-render-border p-4">
              <p className="text-xs text-render-muted uppercase tracking-wide">Lexicon</p>
              <p className="text-2xl font-semibold text-white mt-1">
                {preview.pending_lexicon}
              </p>
              <p className="text-xs text-render-subtle mt-1">ready to commit</p>
            </div>
            <div className="rounded-xl bg-render-surface border border-render-border p-4">
              <p className="text-xs text-render-muted uppercase tracking-wide">Rules</p>
              <p className="text-2xl font-semibold text-white mt-1">{preview.pending_rules}</p>
              <p className="text-xs text-render-subtle mt-1">ready to commit</p>
            </div>
          </div>
        </Card>
      )}

      <button type="button" onClick={commit} disabled={loading} className="btn-primary">
        {loading ? (
          <>
            <Spinner />
            Committing…
          </>
        ) : (
          "Commit & reload"
        )}
      </button>

      {result && (
        <pre className="mt-6 panel-card p-4 text-xs text-render-muted overflow-auto max-h-96 font-mono animate-slide-up">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
