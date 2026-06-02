import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, SourceDocument } from "../api";
import { ExtractionFocusPicker, ExtractionFocusValue } from "../components/ExtractionFocusPicker";
import { Card, PageHeader } from "../components/ui";
import { Taxonomy } from "../taxonomy";

const DEFAULT_FOCUS: ExtractionFocusValue = {
  extraction_focus: "general",
  grammar_lineage: null,
};

export default function Upload() {
  const [driveUrl, setDriveUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [focus, setFocus] = useState<ExtractionFocusValue>(DEFAULT_FOCUS);
  const navigate = useNavigate();

  useEffect(() => {
    api<Taxonomy>("/rules/taxonomy").then(setTaxonomy);
  }, []);

  const submitFile = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setError("");
    setMessage("Uploading…");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("extraction_focus", focus.extraction_focus);
    if (focus.grammar_lineage) fd.append("grammar_lineage", focus.grammar_lineage);
    try {
      const doc = await api<SourceDocument>("/documents", { method: "POST", body: fd });
      setMessage(`"${doc.title}" queued — watch Library for extraction progress.`);
      setTimeout(() => navigate("/library"), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setMessage("");
    }
  };

  const submitDrive = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("Fetching from Drive…");
    try {
      const doc = await api<SourceDocument>("/documents/link", {
        method: "POST",
        body: JSON.stringify({
          drive_url: driveUrl,
          extraction_focus: focus.extraction_focus,
          grammar_lineage: focus.grammar_lineage,
        }),
      });
      setMessage(`"${doc.title}" queued — watch Library for extraction progress.`);
      setDriveUrl("");
      setTimeout(() => navigate("/library"), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Drive ingest failed");
      setMessage("");
    }
  };

  const focusPicker =
    taxonomy?.extraction_focuses?.length && taxonomy?.grammar_lineages?.length ? (
      <ExtractionFocusPicker
        focuses={taxonomy.extraction_focuses}
        lineages={taxonomy.grammar_lineages}
        value={focus}
        onChange={setFocus}
      />
    ) : null;

  return (
    <div className="max-w-xl">
      <PageHeader
        title="Upload scholarship"
        subtitle="PDF, plain text, Word (.docx), or a Google Drive link shared with the service account."
      />

      {message && (
        <p className="mb-4 rounded-xl border border-emerald-900/40 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-200 animate-fade-in">
          {message}
        </p>
      )}
      {error && (
        <p className="mb-4 rounded-xl border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-300 animate-fade-in">
          {error}
        </p>
      )}

      {focusPicker && (
        <Card className="p-6 mb-6">
          <h3 className="text-sm font-semibold text-render-text mb-1">AI extraction settings</h3>
          <p className="text-xs text-render-muted mb-4">
            Choose what the analyzer looks for. Grammar mode uses a lineage filter to separate attested
            Woccon from comparative or proto-Siouan material.
          </p>
          {focusPicker}
        </Card>
      )}

      <form onSubmit={submitFile} className="mb-6">
        <Card className="p-6">
          <h3 className="text-sm font-semibold text-render-text mb-1">File upload</h3>
          <p className="text-xs text-render-muted mb-4">Drop a document to extract using the focus above.</p>
          <input
            type="file"
            accept=".pdf,.txt,.docx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mb-4 block w-full text-sm text-render-muted file:mr-4 file:rounded-full file:border-0 file:bg-white file:px-4 file:py-2 file:text-sm file:font-semibold file:text-black hover:file:bg-neutral-100 file:transition-all"
          />
          <button type="submit" disabled={!file} className="btn-primary">
            Upload & extract
          </button>
        </Card>
      </form>

      <form onSubmit={submitDrive}>
        <Card className="p-6">
          <h3 className="text-sm font-semibold text-render-text mb-1">Google Drive link</h3>
          <p className="text-xs text-render-muted mb-4">Paste a share link to a Doc or PDF.</p>
          <input
            type="url"
            placeholder="https://drive.google.com/file/d/... or https://docs.google.com/document/d/..."
            value={driveUrl}
            onChange={(e) => setDriveUrl(e.target.value)}
            className="input-field mb-4"
            required
          />
          <button type="submit" className="btn-primary">
            Ingest from Drive
          </button>
        </Card>
      </form>
    </div>
  );
}
