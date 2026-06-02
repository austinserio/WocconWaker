import { useEffect, useState } from "react";
import { api, CanonicalRule } from "../api";
import { Taxonomy } from "../taxonomy";
import {
  ProvenanceFields,
  provenanceFromRow,
  provenancePayload,
  ProvenanceValues,
} from "./ProvenanceFields";

export function RuleEntryEditor({
  rule,
  taxonomy,
  onClose,
  onSaved,
  onDeleted,
}: {
  rule: CanonicalRule;
  taxonomy: Taxonomy;
  onClose: () => void;
  onSaved: () => void;
  onDeleted?: () => void;
}) {
  const [content, setContent] = useState(rule.content);
  const [domain, setDomain] = useState(rule.grammar_domain ?? "other");
  const [pos, setPos] = useState(rule.pos_tag ?? "multi");
  const [construction, setConstruction] = useState(rule.construction_type ?? "na");
  const [provenance, setProvenance] = useState<ProvenanceValues>(() => provenanceFromRow(rule));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isGrammar = rule.category === "grammar";

  useEffect(() => {
    setContent(rule.content);
    setDomain(rule.grammar_domain ?? "other");
    setPos(rule.pos_tag ?? "multi");
    setConstruction(rule.construction_type ?? "na");
    setProvenance(provenanceFromRow(rule));
  }, [rule]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        content: content.trim(),
        ...provenancePayload(provenance),
      };
      if (isGrammar) {
        body.grammar_domain = domain;
        body.pos_tag = pos;
        body.construction_type = construction;
      }
      await api(`/rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete this rule? This takes effect after the next Commit export.")) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await api(`/rules/${rule.id}`, { method: "DELETE" });
      onDeleted?.();
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="panel-card p-5 mt-2 border-violet-500/30 animate-slide-up">
      <p className="text-[10px] uppercase tracking-wide text-render-subtle mb-3">
        Edit {rule.category} note
      </p>
      <label className="block mb-4">
        <span className="text-[10px] uppercase tracking-wide text-render-subtle">Content</span>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          className="input-field mt-1 text-xs resize-y min-h-[5rem]"
        />
      </label>
      {isGrammar && (
        <div className="grid gap-3 sm:grid-cols-3 mb-4">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-render-subtle">Grammar area</span>
            <select value={domain} onChange={(e) => setDomain(e.target.value)} className="input-field mt-1 text-xs">
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
      )}
      <p className="text-[10px] uppercase tracking-wide text-render-subtle mb-2">Citation locators</p>
      <ProvenanceFields values={provenance} onChange={setProvenance} />
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
      <div className="flex flex-wrap gap-2 mt-4">
        <button type="button" onClick={save} disabled={saving} className="btn-primary text-xs py-1.5">
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onClose} className="btn-ghost text-xs">
          Cancel
        </button>
        <button
          type="button"
          onClick={remove}
          disabled={deleting}
          className="btn-danger text-xs py-1.5 ml-auto"
        >
          {deleting ? "Deleting…" : "Delete rule"}
        </button>
      </div>
    </div>
  );
}

export { RuleEntryEditor as RuleEditPanel };
