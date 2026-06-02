import { ReactNode } from "react";
import { DuplicateMatchPreview, PendingLexicon, PendingRule } from "../api";
import { LexiconBadges } from "./LexiconBadges";
import { PronunciationGuide } from "./PronunciationGuide";
import { SourceCitation } from "./SourceCitation";
import { LexiconTaxonomy } from "../lexiconTaxonomy";
import { Taxonomy } from "../taxonomy";
import { RuleBadges } from "./RuleBadges";

function MatchTypeBadge({ matchType }: { matchType: string }) {
  const label = matchType === "canonical" ? "Canonical" : "Pending";
  const style =
    matchType === "canonical"
      ? "border-emerald-500/30 text-emerald-200"
      : "border-amber-500/30 text-amber-200";
  return (
    <span className={`badge border text-[10px] uppercase tracking-wider ${style}`}>{label}</span>
  );
}

function CompareColumn({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex-1 min-w-0 p-3 rounded-lg bg-black/20 border border-render-border">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider text-render-subtle font-medium">
          {title}
        </span>
        {badge}
      </div>
      {children}
    </div>
  );
}

export function LexiconDuplicateCompare({
  entry,
  duplicateMatch,
  duplicateScore,
  taxonomy,
  onClose,
}: {
  entry: PendingLexicon;
  duplicateMatch?: DuplicateMatchPreview | null;
  duplicateScore?: number | null;
  taxonomy?: LexiconTaxonomy | null;
  onClose: () => void;
}) {
  return (
    <div className="mt-3 p-3 rounded-xl bg-black/20 border border-amber-500/25 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-amber-200">
          Similarity score: {((duplicateScore ?? 0) * 100).toFixed(0)}%
        </p>
        <button type="button" onClick={onClose} className="btn-secondary text-xs">
          Close
        </button>
      </div>
      {!duplicateMatch ? (
        <p className="text-sm text-render-muted">
          The linked duplicate could not be found (it may have been rejected or removed).
        </p>
      ) : (
        <div className="flex flex-col md:flex-row gap-3">
          <CompareColumn title="This pending entry">
            <p className="text-sm text-render-text">
              <span className="font-semibold text-white">{entry.woccon}</span>
              <span className="text-render-muted"> — {entry.english}</span>
              {entry.pos && (
                <span className="text-render-subtle text-xs ml-1">({entry.pos})</span>
              )}
            </p>
            {entry.pronunciation && <PronunciationGuide pronunciation={entry.pronunciation} />}
            {taxonomy && (
              <LexiconBadges
                taxonomy={taxonomy}
                teaching_unit={entry.teaching_unit}
                word_class={entry.word_class}
                lesson_band={entry.lesson_band}
              />
            )}
            <SourceCitation citation={entry.citation} />
          </CompareColumn>
          <CompareColumn
            title="Existing match"
            badge={<MatchTypeBadge matchType={duplicateMatch.match_type} />}
          >
            <p className="text-sm text-render-text">
              <span className="font-semibold text-white">{duplicateMatch.woccon}</span>
              <span className="text-render-muted"> — {duplicateMatch.english}</span>
              {duplicateMatch.pos && (
                <span className="text-render-subtle text-xs ml-1">({duplicateMatch.pos})</span>
              )}
            </p>
            {duplicateMatch.pronunciation && (
              <PronunciationGuide pronunciation={duplicateMatch.pronunciation} />
            )}
            {taxonomy && (
              <LexiconBadges
                taxonomy={taxonomy}
                teaching_unit={duplicateMatch.teaching_unit}
                word_class={duplicateMatch.word_class}
                lesson_band={duplicateMatch.lesson_band}
              />
            )}
            {duplicateMatch.status && duplicateMatch.match_type === "pending" && (
              <span className="badge border border-render-border text-render-muted mt-2 inline-flex text-xs">
                Status: {duplicateMatch.status}
              </span>
            )}
            <SourceCitation citation={duplicateMatch.citation} />
          </CompareColumn>
        </div>
      )}
    </div>
  );
}

export function RuleDuplicateCompare({
  entry,
  duplicateMatch,
  duplicateScore,
  taxonomy,
  onClose,
}: {
  entry: PendingRule;
  duplicateMatch?: DuplicateMatchPreview | null;
  duplicateScore?: number | null;
  taxonomy?: Taxonomy | null;
  onClose: () => void;
}) {
  return (
    <div className="mt-3 p-3 rounded-xl bg-black/20 border border-amber-500/25 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-amber-200">
          Similarity score: {((duplicateScore ?? 0) * 100).toFixed(0)}%
        </p>
        <button type="button" onClick={onClose} className="btn-secondary text-xs">
          Close
        </button>
      </div>
      {!duplicateMatch ? (
        <p className="text-sm text-render-muted">
          The linked duplicate could not be found (it may have been rejected or removed).
        </p>
      ) : (
        <div className="flex flex-col md:flex-row gap-3">
          <CompareColumn title="This pending rule">
            <span className="text-[10px] uppercase tracking-wider text-render-subtle">
              {entry.category}
            </span>
            <p className="text-sm text-render-text leading-relaxed mt-1">{entry.content}</p>
            {taxonomy && (
              <RuleBadges
                taxonomy={taxonomy}
                grammar_domain={entry.grammar_domain}
                pos_tag={entry.pos_tag}
                construction_type={entry.construction_type}
                grammar_lineage={entry.grammar_lineage}
              />
            )}
            <SourceCitation citation={entry.citation} />
          </CompareColumn>
          <CompareColumn
            title="Existing match"
            badge={<MatchTypeBadge matchType={duplicateMatch.match_type} />}
          >
            <span className="text-[10px] uppercase tracking-wider text-render-subtle">
              {duplicateMatch.category}
            </span>
            <p className="text-sm text-render-text leading-relaxed mt-1">{duplicateMatch.content}</p>
            {duplicateMatch.status && duplicateMatch.match_type === "pending" && (
              <span className="badge border border-render-border text-render-muted mt-2 inline-flex text-xs">
                Status: {duplicateMatch.status}
              </span>
            )}
            <SourceCitation citation={duplicateMatch.citation} />
          </CompareColumn>
        </div>
      )}
    </div>
  );
}
