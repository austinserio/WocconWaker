import { useState } from "react";
import { api, CanonicalRule } from "../api";
import { Taxonomy } from "../taxonomy";

export function RuleEditPanel({
  rule,
  taxonomy,
  onClose,
  onSaved,
}: {
  rule: CanonicalRule;
  taxonomy: Taxonomy;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [domain, setDomain] = useState(rule.grammar_domain ?? "other");
  const [pos, setPos] = useState(rule.pos_tag ?? "multi");
  const [construction, setConstruction] = useState(rule.construction_type ?? "na");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api(`/rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          grammar_domain: domain,
          pos_tag: pos,
          construction_type: construction,
        }),
      });
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel-card p-5 mt-2 border-violet-500/30 animate-slide-up">
      <p className="text-xs text-render-muted mb-3 line-clamp-2">{rule.content}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Grammar area</span>
          <select
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className="input-field mt-1 text-xs"
          >
            {taxonomy.grammar_domains.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Part of speech</span>
          <select value={pos} onChange={(e) => setPos(e.target.value)} className="input-field mt-1 text-xs">
            {taxonomy.pos_tags.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Construction</span>
          <select
            value={construction}
            onChange={(e) => setConstruction(e.target.value)}
            className="input-field mt-1 text-xs"
          >
            {taxonomy.construction_types.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex gap-2 mt-4">
        <button type="button" onClick={save} disabled={saving} className="btn-primary text-xs py-1.5">
          {saving ? "Saving…" : "Save classification"}
        </button>
        <button type="button" onClick={onClose} className="btn-ghost text-xs">
          Cancel
        </button>
      </div>
    </div>
  );
}
