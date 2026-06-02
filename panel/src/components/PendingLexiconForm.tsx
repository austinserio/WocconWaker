import { useEffect, useState } from "react";
import { api, PendingLexicon } from "../api";
import { LexiconTaxonomy } from "../lexiconTaxonomy";
import {
  ProvenanceFields,
  provenanceFromRow,
  provenancePayload,
  ProvenanceValues,
} from "./ProvenanceFields";

export function PendingLexiconForm({
  entry,
  taxonomy,
  onSaved,
  onCancel,
}: {
  entry?: PendingLexicon;
  taxonomy: LexiconTaxonomy;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const isCreate = !entry;
  const [woccon, setWoccon] = useState(entry?.woccon ?? "");
  const [english, setEnglish] = useState(entry?.english ?? "");
  const [pos, setPos] = useState(entry?.pos ?? "unknown");
  const [pronunciation, setPronunciation] = useState(entry?.pronunciation ?? "");
  const [unit, setUnit] = useState(entry?.teaching_unit ?? "other");
  const [wordClass, setWordClass] = useState(entry?.word_class ?? "unknown");
  const [band, setBand] = useState(entry?.lesson_band ?? "intermediate");
  const [reviewerNotes, setReviewerNotes] = useState(entry?.reviewer_notes ?? "");
  const [provenance, setProvenance] = useState<ProvenanceValues>(() => provenanceFromRow(entry));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entry) return;
    setWoccon(entry.woccon);
    setEnglish(entry.english);
    setPos(entry.pos ?? "unknown");
    setPronunciation(entry.pronunciation ?? "");
    setUnit(entry.teaching_unit ?? "other");
    setWordClass(entry.word_class ?? "unknown");
    setBand(entry.lesson_band ?? "intermediate");
    setReviewerNotes(entry.reviewer_notes ?? "");
    setProvenance(provenanceFromRow(entry));
  }, [entry]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = {
        woccon: woccon.trim(),
        english: english.trim(),
        pos: pos.trim() || "unknown",
        pronunciation: pronunciation.trim() || null,
        teaching_unit: unit,
        word_class: wordClass,
        lesson_band: band,
        reviewer_notes: reviewerNotes.trim() || null,
        ...provenancePayload(provenance),
      };
      if (isCreate) {
        await api("/pending/lexicon", { method: "POST", body: JSON.stringify(body) });
      } else {
        await api(`/pending/lexicon/${entry.id}`, {
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
    <div className="panel-card p-5 border-amber-500/30 animate-slide-up">
      <p className="text-xs text-render-muted mb-4">
        {isCreate ? "Add a manual lexicon entry for review." : "Edit pending lexicon entry."}
      </p>
      <div className="grid gap-3 sm:grid-cols-2 mb-4">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Woccon</span>
          <input
            value={woccon}
            onChange={(e) => setWoccon(e.target.value)}
            className="input-field mt-1 text-xs"
            required
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">English</span>
          <input
            value={english}
            onChange={(e) => setEnglish(e.target.value)}
            className="input-field mt-1 text-xs"
            required
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">POS</span>
          <input
            value={pos}
            onChange={(e) => setPos(e.target.value)}
            className="input-field mt-1 text-xs"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Pronunciation</span>
          <input
            value={pronunciation}
            onChange={(e) => setPronunciation(e.target.value)}
            className="input-field mt-1 text-xs"
            placeholder="optional"
          />
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-3 mb-4">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Teaching unit</span>
          <select value={unit} onChange={(e) => setUnit(e.target.value)} className="input-field mt-1 text-xs">
            {taxonomy.teaching_units.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Word class</span>
          <select
            value={wordClass}
            onChange={(e) => setWordClass(e.target.value)}
            className="input-field mt-1 text-xs"
          >
            {taxonomy.word_classes.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Lesson band</span>
          <select value={band} onChange={(e) => setBand(e.target.value)} className="input-field mt-1 text-xs">
            {taxonomy.lesson_bands.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
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
          {saving ? "Saving…" : isCreate ? "Create entry" : "Save changes"}
        </button>
        <button type="button" onClick={onCancel} className="btn-ghost text-xs">
          Cancel
        </button>
      </div>
    </div>
  );
}
