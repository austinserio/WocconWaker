import { useEffect, useState } from "react";
import { api, PendingRule } from "../api";
import { Taxonomy } from "../taxonomy";
import {
  ProvenanceFields,
  provenanceFromRow,
  provenancePayload,
  ProvenanceValues,
} from "./ProvenanceFields";

const CATEGORIES = [
  { id: "grammar", label: "Grammar" },
  { id: "pronunciation", label: "Pronunciation" },
  { id: "cultural", label: "Cultural" },
] as const;

export function PendingRuleForm({
  entry,
  taxonomy,
  onSaved,
  onCancel,
}: {
  entry?: PendingRule;
  taxonomy: Taxonomy;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const isCreate = !entry;
  const [category, setCategory] = useState(entry?.category ?? "grammar");
  const [content, setContent] = useState(entry?.content ?? "");
  const [domain, setDomain] = useState(entry?.grammar_domain ?? "other");
  const [pos, setPos] = useState(entry?.pos_tag ?? "multi");
  const [construction, setConstruction] = useState(entry?.construction_type ?? "na");
  const [reviewerNotes, setReviewerNotes] = useState(entry?.reviewer_notes ?? "");
  const [provenance, setProvenance] = useState<ProvenanceValues>(() => provenanceFromRow(entry));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entry) return;
    setCategory(entry.category);
    setContent(entry.content);
    setDomain(entry.grammar_domain ?? "other");
    setPos(entry.pos_tag ?? "multi");
    setConstruction(entry.construction_type ?? "na");
    setReviewerNotes(entry.reviewer_notes ?? "");
    setProvenance(provenanceFromRow(entry));
  }, [entry]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        category,
        content: content.trim(),
        reviewer_notes: reviewerNotes.trim() || null,
        ...provenancePayload(provenance),
      };
      if (category === "grammar") {
        body.grammar_domain = domain;
        body.pos_tag = pos;
        body.construction_type = construction;
      }
      if (isCreate) {
        await api("/pending/rules", { method: "POST", body: JSON.stringify(body) });
      } else {
        await api(`/pending/rules/${entry.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel-card p-5 border-violet-500/30 animate-slide-up">
      <p className="text-xs text-render-muted mb-4">
        {isCreate ? "Add a manual rule note for review." : "Edit pending rule."}
      </p>
      <div className="grid gap-3 sm:grid-cols-2 mb-4">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="input-field mt-1 text-xs"
          >
            {CATEGORIES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block mb-4">
        <span className="text-[10px] uppercase tracking-wide text-render-subtle">Content</span>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          className="input-field mt-1 text-xs resize-y min-h-[5rem]"
          required
        />
      </label>
      {category === "grammar" && (
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
      <label className="block mt-4">
        <span className="text-[10px] uppercase tracking-wide text-render-subtle">Reviewer notes</span>
        <textarea
          value={reviewerNotes}
          onChange={(e) => setReviewerNotes(e.target.value)}
          rows={2}
          className="input-field mt-1 text-xs resize-y"
          placeholder="optional"
        />
      </label>
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
      <div className="flex gap-2 mt-4">
        <button type="button" onClick={save} disabled={saving} className="btn-primary text-xs py-1.5">
          {saving ? "Saving…" : isCreate ? "Create rule" : "Save changes"}
        </button>
        <button type="button" onClick={onCancel} className="btn-ghost text-xs">
          Cancel
        </button>
      </div>
    </div>
  );
}
