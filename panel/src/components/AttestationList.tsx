import { useEffect, useMemo, useState } from "react";
import { api, LexiconEntry } from "../api";
import { PronunciationGuide } from "./PronunciationGuide";
import { SourceCitation } from "./SourceCitation";
import { Spinner } from "./ui";

function attestationLabel(entry: LexiconEntry, isBase: boolean): string | null {
  if (isBase) return "Definitive vocabulary";
  if (entry.source === "lawson" || entry.source?.includes("lawson")) return "Lawson (1709)";
  if (entry.source === "vocab_base") return "Definitive vocabulary";
  if (entry.source === "community_drive") return "Community source";
  return entry.citation?.document_title || entry.citation?.short || null;
}

function citationKey(entry: LexiconEntry): string {
  const c = entry.citation;
  return [c?.short, c?.page, c?.excerpt?.slice(0, 80), entry.source_url, entry.id].join("|");
}

function isAlternateSpelling(base: LexiconEntry, entry: LexiconEntry): boolean {
  return (
    (entry.woccon || "").trim().toLowerCase() !== (base.woccon || "").trim().toLowerCase()
  );
}

type CitationRow = {
  key: string;
  label: string | null;
  entry: LexiconEntry;
  alternateSpelling?: string;
};

export function AttestationList({ baseEntry }: { baseEntry: LexiconEntry }) {
  const [variants, setVariants] = useState<LexiconEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!baseEntry.is_base_entry) {
      setVariants([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<LexiconEntry[]>(`/lexicon/${baseEntry.id}/variants`)
      .then(setVariants)
      .finally(() => setLoading(false));
  }, [baseEntry.id, baseEntry.is_base_entry]);

  const { alternateSpellings, citations } = useMemo(() => {
    const alts: LexiconEntry[] = [];
    const cites: CitationRow[] = [];
    const seen = new Set<string>();

    for (const entry of variants) {
      if (isAlternateSpelling(baseEntry, entry)) {
        alts.push(entry);
      }
    }

    for (const entry of [baseEntry, ...variants]) {
      const key = citationKey(entry);
      if (seen.has(key)) continue;
      seen.add(key);

      const alt = isAlternateSpelling(baseEntry, entry) ? entry.woccon : undefined;
      cites.push({
        key,
        label: attestationLabel(entry, entry.id === baseEntry.id),
        entry,
        alternateSpelling: alt,
      });
    }

    return { alternateSpellings: alts, citations: cites };
  }, [baseEntry, variants]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-render-muted py-2 pl-4">
        <Spinner />
        <span className="text-xs">Loading citations…</span>
      </div>
    );
  }

  if (variants.length === 0 && !baseEntry.citation?.short) {
    return (
      <p className="text-xs text-render-subtle pl-4 py-2">No additional attestations linked yet.</p>
    );
  }

  const altEntry = alternateSpellings.find((e) => e.pronunciation);
  const altPronunciation = altEntry?.pronunciation;
  const altAudioUrl = altEntry?.pronunciation_audio_url;

  return (
    <div className="mt-3 ml-4 border-l border-render-border pl-4 space-y-3">
      {alternateSpellings.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-render-subtle mb-1">
            Alternate spelling{alternateSpellings.length === 1 ? "" : "s"}
          </p>
          <p className="text-sm text-render-muted">
            {alternateSpellings.map((e) => e.woccon).join(", ")}
            {alternateSpellings.some((e) => e.base_match_method) && (
              <span className="text-[10px] text-render-subtle ml-2 uppercase tracking-wide">
                {alternateSpellings
                  .map((e) => e.base_match_method?.replace(/_/g, " "))
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            )}
          </p>
          {altPronunciation && (
            <PronunciationGuide
              pronunciation={altPronunciation}
              pronunciationAudioUrl={altAudioUrl}
              className="text-xs mt-1"
            />
          )}
        </div>
      )}

      {citations.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-render-subtle mb-2">
            {citations.length} citation{citations.length === 1 ? "" : "s"}
          </p>
          <ul className="space-y-2">
            {citations.map(({ key, label, entry, alternateSpelling }) => (
              <li key={key} className="text-sm">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mb-0.5">
                  {label && (
                    <span className="text-[10px] uppercase tracking-wide text-render-subtle">
                      {label}
                    </span>
                  )}
                  {alternateSpelling && (
                    <span className="text-xs text-render-muted">as {alternateSpelling}</span>
                  )}
                </div>
                <SourceCitation citation={entry.citation} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
