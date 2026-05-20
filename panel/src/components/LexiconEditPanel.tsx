import { useState } from "react";
import { api, LexiconEntry } from "../api";
import { LexiconTaxonomy } from "../lexiconTaxonomy";

export function LexiconEditPanel({
  entry,
  taxonomy,
  onClose,
  onSaved,
}: {
  entry: LexiconEntry;
  taxonomy: LexiconTaxonomy;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [unit, setUnit] = useState(entry.teaching_unit ?? "other");
  const [wordClass, setWordClass] = useState(entry.word_class ?? "unknown");
  const [band, setBand] = useState(entry.lesson_band ?? "intermediate");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api(`/lexicon/${entry.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          teaching_unit: unit,
          word_class: wordClass,
          lesson_band: band,
        }),
      });
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel-card p-5 mt-2 border-amber-500/30 animate-slide-up">
      <p className="text-xs text-render-muted mb-3">
        <span className="font-medium text-render-text">{entry.woccon}</span>
        {" — "}
        {entry.english}
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Teaching unit</span>
          <select
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            className="input-field mt-1 text-xs"
          >
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
          <select
            value={band}
            onChange={(e) => setBand(e.target.value)}
            className="input-field mt-1 text-xs"
          >
            {taxonomy.lesson_bands.map((o) => (
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
