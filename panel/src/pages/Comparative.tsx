import { useCallback, useEffect, useState } from "react";
import {
  api,
  CognateSet,
  CognateSetListResponse,
  CorrespondenceRule,
  CorrespondenceRuleListResponse,
} from "../api";
import { EmptyState, PageHeader, Spinner } from "../components/ui";

type Tab = "cognates" | "rules";

function TierBadge({ tier }: { tier: string }) {
  const styles: Record<string, string> = {
    certain: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
    partial: "bg-amber-500/15 text-amber-200 border-amber-500/25",
    possible: "bg-sky-500/15 text-sky-200 border-sky-500/25",
    ps_only: "bg-violet-500/15 text-violet-200 border-violet-500/25",
  };
  return (
    <span className={`badge border text-xs capitalize ${styles[tier] ?? "bg-white/5 text-render-muted border-render-border"}`}>
      {tier.replace("_", " ")}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    established: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
    tentative: "bg-amber-500/15 text-amber-200 border-amber-500/25",
    singleton: "bg-white/5 text-render-muted border-render-border",
  };
  return (
    <span className={`badge border text-xs capitalize ${styles[status] ?? styles.singleton}`}>
      {status}
    </span>
  );
}

export default function Comparative() {
  const [tab, setTab] = useState<Tab>("cognates");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [cognates, setCognates] = useState<CognateSet[]>([]);
  const [cognateTotal, setCognateTotal] = useState(0);
  const [rules, setRules] = useState<CorrespondenceRule[]>([]);
  const [ruleTotal, setRuleTotal] = useState(0);
  const [tierFilter, setTierFilter] = useState<string>("");
  const [kindFilter, setKindFilter] = useState<string>("sister_wc");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    if (tab === "cognates") {
      const params = new URLSearchParams({ page_size: "100" });
      if (search.trim()) params.set("gloss", search.trim());
      if (tierFilter) params.set("evidence_tier", tierFilter);
      api<CognateSetListResponse>(`/cognate-sets?${params}`)
        .then((resp) => {
          setCognates(resp.items);
          setCognateTotal(resp.total);
        })
        .finally(() => setLoading(false));
    } else {
      const params = new URLSearchParams({ page_size: "100" });
      if (kindFilter) params.set("rule_kind", kindFilter);
      api<CorrespondenceRuleListResponse>(`/correspondence-rules?${params}`)
        .then((resp) => {
          setRules(resp.items);
          setRuleTotal(resp.total);
        })
        .finally(() => setLoading(false));
    }
  }, [tab, search, tierFilter, kindFilter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Comparative data"
        subtitle="Rudes/Carter cognate sets and Woccon–Catawba correspondence rules (read-only; re-import from JSON via admin)."
      />

      <div className="flex flex-wrap gap-2 mb-6">
        <button
          type="button"
          className={`btn-secondary ${tab === "cognates" ? "ring-1 ring-white/20" : ""}`}
          onClick={() => setTab("cognates")}
        >
          Cognate sets ({cognateTotal || "…"})
        </button>
        <button
          type="button"
          className={`btn-secondary ${tab === "rules" ? "ring-1 ring-white/20" : ""}`}
          onClick={() => setTab("rules")}
        >
          Correspondences ({ruleTotal || "…"})
        </button>
      </div>

      {tab === "cognates" ? (
        <div className="flex flex-wrap gap-3 mb-6">
          <input
            type="search"
            placeholder="Filter by gloss…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input max-w-xs"
          />
          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className="input max-w-[10rem]"
          >
            <option value="">All tiers</option>
            <option value="certain">Certain</option>
            <option value="partial">Partial</option>
            <option value="possible">Possible</option>
            <option value="ps_only">PS only</option>
          </select>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3 mb-6">
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="input max-w-[12rem]"
          >
            <option value="">All kinds</option>
            <option value="sister_wc">Sister W↔C</option>
            <option value="diachronic_ps">Diachronic PS</option>
            <option value="orthographic">Orthographic</option>
            <option value="diachronic_psc">Diachronic PSC</option>
          </select>
        </div>
      )}

      {loading ? (
        <Spinner label="Loading comparative data…" />
      ) : tab === "cognates" ? (
        cognates.length === 0 ? (
          <EmptyState title="No cognate sets" message="Run POST /api/admin/import-comparative to load seed JSON." />
        ) : (
          <div className="space-y-3">
            {cognates.map((row) => (
              <article key={row.id} className="card p-4">
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium text-render-text capitalize">{row.gloss}</h3>
                    <TierBadge tier={row.evidence_tier} />
                    <span className="text-xs text-render-muted">
                      App. {row.rudes_appendix} #{row.rudes_item}
                    </span>
                  </div>
                  <div className="mt-2 grid gap-1 text-sm text-render-muted sm:grid-cols-3">
                    <div>
                      <span className="text-render-subtle">Lawson:</span> {row.lawson_form_corrected || row.lawson_form || "—"}
                    </div>
                    <div>
                      <span className="text-render-subtle">Woccon:</span> {row.woccon_reconstituted || "—"}
                    </div>
                    <div>
                      <span className="text-render-subtle">Catawba:</span> {row.catawba_form || "—"}
                    </div>
                  </div>
                </button>
                {expandedId === row.id && (
                  <div className="mt-3 pt-3 border-t border-render-border text-sm space-y-2">
                    {row.citation_short && <p className="text-render-muted">{row.citation_short}</p>}
                    {row.notes && <p className="text-render-subtle">{row.notes}</p>}
                    {row.canonical_lexicon_id && (
                      <p className="text-xs text-emerald-300/80">
                        Linked to dictionary entry {row.canonical_lexicon_id.slice(0, 8)}…
                      </p>
                    )}
                    {row.rule_examples.length > 0 && (
                      <div>
                        <p className="text-render-subtle text-xs uppercase tracking-wide mb-1">Alignments</p>
                        <ul className="text-xs text-render-muted space-y-1">
                          {row.rule_examples.map((ex) => (
                            <li key={ex.id}>
                              Rule <code className="text-render-text">{ex.correspondence_rule_id}</code>
                              {ex.alignment?.length
                                ? `: ${ex.alignment.map((a) => `${a.w_span}↔${a.c_span}`).join(", ")}`
                                : null}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )
      ) : rules.length === 0 ? (
        <EmptyState title="No correspondence rules" message="Run POST /api/admin/import-comparative to load registry JSON." />
      ) : (
        <div className="space-y-2">
          {rules.map((rule) => (
            <article key={rule.id} className="card p-4">
              <div className="flex flex-wrap items-center gap-2">
                <code className="text-sm text-render-text">{rule.id}</code>
                <StatusBadge status={rule.correspondence_status} />
                <span className="badge border text-xs bg-white/5 text-render-muted border-render-border">
                  {rule.rule_kind}
                </span>
                {rule.environment && rule.environment !== "default" && (
                  <span className="text-xs text-render-muted">env: {rule.environment}</span>
                )}
              </div>
              <p className="mt-2 text-sm">
                <span className="text-render-subtle">Mapping:</span>{" "}
                {rule.lhs ?? "?"} → {rule.rhs ?? "?"}
                {rule.direction ? ` (${rule.direction})` : null}
              </p>
              {rule.provenance_text && (
                <p className="mt-1 text-xs text-render-muted line-clamp-2">{rule.provenance_text}</p>
              )}
              {rule.example_cognate_ids.length > 0 && (
                <p className="mt-1 text-xs text-render-subtle">
                  {rule.example_cognate_ids.length} aligned example(s)
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
