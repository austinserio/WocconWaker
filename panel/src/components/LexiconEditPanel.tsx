import { useEffect, useState } from "react";
import { api, LexiconEntry } from "../api";
import { LexiconTaxonomy } from "../lexiconTaxonomy";
import {
  ProvenanceFields,
  provenanceFromRow,
  provenancePayload,
  ProvenanceValues,
} from "./ProvenanceFields";

function isLawsonSource(source?: string | null): boolean {
  return Boolean(source && source.toLowerCase().includes("lawson"));
}

export function LexiconEntryEditor({
  entry,
  taxonomy,
  onClose,
  onSaved,
  onDeleted,
}: {
  entry: LexiconEntry;
  taxonomy: LexiconTaxonomy;
  onClose: () => void;
  onSaved: () => void;
  onDeleted?: () => void;
}) {
  const [woccon, setWoccon] = useState(entry.woccon);
  const [english, setEnglish] = useState(entry.english);
  const [pos, setPos] = useState(entry.pos ?? "unknown");
  const [pronunciation, setPronunciation] = useState(entry.pronunciation ?? "");
  const [unit, setUnit] = useState(entry.teaching_unit ?? "other");
  const [wordClass, setWordClass] = useState(entry.word_class ?? "unknown");
  const [band, setBand] = useState(entry.lesson_band ?? "intermediate");
  const [provenance, setProvenance] = useState<ProvenanceValues>(() => provenanceFromRow(entry));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lawson = isLawsonSource(entry.source);

  useEffect(() => {
    setWoccon(entry.woccon);
    setEnglish(entry.english);
    setPos(entry.pos ?? "unknown");
    setPronunciation(entry.pronunciation ?? "");
    setUnit(entry.teaching_unit ?? "other");
    setWordClass(entry.word_class ?? "unknown");
    setBand(entry.lesson_band ?? "intermediate");
    setProvenance(provenanceFromRow(entry));
  }, [entry]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api(`/lexicon/${entry.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          woccon: woccon.trim(),
          english: english.trim(),
          pos: pos.trim() || "unknown",
          pronunciation: pronunciation.trim() || null,
          teaching_unit: unit,
          word_class: wordClass,
          lesson_band: band,
          ...provenancePayload(provenance),
        }),
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
    if (
      !window.confirm(
        `Delete "${entry.woccon}" from the dictionary? This takes effect after the next Commit export.`
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await api(`/lexicon/${entry.id}`, { method: "DELETE" });
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
    <div className="panel-card p-5 mt-2 border-amber-500/30 animate-slide-up">
      <p className="text-[10px] uppercase tracking-wide text-render-subtle mb-3">Edit entry</p>
      <div className="grid gap-3 sm:grid-cols-2 mb-4">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">Woccon</span>
          <input
            value={woccon}
            onChange={(e) => setWoccon(e.target.value)}
            className="input-field mt-1 text-xs"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">English</span>
          <input
            value={english}
            onChange={(e) => setEnglish(e.target.value)}
            className="input-field mt-1 text-xs"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-render-subtle">POS</span>
          <input value={pos} onChange={(e) => setPos(e.target.value)} className="input-field mt-1 text-xs" />
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
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
      <div className="flex flex-wrap gap-2 mt-4">
        <button type="button" onClick={save} disabled={saving} className="btn-primary text-xs py-1.5">
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onClose} className="btn-ghost text-xs">
          Cancel
        </button>
        {lawson ? (
          <span
            className="text-xs text-render-subtle self-center ml-auto"
            title="Lawson seed entries cannot be deleted from the panel."
          >
            Lawson entry (delete disabled)
          </span>
        ) : (
          <button
            type="button"
            onClick={remove}
            disabled={deleting}
            className="btn-danger text-xs py-1.5 ml-auto"
          >
            {deleting ? "Deleting…" : "Delete entry"}
          </button>
        )}
      </div>
    </div>
  );
}

export { LexiconEntryEditor as LexiconEditPanel };
