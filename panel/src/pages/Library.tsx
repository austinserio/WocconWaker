import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken, LexiconEntry, LexiconListResponse, MergedSource, SourceDocument } from "../api";
import { ExtractionFocusPicker, ExtractionFocusValue } from "../components/ExtractionFocusPicker";
import { ExtractionBadges } from "../components/ExtractionBadges";
import { LexiconEntryCard } from "../components/LexiconEntryCard";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { Taxonomy } from "../taxonomy";
import { useAuth } from "../context/AuthContext";

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

function ExtractionMethodBadge({ method }: { method?: string | null }) {
  if (!method || method === "text") return null;
  const label = method === "vision" ? "Vision OCR" : method === "hybrid" ? "Hybrid OCR" : method;
  return (
    <span className="badge border bg-violet-500/15 text-violet-200 border-violet-500/25 text-xs">
      {label}
    </span>
  );
}

function ExtractionProgress({ doc }: { doc: SourceDocument }) {
  if (doc.status !== "processing") return null;
  const pct = doc.progress_pct ?? 0;
  const label = doc.progress_message || "Processing…";
  return (
    <div className="mt-3 space-y-1.5">
      <div className="flex justify-between text-xs text-render-muted">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-black/30 border border-render-border overflow-hidden">
        <div
          className="h-full bg-amber-400/80 transition-all duration-500 ease-out"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
    </div>
  );
}

