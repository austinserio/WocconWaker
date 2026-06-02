import { useEffect, useState } from "react";
import { api, PendingLexicon, PendingRule } from "../api";
import { BaseWordPicker } from "../components/BaseWordPicker";
import { LexiconDuplicateCompare, RuleDuplicateCompare } from "../components/DuplicateCompare";
import { LexiconBadges } from "../components/LexiconBadges";
import { PronunciationGuide } from "../components/PronunciationGuide";
import { PendingRuleForm } from "../components/PendingRuleForm";
import { SourceCitation } from "../components/SourceCitation";
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
  const [unmatchedOnly, setUnmatchedOnly] = useState(false);
  const [linkLexiconId, setLinkLexiconId] = useState<string | null>(null);
  const [compareLexiconId, setCompareLexiconId] = useState<string | null>(null);
  const [compareRuleId, setCompareRuleId] = useState<string | null>(null);
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [editLexiconId, setEditLexiconId] = useState<string | null>(null);
  const [editRuleId, setEditRuleId] = useState<string | null>(null);
  const [showAddLexicon, setShowAddLexicon] = useState(false);
  const [showAddRule, setShowAddRule] = useState(false);

  useEffect(() => {
    api<Taxonomy>("/rules/taxonomy").then(setTaxonomy);
    api<LexiconTaxonomy>("/lexicon/taxonomy").then(setLexTaxonomy);
  }, []);

  const load = () => {
    const params = new URLSearchParams({ status: "pending" });
    if (dupOnly) params.set("duplicate_only", "true");
    if (unmatchedOnly) params.set("unmatched_only", "true");
    api<PendingLexicon[]>(`/pending/lexicon?${params}`).then(setLexicon);
    api<PendingRule[]>(`/pending/rules?${params}`).then(setRules);
  };

  useEffect(() => {
    load();
  }, [dupOnly, unmatchedOnly, tab]);

  const setStatus = async (type: Tab, id: string, status: string) => {
    const path = type === "lexicon" ? `/pending/lexicon/${id}` : `/pending/rules/${id}`;
    await api(path, { method: "PATCH", body: JSON.stringify({ status }) });
    setEditLexiconId(null);
    setEditRuleId(null);
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

  const onLexiconSaved = () => {
    setShowAddLexicon(false);
    setEditLexiconId(null);
    load();
  };

  const onRuleSaved = () => {
    setShowAddRule(false);
    setEditRuleId(null);
    load();
  };

  const linkToBase = async (pendingId: string, baseEntryId: string) => {
    await api(`/pending/lexicon/${pendingId}/link-base`, {
      method: "POST",
      body: JSON.stringify({ base_entry_id: baseEntryId }),
    });
    setLinkLexiconId(null);
    load();
  };

  const promoteToBase = async (pendingId: string) => {
    await api(`/pending/lexicon/${pendingId}/promote-base`, { method: "POST" });
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
        subtitle="Add, edit, approve, or reject lexicon and rules before commit."
      />

      <div className="flex flex-wrap gap-6 mb-6">
        <label className="flex items-center gap-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={dupOnly}
            onChange={(e) => {
              setDupOnly(e.target.checked);
              if (e.target.checked) setUnmatchedOnly(false);
            }}
            className="h-4 w-4 rounded border-render-border bg-render-surface accent-white"
          />
          <span className="text-sm text-render-muted group-hover:text-render-text transition-colors">
            Show possible duplicates only
          </span>
        </label>
        <label className="flex items-center gap-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={unmatchedOnly}
            onChange={(e) => {
              setUnmatchedOnly(e.target.checked);
              if (e.target.checked) setDupOnly(false);
            }}
            className="h-4 w-4 rounded border-render-border bg-render-surface accent-white"
          />
          <span className="text-sm text-render-muted group-hover:text-render-text transition-colors">
            Show unmatched to base vocabulary only
          </span>
        </label>
      </div>

      <div className="mb-6">
        <PillTabs options={tabOptions} value={tab} onChange={setTab} />
      </div>

      {tab === "rules" && (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            <button
              type="button"
              onClick={() => {
                setShowAddRule(true);
                setEditRuleId(null);
              }}
              className="btn-secondary text-xs"
            >
              Add rule
            </button>
            <button type="button" onClick={() => bulk("rules", "approved")} className="btn-primary">
              Approve all
            </button>
            <button type="button" onClick={() => bulk("rules", "rejected")} className="btn-danger">
              Reject all
            </button>
          </div>
          {showAddRule && taxonomy && (
            <div className="mb-4">
              <PendingRuleForm taxonomy={taxonomy} onSaved={onRuleSaved} onCancel={() => setShowAddRule(false)} />
            </div>
          )}
          <ul className="space-y-2">
            {rules.map((r) => (
              <li key={r.id} className="panel-card p-4">
                {editRuleId === r.id && taxonomy ? (
                  <PendingRuleForm
                    entry={r}
                    taxonomy={taxonomy}
                    onSaved={onRuleSaved}
                    onCancel={() => setEditRuleId(null)}
                  />
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className="text-[10px] uppercase tracking-wider text-render-subtle font-medium">
                        {r.category}
                      </span>
                      {r.status === "modified" && (
                        <span className="badge border border-amber-500/30 text-amber-200">Modified</span>
                      )}
                      {r.duplicate_of_id && (
                        <span className="badge-warn">
                          Duplicate {(r.duplicate_score ?? 0).toFixed(2)}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-render-text leading-relaxed">{r.content}</p>
                    <SourceCitation citation={r.citation} />
                    {taxonomy && (
                      <RuleBadges
                        taxonomy={taxonomy}
                        grammar_domain={r.grammar_domain}
                        pos_tag={r.pos_tag}
                        construction_type={r.construction_type}
                        grammar_lineage={r.grammar_lineage}
                      />
                    )}
                    {r.duplicate_of_id && (
                      <div className="mt-3">
                        <button
                          type="button"
                          onClick={() =>
                            setCompareRuleId(compareRuleId === r.id ? null : r.id)
                          }
                          className="btn-secondary text-xs"
                        >
                          {compareRuleId === r.id ? "Hide comparison" : "Compare duplicate"}
                        </button>
                      </div>
                    )}
                    {compareRuleId === r.id && (
                      <RuleDuplicateCompare
                        entry={r}
                        duplicateMatch={r.duplicate_match}
                        duplicateScore={r.duplicate_score}
                        taxonomy={taxonomy}
                        onClose={() => setCompareRuleId(null)}
                      />
                    )}
                    <div className="flex gap-2 mt-4">
                      <button
                        type="button"
                        onClick={() => {
                          setEditRuleId(r.id);
                          setShowAddRule(false);
                        }}
                        className="btn-secondary text-xs"
                      >
                        Edit
                      </button>
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
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {tab === "lexicon" && (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            <button
              type="button"
              onClick={() => {
                setShowAddLexicon(true);
                setEditLexiconId(null);
              }}
              className="btn-secondary text-xs"
            >
              Add lexicon entry
            </button>
            <button type="button" onClick={() => bulk("lexicon", "approved")} className="btn-primary">
              Approve all
            </button>
          </div>
          {showAddLexicon && lexTaxonomy && (
            <div className="mb-4">
              <PendingLexiconForm
                taxonomy={lexTaxonomy}
                onSaved={onLexiconSaved}
                onCancel={() => setShowAddLexicon(false)}
              />
            </div>
          )}
          <ul className="space-y-2">
            {lexicon.map((r) => (
              <li key={r.id} className="panel-card p-4">
                {editLexiconId === r.id && lexTaxonomy ? (
                  <PendingLexiconForm
                    entry={r}
                    taxonomy={lexTaxonomy}
                    onSaved={onLexiconSaved}
                    onCancel={() => setEditLexiconId(null)}
                  />
                ) : (
                  <>
                    <p className="text-sm text-render-text">
                      <span className="font-semibold text-white">{r.woccon}</span>
                      <span className="text-render-muted"> — {r.english}</span>
                      {r.pos && (
                        <span className="text-render-subtle text-xs ml-1">({r.pos})</span>
                      )}
                    </p>
                    {r.pronunciation && <PronunciationGuide pronunciation={r.pronunciation} />}
                    {lexTaxonomy && (
                      <LexiconBadges
                        taxonomy={lexTaxonomy}
                        teaching_unit={r.teaching_unit}
                        word_class={r.word_class}
                        lesson_band={r.lesson_band}
                      />
                    )}
                    <SourceCitation citation={r.citation} />
                    {r.status === "modified" && (
                      <span className="badge border border-amber-500/30 text-amber-200 mt-2 inline-flex">
                        Modified
                      </span>
                    )}
                    {r.base_match && (
                      <span className="badge border border-emerald-500/30 text-emerald-200 mt-2 inline-flex text-xs">
                        → matches {r.base_match.woccon} ({r.base_match.english})
                        {r.base_match_score != null
                          ? ` · ${(r.base_match_score * 100).toFixed(0)}%`
                          : ""}
                      </span>
                    )}
                    {r.match_status === "unmatched" && (
                      <span className="badge-warn mt-2 inline-flex">Unmatched to base vocab</span>
                    )}
                    {r.duplicate_of_id && (
                      <span className="badge-warn mt-2 inline-flex">
                        Possible duplicate
                        {r.duplicate_score != null
                          ? ` (${(r.duplicate_score * 100).toFixed(0)}%)`
                          : ""}
                      </span>
                    )}
                    {r.duplicate_of_id && (
                      <div className="mt-3">
                        <button
                          type="button"
                          onClick={() =>
                            setCompareLexiconId(compareLexiconId === r.id ? null : r.id)
                          }
                          className="btn-secondary text-xs"
                        >
                          {compareLexiconId === r.id ? "Hide comparison" : "Compare duplicate"}
                        </button>
                      </div>
                    )}
                    {compareLexiconId === r.id && (
                      <LexiconDuplicateCompare
                        entry={r}
                        duplicateMatch={r.duplicate_match}
                        duplicateScore={r.duplicate_score}
                        taxonomy={lexTaxonomy}
                        onClose={() => setCompareLexiconId(null)}
                      />
                    )}
                    {r.match_status === "unmatched" && (
                      <div className="flex flex-wrap gap-2 mt-3">
                        <button
                          type="button"
                          onClick={() => setLinkLexiconId(linkLexiconId === r.id ? null : r.id)}
                          className="btn-secondary text-xs"
                        >
                          Link to existing word
                        </button>
                        <button
                          type="button"
                          onClick={() => promoteToBase(r.id)}
                          className="btn-primary text-xs"
                        >
                          Add to vocabulary
                        </button>
                      </div>
                    )}
                    {linkLexiconId === r.id && (
                      <BaseWordPicker
                        onSelect={(entry) => linkToBase(r.id, entry.id)}
                        onCancel={() => setLinkLexiconId(null)}
                      />
                    )}
                    <div className="flex gap-2 mt-4">
                      <button
                        type="button"
                        onClick={() => {
                          setEditLexiconId(r.id);
                          setShowAddLexicon(false);
                        }}
                        className="btn-secondary text-xs"
                      >
                        Edit
                      </button>
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
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
