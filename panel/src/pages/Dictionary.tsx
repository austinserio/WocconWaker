import { useCallback, useEffect, useMemo, useState } from "react";
import { api, LexiconEntry } from "../api";
import { LexiconBadges } from "../components/LexiconBadges";
import { LexiconEditPanel } from "../components/LexiconEditPanel";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { LexiconTaxonomy } from "../lexiconTaxonomy";

interface LexiconGroup {
  teaching_unit: string;
  label: string;
  count: number;
  entries: LexiconEntry[];
}

interface LexiconStats {
  total: number;
  by_teaching_unit: Record<string, number>;
}

function LexiconEntryCard({
  entry,
  taxonomy,
  editing,
  onEdit,
}: {
  entry: LexiconEntry;
  taxonomy: LexiconTaxonomy;
  editing: boolean;
  onEdit: () => void;
}) {
  return (
    <li className="panel-card p-4 mb-2">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span className="font-medium text-render-text">{entry.woccon}</span>
        <span className="text-sm text-render-muted">{entry.english}</span>
        {entry.pos && (
          <span className="text-xs text-render-subtle self-center">({entry.pos})</span>
        )}
      </div>
      {entry.pronunciation && (
        <p className="text-xs text-render-subtle mt-1">/{entry.pronunciation}/</p>
      )}
      <LexiconBadges
        taxonomy={taxonomy}
        teaching_unit={entry.teaching_unit}
        word_class={entry.word_class}
        lesson_band={entry.lesson_band}
      />
      <div className="flex gap-3 mt-2">
        {entry.source_url ? (
          <a
            href={entry.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-render-muted hover:text-white transition-colors"
          >
            Source →
          </a>
        ) : entry.source ? (
          <span className="text-xs text-render-subtle">{entry.source}</span>
        ) : null}
        <button type="button" onClick={onEdit} className="text-xs text-render-muted hover:text-white">
          {editing ? "Close" : "Edit tags"}
        </button>
      </div>
    </li>
  );
}

export default function Dictionary() {
  const [taxonomy, setTaxonomy] = useState<LexiconTaxonomy | null>(null);
  const [groups, setGroups] = useState<LexiconGroup[]>([]);
  const [stats, setStats] = useState<LexiconStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeUnit, setActiveUnit] = useState<string | null>(null);
  const [wordClassFilter, setWordClassFilter] = useState<string | null>(null);
  const [bandFilter, setBandFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [reclassifying, setReclassifying] = useState(false);

  useEffect(() => {
    api<LexiconTaxonomy>("/lexicon/taxonomy").then(setTaxonomy);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (wordClassFilter) params.set("word_class", wordClassFilter);
    if (bandFilter) params.set("lesson_band", bandFilter);
    if (search.trim()) params.set("q", search.trim());
    Promise.all([
      api<LexiconGroup[]>(`/lexicon/grouped?${params}`),
      api<LexiconStats>("/lexicon/stats"),
    ])
      .then(([g, s]) => {
        setGroups(g);
        setStats(s);
        setActiveUnit((prev) => prev ?? g[0]?.teaching_unit ?? null);
      })
      .finally(() => setLoading(false));
  }, [wordClassFilter, bandFilter, search]);

  useEffect(() => {
    load();
  }, [load]);

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

  if (!taxonomy) {
    return (
      <div className="flex items-center gap-2 text-render-muted py-8">
        <Spinner />
        <span className="text-sm">Loading taxonomy…</span>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Dictionary"
        subtitle={
          stats
            ? `${stats.total.toLocaleString()} entries grouped by teaching unit for lessons. Edit tags on any word.`
            : "Teaching-oriented vocabulary"
        }
        action={
          <button
            type="button"
            onClick={reclassify}
            disabled={reclassifying}
            className="btn-secondary text-xs"
          >
            {reclassifying ? "Reclassifying…" : "Reclassify all"}
          </button>
        }
      />

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
          <input
            type="search"
            placeholder="Search Woccon or English…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-field mb-4 max-w-md"
          />

          <div className="flex flex-wrap gap-2 mb-4">
            <span className="text-xs text-render-subtle self-center mr-1">Word class:</span>
            <button
              type="button"
              onClick={() => setWordClassFilter(null)}
              className={`pill-tab text-xs py-1 ${!wordClassFilter ? "pill-tab-active" : "pill-tab-inactive"}`}
            >
              All
            </button>
            {taxonomy.word_classes.slice(0, 10).map((w) => (
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

          {loading ? (
            <div className="flex items-center gap-2 text-render-muted py-8">
              <Spinner />
              <span className="text-sm">Loading…</span>
            </div>
          ) : !activeGroup || activeGroup.entries.length === 0 ? (
            <EmptyState message="No entries match these filters." />
          ) : (
            <>
              <div className="mb-4">
                <h3 className="text-lg font-medium text-render-text">{activeGroup.label}</h3>
                <p className="text-xs text-render-muted mt-1">
                  {taxonomy.teaching_units.find((u) => u.id === activeGroup.teaching_unit)?.description}
                </p>
                <p className="text-xs text-render-subtle mt-1">
                  {activeGroup.count} {activeGroup.count === 1 ? "word" : "words"} in this unit
                </p>
              </div>
              <ul>
                {activeGroup.entries.map((entry) => (
                  <div key={entry.id}>
                    <LexiconEntryCard
                      entry={entry}
                      taxonomy={taxonomy}
                      editing={editId === entry.id}
                      onEdit={() => setEditId(editId === entry.id ? null : entry.id)}
                    />
                    {editId === entry.id && (
                      <LexiconEditPanel
                        entry={entry}
                        taxonomy={taxonomy}
                        onClose={() => setEditId(null)}
                        onSaved={load}
                      />
                    )}
                  </div>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
