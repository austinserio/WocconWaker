import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  LexiconEntry,
  LexiconListResponse,
  PendingCatawba,
  PendingCatawbaListResponse,
  PendingCatawbaStats,
} from "../api";
import { LexiconEntryEditor } from "../components/LexiconEditPanel";
import { LexiconEntryCard } from "../components/LexiconEntryCard";
import { SourceCitation } from "../components/SourceCitation";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { LexiconTaxonomy } from "../lexiconTaxonomy";
import { useAuth } from "../context/AuthContext";

type ViewMode = "base" | "all" | "units";
type DictLanguage = "woccon" | "catawba";

interface LexiconGroup {
  teaching_unit: string;
  label: string;
  count: number;
  entries: LexiconEntry[];
}

interface LexiconStats {
  total: number;
  base_count?: number;
  variant_count?: number;
  unmatched_pending?: number;
  by_teaching_unit: Record<string, number>;
}

export default function Dictionary() {
  const { canWrite } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialView = (searchParams.get("view") as ViewMode) || "base";
  const initialLang = (searchParams.get("lang") as DictLanguage) || "woccon";
  const initialDoc = searchParams.get("doc") || "";

  const [taxonomy, setTaxonomy] = useState<LexiconTaxonomy | null>(null);
  const [groups, setGroups] = useState<LexiconGroup[]>([]);
  const [baseItems, setBaseItems] = useState<LexiconEntry[]>([]);
  const [allItems, setAllItems] = useState<LexiconEntry[]>([]);
  const [stats, setStats] = useState<LexiconStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>(initialView);
  const [dictLanguage, setDictLanguage] = useState<DictLanguage>(initialLang);
  const [activeUnit, setActiveUnit] = useState<string | null>(null);
  const [wordClassFilter, setWordClassFilter] = useState<string | null>(null);
  const [bandFilter, setBandFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reclassifying, setReclassifying] = useState(false);
  const [allPage, setAllPage] = useState(1);
  const [allTotal, setAllTotal] = useState(0);
  const [allSort, setAllSort] = useState<"woccon" | "english">("woccon");
  const pageSize = 100;

  const [catawbaItems, setCatawbaItems] = useState<PendingCatawba[]>([]);
  const [catawbaTotal, setCatawbaTotal] = useState(0);
  const [catawbaPage, setCatawbaPage] = useState(1);
  const [catawbaSort, setCatawbaSort] = useState<"catawba" | "english">("catawba");
  const [catawbaStats, setCatawbaStats] = useState<PendingCatawbaStats | null>(null);
  const [catawbaDocFilter, setCatawbaDocFilter] = useState(initialDoc);

  useEffect(() => {
    api<LexiconTaxonomy>("/lexicon/taxonomy").then(setTaxonomy);
    api<PendingCatawbaStats>("/pending/catawba/stats").then(setCatawbaStats);
  }, []);

  useEffect(() => {
    if (initialDoc) {
      setDictLanguage("catawba");
    }
  }, [initialDoc]);

  const loadWoccon = useCallback(() => {
    const params = new URLSearchParams();
    if (wordClassFilter) params.set("word_class", wordClassFilter);
    if (bandFilter) params.set("lesson_band", bandFilter);
    if (search.trim()) params.set("q", search.trim());

    const requests: Promise<unknown>[] = [api<LexiconStats>("/lexicon/stats")];

    if (viewMode === "base") {
      const baseParams = new URLSearchParams(params);
      baseParams.set("page_size", "500");
      baseParams.set("sort", "order");
      requests.push(api<LexiconListResponse>(`/lexicon/base?${baseParams}`));
    } else if (viewMode === "all") {
      const allParams = new URLSearchParams(params);
      allParams.set("page", String(allPage));
      allParams.set("page_size", String(pageSize));
      allParams.set("sort", allSort);
      allParams.set("dedupe", "true");
      requests.push(api<LexiconListResponse>(`/lexicon?${allParams}`));
    } else {
      params.set("dedupe", "true");
      requests.push(api<LexiconGroup[]>(`/lexicon/grouped?${params}`));
    }

    return Promise.allSettled(requests).then((results) => {
      const statsResult = results[0];
      if (statsResult.status === "fulfilled") {
        setStats(statsResult.value as LexiconStats);
      }
      const dataResult = results[1];
      if (dataResult.status !== "fulfilled") return;
      if (viewMode === "base") {
        const resp = dataResult.value as LexiconListResponse;
        setBaseItems(resp.items);
      } else if (viewMode === "all") {
        const resp = dataResult.value as LexiconListResponse;
        setAllItems(resp.items);
        setAllTotal(resp.total);
      } else {
        const g = dataResult.value as LexiconGroup[];
        setGroups(g);
        setActiveUnit((prev) => prev ?? g[0]?.teaching_unit ?? null);
      }
    });
  }, [viewMode, wordClassFilter, bandFilter, search, allPage, allSort]);

  const loadCatawba = useCallback(() => {
    const params = new URLSearchParams({
      status: "approved",
      page: String(catawbaPage),
      page_size: String(pageSize),
      sort: catawbaSort,
    });
    if (search.trim()) params.set("q", search.trim());
    if (catawbaDocFilter) params.set("document_id", catawbaDocFilter);
    return api<PendingCatawbaListResponse>(`/pending/catawba/dictionary?${params}`).then((resp) => {
      setCatawbaItems(resp.items);
      setCatawbaTotal(resp.total);
    });
  }, [catawbaPage, catawbaSort, search, catawbaDocFilter]);

  const load = useCallback(() => {
    setLoading(true);
    const promise = dictLanguage === "catawba" ? loadCatawba() : loadWoccon();
    promise.finally(() => setLoading(false));
  }, [dictLanguage, loadCatawba, loadWoccon]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const params: Record<string, string> = { lang: dictLanguage };
    if (dictLanguage === "woccon" && viewMode !== "base") {
      params.view = viewMode;
    }
    setSearchParams(params, { replace: true });
  }, [viewMode, dictLanguage, setSearchParams]);

  const activeGroup = useMemo(() => {
    if (!activeUnit) return groups[0];
    return groups.find((g) => g.teaching_unit === activeUnit) ?? groups[0];
  }, [groups, activeUnit]);

  const unitNav = useMemo(() => {
    if (!taxonomy) return [];
    return taxonomy.teaching_units.map((u) => ({
      ...u,
      count: stats?.by_teaching_unit[u.id] ?? 0,
    }));
  }, [taxonomy, stats]);

  const reclassify = async () => {
    if (
      !window.confirm(
        "Re-run automatic teaching tags on every Woccon entry?\n\n" +
          "This updates teaching unit, word class, and lesson band from each word's English gloss and POS. " +
          "It does not change Woccon/English forms or delete entries.\n\n" +
          "Manual tag edits will be overwritten. There is no undo."
      )
    ) {
      return;
    }
    setReclassifying(true);
    try {
      await api("/lexicon/reclassify", { method: "POST" });
      load();
    } finally {
      setReclassifying(false);
    }
  };

  const setMode = (mode: ViewMode) => {
    setViewMode(mode);
    setEditId(null);
    setExpandedId(null);
    if (mode === "all") setAllPage(1);
  };

  const setLanguage = (lang: DictLanguage) => {
    setDictLanguage(lang);
    setEditId(null);
    setExpandedId(null);
    setAllPage(1);
    setCatawbaPage(1);
  };

  const renderEntries = (entries: LexiconEntry[], showExpand: boolean) => (
    <ul>
      {entries.map((entry) => (
        <div key={entry.id}>
          <LexiconEntryCard
            entry={entry}
            taxonomy={taxonomy}
            editing={editId === entry.id}
            onEdit={canWrite ? () => setEditId(editId === entry.id ? null : entry.id) : undefined}
            showExpand={showExpand || entry.is_base_entry === true}
            expanded={expandedId === entry.id}
            onToggleExpand={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
          />
          {canWrite && editId === entry.id && taxonomy && (
            <LexiconEntryEditor
              entry={entry}
              taxonomy={taxonomy}
              onClose={() => setEditId(null)}
              onSaved={load}
            />
          )}
        </div>
      ))}
    </ul>
  );

  const renderCatawbaEntries = () => (
    <ul className="space-y-2">
      {catawbaItems.map((entry) => (
        <li key={entry.id} className="panel-card p-4">
          <p className="text-sm text-render-text">
            <span className="font-semibold text-amber-100">{entry.catawba}</span>
            <span className="text-render-muted"> — {entry.english}</span>
            {entry.pos && (
              <span className="text-render-subtle text-xs ml-1">({entry.pos})</span>
            )}
          </p>
          {entry.woccon_cited && (
            <p className="text-xs text-render-subtle mt-1">
              Woccon cited in source: {entry.woccon_cited}
            </p>
          )}
          <SourceCitation citation={entry.citation} />
        </li>
      ))}
    </ul>
  );

  if (!taxonomy) {
    return (
      <div className="flex items-center gap-2 text-render-muted py-8">
        <Spinner />
        <span className="text-sm">Loading taxonomy…</span>
      </div>
    );
  }

  const wocconSubtitle = stats
    ? `${stats.base_count ?? 0} base words · ${stats.variant_count ?? 0} linked variants · ${stats.total} total`
    : "Teaching-oriented vocabulary";

  const catawbaSubtitle = catawbaStats
    ? `${catawbaStats.total_approved} approved · ${catawbaStats.total_pending} pending · comparative evidence only`
    : "Catawba comparative vocabulary";

  return (
    <div>
      <PageHeader
        title="Dictionary"
        subtitle={dictLanguage === "woccon" ? wocconSubtitle : catawbaSubtitle}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-full border border-white/10 p-0.5">
              <button
                type="button"
                onClick={() => setLanguage("woccon")}
                className={`pill-tab text-xs py-1 px-3 rounded-full ${
                  dictLanguage === "woccon" ? "pill-tab-active" : "pill-tab-inactive"
                }`}
              >
                Woccon
              </button>
              <button
                type="button"
                onClick={() => setLanguage("catawba")}
                className={`pill-tab text-xs py-1 px-3 rounded-full ${
                  dictLanguage === "catawba" ? "pill-tab-active" : "pill-tab-inactive"
                }`}
              >
                Catawba
              </button>
            </div>
            {canWrite && dictLanguage === "woccon" && (
              <button
                type="button"
                onClick={reclassify}
                disabled={reclassifying}
                className="btn-secondary text-xs"
              >
                {reclassifying ? "Reclassifying…" : "Reclassify all"}
              </button>
            )}
          </div>
        }
      />

      {dictLanguage === "catawba" && (
        <div className="panel-card p-4 mb-4 border-amber-500/20 bg-amber-500/5">
          <p className="text-sm text-render-text">
            Approved Catawba entries from staged comparative sources. These support cognate
            reconstruction only — they never enter the Woccon Commit flow.
          </p>
        </div>
      )}

      {dictLanguage === "woccon" && (
        <div className="flex flex-wrap gap-2 mb-4">
          {(
            [
              ["base", "Base vocabulary"],
              ["all", "All entries"],
              ["units", "By teaching unit"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setMode(id)}
              className={`pill-tab text-xs py-1 ${viewMode === id ? "pill-tab-active" : "pill-tab-inactive"}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <input
        type="search"
        placeholder={
          dictLanguage === "catawba"
            ? "Search Catawba, English, or cited Woccon…"
            : "Search Woccon or English…"
        }
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setAllPage(1);
          setCatawbaPage(1);
        }}
        className="input-field mb-4 max-w-md"
      />

      {dictLanguage === "catawba" && (
        <>
          <div className="flex flex-wrap gap-3 mb-4 items-end">
            <label className="text-sm text-render-muted">
              Source
              <select
                className="input-field text-sm ml-2 min-w-[220px]"
                value={catawbaDocFilter}
                onChange={(e) => {
                  setCatawbaDocFilter(e.target.value);
                  setCatawbaPage(1);
                }}
              >
                <option value="">All Catawba sources</option>
                {(catawbaStats?.sources ?? []).map((s) => (
                  <option key={s.document_id} value={s.document_id}>
                    {s.title} ({s.approved_count} approved)
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-xs text-render-subtle">Sort:</span>
              <button
                type="button"
                onClick={() => setCatawbaSort("catawba")}
                className={`pill-tab text-xs py-1 ${
                  catawbaSort === "catawba" ? "pill-tab-active" : "pill-tab-inactive"
                }`}
              >
                Catawba
              </button>
              <button
                type="button"
                onClick={() => setCatawbaSort("english")}
                className={`pill-tab text-xs py-1 ${
                  catawbaSort === "english" ? "pill-tab-active" : "pill-tab-inactive"
                }`}
              >
                English
              </button>
            </div>
          </div>
        </>
      )}

      {dictLanguage === "woccon" && viewMode !== "base" && (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            <span className="text-xs text-render-subtle self-center mr-1">Word class:</span>
            <button
              type="button"
              onClick={() => setWordClassFilter(null)}
              className={`pill-tab text-xs py-1 ${!wordClassFilter ? "pill-tab-active" : "pill-tab-inactive"}`}
            >
              All
            </button>
            {taxonomy.word_classes.map((w) => (
              <button
                key={w.id}
                type="button"
                onClick={() => setWordClassFilter(wordClassFilter === w.id ? null : w.id)}
                className={`pill-tab text-xs py-1 ${
                  wordClassFilter === w.id ? "pill-tab-active" : "pill-tab-inactive"
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-2 mb-6">
            <span className="text-xs text-render-subtle self-center mr-1">Lesson band:</span>
            <button
              type="button"
              onClick={() => setBandFilter(null)}
              className={`pill-tab text-xs py-1 ${!bandFilter ? "pill-tab-active" : "pill-tab-inactive"}`}
            >
              All
            </button>
            {taxonomy.lesson_bands.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setBandFilter(bandFilter === b.id ? null : b.id)}
                className={`pill-tab text-xs py-1 ${
                  bandFilter === b.id ? "pill-tab-active" : "pill-tab-inactive"
                }`}
              >
                {b.label}
              </button>
            ))}
          </div>
        </>
      )}

      {dictLanguage === "woccon" && viewMode === "all" && (
        <div className="flex flex-wrap gap-2 mb-4 items-center">
          <span className="text-xs text-render-subtle">Sort:</span>
          <button
            type="button"
            onClick={() => setAllSort("woccon")}
            className={`pill-tab text-xs py-1 ${allSort === "woccon" ? "pill-tab-active" : "pill-tab-inactive"}`}
          >
            Woccon
          </button>
          <button
            type="button"
            onClick={() => setAllSort("english")}
            className={`pill-tab text-xs py-1 ${allSort === "english" ? "pill-tab-active" : "pill-tab-inactive"}`}
          >
            English
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-render-muted py-8">
          <Spinner />
          <span className="text-sm">Loading…</span>
        </div>
      ) : dictLanguage === "catawba" ? (
        catawbaItems.length === 0 ? (
          <EmptyState message="No approved Catawba entries match these filters." />
        ) : (
          <>
            <p className="text-xs text-render-subtle mb-4">
              Showing {(catawbaPage - 1) * pageSize + 1}–
              {Math.min(catawbaPage * pageSize, catawbaTotal)} of {catawbaTotal}
            </p>
            {renderCatawbaEntries()}
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                disabled={catawbaPage <= 1}
                onClick={() => setCatawbaPage((p) => p - 1)}
                className="btn-secondary text-xs"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={catawbaPage * pageSize >= catawbaTotal}
                onClick={() => setCatawbaPage((p) => p + 1)}
                className="btn-secondary text-xs"
              >
                Next
              </button>
            </div>
          </>
        )
      ) : viewMode === "base" ? (
        baseItems.length === 0 ? (
          <EmptyState message="No base vocabulary imported yet. Sync from Library." />
        ) : (
          <>
            <p className="text-xs text-render-subtle mb-4">
              Definitive word list — expand a row to see linked attestations from other sources.
            </p>
            {renderEntries(baseItems, true)}
          </>
        )
      ) : viewMode === "all" ? (
        allItems.length === 0 ? (
          <EmptyState message="No entries match these filters." />
        ) : (
          <>
            <p className="text-xs text-render-subtle mb-4">
              Showing {(allPage - 1) * pageSize + 1}–{Math.min(allPage * pageSize, allTotal)} of{" "}
              {allTotal}
            </p>
            {renderEntries(allItems, false)}
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                disabled={allPage <= 1}
                onClick={() => setAllPage((p) => p - 1)}
                className="btn-secondary text-xs"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={allPage * pageSize >= allTotal}
                onClick={() => setAllPage((p) => p + 1)}
                className="btn-secondary text-xs"
              >
                Next
              </button>
            </div>
          </>
        )
      ) : !activeGroup || activeGroup.entries.length === 0 ? (
        <EmptyState message="No entries match these filters." />
      ) : (
        <div className="flex gap-6">
          <aside className="w-56 shrink-0 space-y-1">
            <p className="text-[10px] uppercase tracking-wider text-render-subtle px-3 mb-2">
              Teaching unit
            </p>
            {unitNav.map((u) => (
              <button
                key={u.id}
                type="button"
                onClick={() => setActiveUnit(u.id)}
                className={`w-full text-left rounded-full px-3 py-2 text-sm transition-all duration-200 flex justify-between gap-2 ${
                  activeUnit === u.id
                    ? "bg-white/10 text-white"
                    : "text-render-muted hover:bg-white/5 hover:text-render-text"
                }`}
              >
                <span className="truncate">{u.label}</span>
                <span className="text-xs text-render-subtle shrink-0">{u.count}</span>
              </button>
            ))}
          </aside>
          <div className="flex-1 min-w-0">
            <div className="mb-4">
              <h3 className="text-lg font-medium text-render-text">{activeGroup.label}</h3>
              <p className="text-xs text-render-muted mt-1">
                {taxonomy.teaching_units.find((u) => u.id === activeGroup.teaching_unit)?.description}
              </p>
              <p className="text-xs text-render-subtle mt-1">
                {activeGroup.count} {activeGroup.count === 1 ? "word" : "words"} in this unit
              </p>
            </div>
            {renderEntries(activeGroup.entries, false)}
          </div>
        </div>
      )}
    </div>
  );
}
