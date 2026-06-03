import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, LexiconEntry, LexiconListResponse } from "../api";
import { LexiconEntryEditor } from "../components/LexiconEditPanel";
import { LexiconEntryCard } from "../components/LexiconEntryCard";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { LexiconTaxonomy } from "../lexiconTaxonomy";
import { useAuth } from "../context/AuthContext";

type ViewMode = "base" | "all" | "units";

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

  const [taxonomy, setTaxonomy] = useState<LexiconTaxonomy | null>(null);
  const [groups, setGroups] = useState<LexiconGroup[]>([]);
  const [baseItems, setBaseItems] = useState<LexiconEntry[]>([]);
  const [allItems, setAllItems] = useState<LexiconEntry[]>([]);
  const [stats, setStats] = useState<LexiconStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>(initialView);
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

  useEffect(() => {
    api<LexiconTaxonomy>("/lexicon/taxonomy").then(setTaxonomy);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
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

    Promise.allSettled(requests)
      .then((results) => {
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
      })
      .finally(() => setLoading(false));
  }, [viewMode, wordClassFilter, bandFilter, search, allPage, allSort]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setSearchParams(viewMode === "base" ? {} : { view: viewMode }, { replace: true });
  }, [viewMode, setSearchParams]);

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

  if (!taxonomy) {
    return (
      <div className="flex items-center gap-2 text-render-muted py-8">
        <Spinner />
        <span className="text-sm">Loading taxonomy…</span>
      </div>
    );
  }

  const subtitle = stats
    ? `${stats.base_count ?? 0} base words · ${stats.variant_count ?? 0} linked variants · ${stats.total} total`
    : "Teaching-oriented vocabulary";

  return (
    <div>
      <PageHeader
        title="Dictionary"
        subtitle={subtitle}
        action={
          canWrite ? (
            <button
              type="button"
              onClick={reclassify}
              disabled={reclassifying}
              className="btn-secondary text-xs"
            >
              {reclassifying ? "Reclassifying…" : "Reclassify all"}
            </button>
          ) : undefined
        }
      />

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

      <input
        type="search"
        placeholder="Search Woccon or English…"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setAllPage(1);
        }}
        className="input-field mb-4 max-w-md"
      />

      {viewMode !== "base" && (
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

      {viewMode === "all" && (
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
