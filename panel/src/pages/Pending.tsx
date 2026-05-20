import { useEffect, useState } from "react";
import { api, PendingLexicon, PendingRule } from "../api";
import { LexiconBadges } from "../components/LexiconBadges";
import { RuleBadges } from "../components/RuleBadges";
import { PageHeader, PillTabs } from "../components/ui";
import { LexiconTaxonomy } from "../lexiconTaxonomy";
import { Taxonomy } from "../taxonomy";

type Tab = "lexicon" | "rules";

const TABS = [
  { id: "rules" as const, label: "Rules" },
  { id: "lexicon" as const, label: "Lexicon" },
];

export default function Pending() {
  const [tab, setTab] = useState<Tab>("rules");
  const [lexicon, setLexicon] = useState<PendingLexicon[]>([]);
  const [lexTaxonomy, setLexTaxonomy] = useState<LexiconTaxonomy | null>(null);
  const [rules, setRules] = useState<PendingRule[]>([]);
  const [dupOnly, setDupOnly] = useState(false);
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);

  useEffect(() => {
    api<Taxonomy>("/rules/taxonomy").then(setTaxonomy);
  }, []);

  const load = () => {
    const q = dupOnly ? "?duplicate_only=true&status=pending" : "?status=pending";
    api<PendingLexicon[]>(`/pending/lexicon${q}`).then(setLexicon);
    if (tab === "lexicon" && !lexTaxonomy) {
      api<LexiconTaxonomy>("/lexicon/taxonomy").then(setLexTaxonomy);
    }
    api<PendingRule[]>(`/pending/rules${q}`).then(setRules);
  };

  useEffect(() => {
    load();
  }, [dupOnly, tab]);

  const setStatus = async (type: Tab, id: string, status: string) => {
    const path = type === "lexicon" ? `/pending/lexicon/${id}` : `/pending/rules/${id}`;
    await api(path, { method: "PATCH", body: JSON.stringify({ status }) });
    load();
  };

  const bulk = async (type: Tab, status: string) => {
    const ids = type === "lexicon" ? lexicon.map((r) => r.id) : rules.map((r) => r.id);
    await api(`/pending/${type}/bulk`, {
      method: "POST",
      body: JSON.stringify({ ids, status }),
    });
    load();
  };

  const tabOptions = TABS.map((t) => ({
    ...t,
    label: `${t.label} (${t.id === "rules" ? rules.length : lexicon.length})`,
  }));

  return (
    <div>
      <PageHeader
        title="Pending review"
        subtitle="Approve or reject extracted lexicon and rules before commit."
      />

      <label className="flex items-center gap-3 mb-6 cursor-pointer group">
        <input
          type="checkbox"
          checked={dupOnly}
          onChange={(e) => setDupOnly(e.target.checked)}
          className="h-4 w-4 rounded border-render-border bg-render-surface accent-white"
        />
        <span className="text-sm text-render-muted group-hover:text-render-text transition-colors">
          Show possible duplicates only
        </span>
      </label>

      <div className="mb-6">
        <PillTabs options={tabOptions} value={tab} onChange={setTab} />
      </div>

      {tab === "rules" && (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            <button type="button" onClick={() => bulk("rules", "approved")} className="btn-primary">
              Approve all
            </button>
            <button type="button" onClick={() => bulk("rules", "rejected")} className="btn-danger">
              Reject all
            </button>
          </div>
          <ul className="space-y-2">
            {rules.map((r) => (
              <li key={r.id} className="panel-card p-4">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className="text-[10px] uppercase tracking-wider text-render-subtle font-medium">
                    {r.category}
                  </span>
                  {r.duplicate_of_id && (
                    <span className="badge-warn">
                      Duplicate {(r.duplicate_score ?? 0).toFixed(2)}
                    </span>
                  )}
                </div>
                <p className="text-sm text-render-text leading-relaxed">{r.content}</p>
                {taxonomy && (
                  <RuleBadges
                    taxonomy={taxonomy}
                    grammar_domain={r.grammar_domain}
                    pos_tag={r.pos_tag}
                    construction_type={r.construction_type}
                  />
                )}
                <div className="flex gap-2 mt-4">
                  <button
                    type="button"
                    onClick={() => setStatus("rules", r.id, "approved")}
                    className="btn-success"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => setStatus("rules", r.id, "rejected")}
                    className="btn-danger"
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {tab === "lexicon" && (
        <>
          <div className="flex gap-2 mb-4">
            <button type="button" onClick={() => bulk("lexicon", "approved")} className="btn-primary">
              Approve all
            </button>
          </div>
          <ul className="space-y-2">
            {lexicon.map((r) => (
              <li key={r.id} className="panel-card p-4">
                <p className="text-sm text-render-text">
                  <span className="font-semibold text-white">{r.woccon}</span>
                  <span className="text-render-muted"> — {r.english}</span>
                  {r.pos && (
                    <span className="text-render-subtle text-xs ml-1">({r.pos})</span>
                  )}
                </p>
                {lexTaxonomy && (
                  <LexiconBadges
                    taxonomy={lexTaxonomy}
                    teaching_unit={r.teaching_unit}
                    word_class={r.word_class}
                    lesson_band={r.lesson_band}
                  />
                )}
                {r.duplicate_of_id && (
                  <span className="badge-warn mt-2 inline-flex">Possible duplicate</span>
                )}
                <div className="flex gap-2 mt-4">
                  <button
                    type="button"
                    onClick={() => setStatus("lexicon", r.id, "approved")}
                    className="btn-success"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => setStatus("lexicon", r.id, "rejected")}
                    className="btn-danger"
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