function VocabBaseCard({
  doc,
  onSaved,
}: {
  doc: SourceDocument;
  onSaved: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [items, setItems] = useState<LexiconEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const { isAdmin } = useAuth();

  useEffect(() => {
    if (!expanded) return;
    setLoading(true);
    const params = new URLSearchParams({ page_size: "500", sort: "order" });
    if (search.trim()) params.set("q", search.trim());
    api<LexiconListResponse>(`/lexicon/base?${params}`)
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  }, [expanded, search]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter(
      (e) => e.woccon.toLowerCase().includes(q) || e.english.toLowerCase().includes(q)
    );
  }, [items, search]);

  const sync = async () => {
    setSyncing(true);
    try {
      await api("/admin/vocab-base/sync", { method: "POST" });
      onSaved();
      if (expanded) {
        const r = await api<LexiconListResponse>("/lexicon/base?page_size=500&sort=order");
        setItems(r.items);
      }
    } finally {
      setSyncing(false);
    }
  };

  return (
    <li className="panel-card p-5 flex flex-col gap-4 border-emerald-500/20 bg-emerald-500/5">
      <div className="flex justify-between items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="font-medium text-render-text truncate">{doc.title}</h3>
            <span className="badge border border-emerald-500/30 text-emerald-200 text-xs">
              Definitive vocabulary
            </span>
          </div>
          <p className="text-xs text-render-muted">
            {doc.counts?.base_entries ?? 0} base words
            {doc.counts?.variants_from_other_sources != null &&
              ` · ${doc.counts.variants_from_other_sources} linked variants`}
            {doc.counts?.unmatched_pending != null &&
              doc.counts.unmatched_pending > 0 &&
              ` · ${doc.counts.unmatched_pending} unmatched pending`}
          </p>
          <p className="text-xs text-render-subtle mt-1">
            Pronunciations from English-Woccon merge automatically on sync.
          </p>
          {doc.progress_message && doc.status === "ready" && (
            <p className="text-xs text-render-subtle mt-1">{doc.progress_message}</p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <StatusPill status={doc.status} />
            <ExtractionMethodBadge method={doc.text_extraction_method} />
          </div>
          <ExtractionBadges extracted={doc.counts?.extracted} />
          <ExtractionProgress doc={doc} />
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          {doc.source_url && (
            <a
              href={doc.source_url}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary text-xs py-1.5 px-3"
            >
              Drive
            </a>
          )}
          <Link to="/dictionary?view=base" className="btn-secondary text-xs py-1.5 px-3">
            View all words
          </Link>
          {isAdmin && (
            <button
              type="button"
              onClick={sync}
              disabled={syncing || doc.status === "processing"}
              className="btn-primary text-xs py-1.5 px-3"
            >
              {syncing ? "Syncing…" : "Sync from Google Doc"}
            </button>
          )}
        </div>
      </div>
      <div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="btn-secondary text-xs py-1.5 px-3"
        >
          {expanded ? "Hide word list" : "Browse word list"}
        </button>
        {expanded && (
          <div className="mt-4">
            <input
              type="search"
              placeholder="Filter words…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input-field text-sm mb-3 max-w-md"
            />
            {loading ? (
              <div className="flex items-center gap-2 text-render-muted py-4">
                <Spinner />
                <span className="text-sm">Loading vocabulary…</span>
              </div>
            ) : (
              <ul className="max-h-[480px] overflow-y-auto">
                {filtered.map((entry) => (
                  <LexiconEntryCard
                    key={entry.id}
                    entry={entry}
                    showExpand
                    expanded={expandedId === entry.id}
                    onToggleExpand={() =>
                      setExpandedId(expandedId === entry.id ? null : entry.id)
                    }
                  />
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function CitationEditor({
  doc,
  onSaved,
}: {
  doc: SourceDocument;
  onSaved: () => void;
}) {
  const { canWrite, isAdmin } = useAuth();
  const [open, setOpen] = useState(false);
  const [shortTitle, setShortTitle] = useState(doc.short_title ?? "");
  const [authors, setAuthors] = useState(doc.authors ?? "[]");
  const [year, setYear] = useState(doc.year ?? "");
  const [pubTitle, setPubTitle] = useState(doc.pub_title ?? "");
  const [containerTitle, setContainerTitle] = useState(doc.container_title ?? "");
  const [publisher, setPublisher] = useState(doc.publisher ?? "");
  const [place, setPlace] = useState(doc.place ?? "");
  const [citationText, setCitationText] = useState(doc.citation_text ?? "");
  const [saving, setSaving] = useState(false);
  const [reextracting, setReextracting] = useState(false);
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [focus, setFocus] = useState<ExtractionFocusValue>({
    extraction_focus: (doc.extraction_focus as ExtractionFocusValue["extraction_focus"]) || "general",
    grammar_lineage: doc.grammar_lineage ?? null,
  });

  useEffect(() => {
    api<Taxonomy>("/rules/taxonomy").then(setTaxonomy);
  }, []);

  useEffect(() => {
    setFocus({
      extraction_focus: (doc.extraction_focus as ExtractionFocusValue["extraction_focus"]) || "general",
      grammar_lineage: doc.grammar_lineage ?? null,
    });
    setShortTitle(doc.short_title ?? "");
    setAuthors(doc.authors ?? "[]");
    setYear(doc.year ?? "");
    setPubTitle(doc.pub_title ?? "");
    setContainerTitle(doc.container_title ?? "");
    setPublisher(doc.publisher ?? "");
    setPlace(doc.place ?? "");
    setCitationText(doc.citation_text ?? "");
  }, [doc]);

  const save = async () => {
    setSaving(true);
    try {
      await api(`/documents/${doc.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          short_title: shortTitle || null,
          authors: authors || null,
          year: year || null,
          pub_title: pubTitle || null,
          container_title: containerTitle || null,
          publisher: publisher || null,
          place: place || null,
          citation_text: citationText || null,
        }),
      });
      onSaved();
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  const reextract = async () => {
    setReextracting(true);
    try {
      await api(`/admin/documents/${doc.id}/reextract`, {
        method: "POST",
        body: JSON.stringify({
          extraction_focus: focus.extraction_focus,
          grammar_lineage: focus.grammar_lineage,
        }),
      });
      onSaved();
    } finally {
      setReextracting(false);
    }
  };

  if (doc.is_seed) {
    return (
      <span className="text-xs text-render-subtle">{doc.short_title ?? "Seed source"}</span>
    );
  }

  if (doc.is_vocab_base) {
    return null;
  }

  if (!canWrite) {
    return null;
  }

  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)} className="btn-secondary text-xs py-1.5 px-3">
        {open ? "Close citation" : "Edit citation"}
      </button>
      {open && (
        <div className="mt-3 space-y-2 p-4 rounded-xl bg-black/20 border border-render-border">
          <input className="input-field text-sm" placeholder="Short title" value={shortTitle} onChange={(e) => setShortTitle(e.target.value)} />
          <input className="input-field text-sm" placeholder='Authors JSON e.g. ["Koontz, Robert L."]' value={authors} onChange={(e) => setAuthors(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <input className="input-field text-sm" placeholder="Year" value={year} onChange={(e) => setYear(e.target.value)} />
            <input className="input-field text-sm" placeholder="Place" value={place} onChange={(e) => setPlace(e.target.value)} />
          </div>
          <input className="input-field text-sm" placeholder="Publication title" value={pubTitle} onChange={(e) => setPubTitle(e.target.value)} />
          <input className="input-field text-sm" placeholder="Container (journal/book)" value={containerTitle} onChange={(e) => setContainerTitle(e.target.value)} />
          <input className="input-field text-sm" placeholder="Publisher" value={publisher} onChange={(e) => setPublisher(e.target.value)} />
          <textarea className="input-field text-sm min-h-[80px]" placeholder="Full citation override (Chicago)" value={citationText} onChange={(e) => setCitationText(e.target.value)} />
          {taxonomy?.extraction_focuses?.length && taxonomy?.grammar_lineages?.length && (
            <div className="pt-2 border-t border-render-border">
              <p className="text-xs font-medium text-render-text mb-2">Re-extract focus</p>
              <ExtractionFocusPicker
                focuses={taxonomy.extraction_focuses}
                lineages={taxonomy.grammar_lineages}
                value={focus}
                onChange={setFocus}
                compact
              />
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={save} disabled={saving} className="btn-primary text-xs">
              {saving ? "Saving…" : "Save citation"}
            </button>
            {isAdmin && (
              <button type="button" onClick={reextract} disabled={reextracting || doc.status === "processing"} className="btn-secondary text-xs">
                {reextracting ? "Starting…" : "Re-extract with focus"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function isNoTextFailure(doc: SourceDocument): boolean {
  return doc.status === "failed" && /no text extracted/i.test(doc.error_message ?? "");
}

function MergedSourceRow({
  source,
  onDeleted,
}: {
  source: MergedSource;
  onDeleted: () => void;
}) {
  const { canWrite } = useAuth();
  const [deleting, setDeleting] = useState(false);

  const remove = async () => {
    if (!window.confirm(`Remove "${source.title}" from this work group?`)) return;
    setDeleting(true);
    try {
      await api(`/documents/${source.id}`, { method: "DELETE" });
      onDeleted();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <li className="rounded-xl border border-render-border bg-black/20 p-3 flex flex-col gap-2">
      <div className="flex justify-between items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-render-text truncate">{source.title}</p>
          <p className="text-xs text-render-muted mt-0.5">
            {source.short_title && source.year
              ? `${source.short_title} (${source.year})`
              : source.short_title || "Alternate scan"}
          </p>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <StatusPill status={source.status} />
            <ExtractionMethodBadge method={source.text_extraction_method} />
          </div>
          <ExtractionBadges extracted={source.counts?.extracted} />
          {source.error_message && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <p className="text-xs text-red-400">{source.error_message}</p>
              {canWrite &&
                source.status === "failed" &&
                /no text extracted/i.test(source.error_message ?? "") && (
                  <button
                    type="button"
                    onClick={remove}
                    disabled={deleting}
                    className="btn-secondary text-xs py-1 px-2.5 text-red-300 border-red-500/30"
                  >
                    {deleting ? "Removing…" : "Remove"}
                  </button>
                )}
            </div>
          )}
        </div>
        {source.source_url && (
          <a
            href={source.source_url}
            target="_blank"
            rel="noreferrer"
            className="btn-secondary text-xs py-1.5 px-3 shrink-0"
          >
            Drive
          </a>
        )}
      </div>
    </li>
  );
}

function RegularDocCard({
  doc,
  onSaved,
  onDeleted,
  pronunciationGuide = false,
}: {
  doc: SourceDocument;
  onSaved: () => void;
  onDeleted: () => void;
  pronunciationGuide?: boolean;
}) {
  const { canWrite } = useAuth();
  const [deleting, setDeleting] = useState(false);
  const [showAlternates, setShowAlternates] = useState(false);
  const alternates = doc.merged_sources ?? [];

  const remove = async () => {
    if (!window.confirm(`Remove "${doc.title}" from the library?`)) return;
    setDeleting(true);
    try {
      await api(`/documents/${doc.id}`, { method: "DELETE" });
      onDeleted();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <li
      className={`panel-card p-5 flex flex-col gap-4 transition-all duration-200 ${
        pronunciationGuide ? "border-violet-500/20 bg-violet-500/5" : ""
      }`}
    >
      <div className="flex justify-between items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="font-medium text-render-text truncate">{doc.title}</h3>
            {doc.work_group_label && (
              <span className="badge border border-sky-500/30 text-sky-200 text-xs">
                Unified work
              </span>
            )}
            {pronunciationGuide && (
              <span className="badge border border-violet-500/30 text-violet-200 text-xs">
                Pronunciation guide
              </span>
            )}
          </div>
          <p className="text-xs text-render-muted mt-1">
            {doc.work_group_label ||
              (doc.short_title && doc.year
                ? `${doc.short_title} (${doc.year})`
                : doc.short_title || "Citation not set")}
          </p>
          {doc.work_group_label && doc.short_title && doc.year && (
            <p className="text-xs text-render-subtle mt-0.5">
              {doc.short_title} ({doc.year})
            </p>
          )}
          {pronunciationGuide && (
            <p className="text-xs text-render-subtle mt-1">
              Community pronunciation sketches — merged onto base vocabulary on sync.
            </p>
          )}
          {doc.counts?.variants_linked != null && doc.counts.variants_linked > 0 && (
            <p className="text-xs text-render-subtle mt-1">
              {doc.counts.variants_linked} variant{doc.counts.variants_linked === 1 ? "" : "s"} linked
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <StatusPill status={doc.status} />
            <ExtractionMethodBadge method={doc.text_extraction_method} />
            <span className="text-xs text-render-subtle">{doc.source_type}</span>
            <span className="text-xs text-render-subtle">
              {new Date(doc.created_at).toLocaleString()}
            </span>
          </div>
          <ExtractionBadges extracted={doc.counts?.extracted} />
          <ExtractionProgress doc={doc} />
          {doc.error_message && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <p className="text-xs text-red-400">{doc.error_message}</p>
              {canWrite && isNoTextFailure(doc) && (
                <button
                  type="button"
                  onClick={remove}
                  disabled={deleting}
                  className="btn-secondary text-xs py-1 px-2.5 text-red-300 border-red-500/30 hover:border-red-500/50"
                >
                  {deleting ? "Removing…" : "Remove"}
                </button>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {doc.source_url && (
            <a
              href={doc.source_url}
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
              const res = await fetch(`/api/documents/${doc.id}/file`, {
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
      </div>
      {alternates.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowAlternates(!showAlternates)}
            className="btn-secondary text-xs py-1.5 px-3"
          >
            {showAlternates
              ? "Hide alternate scans"
              : `Alternate scans (${alternates.length})`}
          </button>
          {showAlternates && (
            <ul className="mt-3 space-y-2">
              {alternates.map((source) => (
                <MergedSourceRow key={source.id} source={source} onDeleted={onDeleted} />
              ))}
            </ul>
          )}
        </div>
      )}
      <CitationEditor doc={doc} onSaved={onSaved} />
    </li>
  );
}

export default function Library() {
  const [docs, setDocs] = useState<SourceDocument[]>([]);

  const load = () => {
    api<SourceDocument[]>("/documents").then(setDocs);
  };

  useEffect(() => {
    load();
  }, []);

  const hasProcessing =
    docs.some((d) => d.status === "processing") ||
    docs.some((d) => d.merged_sources?.some((s) => s.status === "processing"));

  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [hasProcessing]);

  const vocabBase = docs.filter((d) => d.is_vocab_base);
  const pronunciationGuides = docs.filter((d) => d.source_type === "pronunciation_guide" && !d.is_vocab_base);
  const otherDocs = docs.filter((d) => !d.is_vocab_base && d.source_type !== "pronunciation_guide");

  return (
    <div>
      <PageHeader
        title="Source library"
        subtitle="Uploaded and ingested scholarship documents. The definitive vocabulary list is pinned at the top."
      />

      {docs.length === 0 ? (
        <EmptyState message="No documents yet. Upload from the Upload page." />
      ) : (
        <ul className="space-y-3">
          {vocabBase.map((d) => (
            <VocabBaseCard key={d.id} doc={d} onSaved={load} />
          ))}
          {pronunciationGuides.map((d) => (
            <RegularDocCard key={d.id} doc={d} pronunciationGuide onSaved={load} onDeleted={load} />
          ))}
          {otherDocs.map((d) => (
            <RegularDocCard key={d.id} doc={d} onSaved={load} onDeleted={load} />
          ))}
        </ul>
      )}
    </div>
  );
}
