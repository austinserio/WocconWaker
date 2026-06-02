import { TaxonomyOption } from "../taxonomy";

export type ExtractionFocus = "general" | "vocabulary" | "grammar" | "pronunciation" | "culture";

export interface ExtractionFocusValue {
  extraction_focus: ExtractionFocus;
  grammar_lineage: string | null;
}

export function ExtractionFocusPicker({
  focuses,
  lineages,
  value,
  onChange,
  compact = false,
}: {
  focuses: TaxonomyOption[];
  lineages: TaxonomyOption[];
  value: ExtractionFocusValue;
  onChange: (v: ExtractionFocusValue) => void;
  compact?: boolean;
}) {
  const selectedFocus = focuses.find((f) => f.id === value.extraction_focus);
  const selectedLineage = lineages.find((l) => l.id === value.grammar_lineage);

  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      <div>
        <p className="text-xs font-medium text-render-text mb-2">Analysis focus</p>
        <div className="flex flex-wrap gap-2">
          {focuses.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() =>
                onChange({
                  extraction_focus: f.id as ExtractionFocus,
                  grammar_lineage:
                    f.id === "grammar" ? value.grammar_lineage ?? "woccon_attested" : null,
                })
              }
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                value.extraction_focus === f.id
                  ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200"
                  : "border-render-border text-render-muted hover:text-render-text"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {selectedFocus?.description && (
          <p className="text-xs text-render-subtle mt-2">{selectedFocus.description}</p>
        )}
      </div>

      {value.extraction_focus === "grammar" && (
        <div>
          <p className="text-xs font-medium text-render-text mb-2">Grammar lineage filter</p>
          <select
            value={value.grammar_lineage ?? "woccon_attested"}
            onChange={(e) =>
              onChange({ ...value, grammar_lineage: e.target.value || "woccon_attested" })
            }
            className="input-field text-sm max-w-lg"
          >
            {lineages.map((l) => (
              <option key={l.id} value={l.id}>
                {l.label}
              </option>
            ))}
          </select>
          {selectedLineage?.description && (
            <p className="text-xs text-render-subtle mt-2">{selectedLineage.description}</p>
          )}
        </div>
      )}
    </div>
  );
}
