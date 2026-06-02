import { LexiconEntry } from "../api";
import { sourceCount } from "../utils/lexicon";
import { LexiconBadges } from "./LexiconBadges";
import { AttestationList } from "./AttestationList";
import { PronunciationGuide } from "./PronunciationGuide";
import { SourceCitation } from "./SourceCitation";
import { LexiconTaxonomy } from "../lexiconTaxonomy";

export function LexiconEntryCard({
  entry,
  taxonomy,
  editing,
  onEdit,
  expanded,
  onToggleExpand,
  showExpand = false,
}: {
  entry: LexiconEntry;
  taxonomy?: LexiconTaxonomy | null;
  editing?: boolean;
  onEdit?: () => void;
  expanded?: boolean;
  onToggleExpand?: () => void;
  showExpand?: boolean;
}) {
  const sources = entry.source_count ?? sourceCount(entry);
  const hasLinkedSources = (entry.variant_count ?? 0) > 0;
  const canExpand = showExpand && entry.is_base_entry && (hasLinkedSources || !!entry.citation?.short);

  return (
    <li className="panel-card p-4 mb-2">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
        {canExpand && (
          <button
            type="button"
            onClick={onToggleExpand}
            className="text-render-muted hover:text-white text-xs mt-0.5 shrink-0"
            aria-expanded={expanded}
          >
            {expanded ? "▾" : "▸"}
          </button>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span className="font-medium text-render-text">{entry.woccon}</span>
            <span className="text-sm text-render-muted">{entry.english}</span>
            {entry.pos && (
              <span className="text-xs text-render-subtle self-center">({entry.pos})</span>
            )}
            {entry.is_base_entry && (
              <span className="badge border border-emerald-500/30 text-emerald-200 text-[10px]">Base</span>
            )}
            {hasLinkedSources && (
              <span className="badge border border-white/10 text-render-muted text-[10px]">
                {sources} citation{sources === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {entry.pronunciation && <PronunciationGuide pronunciation={entry.pronunciation} />}
          {taxonomy && (
            <LexiconBadges
              taxonomy={taxonomy}
              teaching_unit={entry.teaching_unit}
              word_class={entry.word_class}
              lesson_band={entry.lesson_band}
            />
          )}
          <div className="flex gap-3 mt-2 flex-wrap items-center">
            {canExpand && !expanded ? (
              <button
                type="button"
                onClick={onToggleExpand}
                className="text-xs text-render-muted hover:text-white"
              >
                {sources} citation{sources === 1 ? "" : "s"} — expand to view
              </button>
            ) : !canExpand ? (
              <SourceCitation citation={entry.citation} />
            ) : null}
            {onEdit && (
              <button
                type="button"
                onClick={onEdit}
                className="text-xs text-render-muted hover:text-white"
              >
                {editing ? "Close" : "Edit"}
              </button>
            )}
          </div>
          {canExpand && expanded && <AttestationList baseEntry={entry} />}
        </div>
      </div>
    </li>
  );
}
