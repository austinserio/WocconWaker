import { useEffect, useState } from "react";
import { api, LexiconEntry } from "../api";
import { SourceCitation } from "./SourceCitation";
import { PronunciationGuide } from "./PronunciationGuide";
import { Spinner } from "./ui";

export function VariantList({ baseEntryId }: { baseEntryId: string }) {
  const [variants, setVariants] = useState<LexiconEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api<LexiconEntry[]>(`/lexicon/${baseEntryId}/variants`)
      .then(setVariants)
      .finally(() => setLoading(false));
  }, [baseEntryId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-render-muted py-2 pl-4">
        <Spinner />
        <span className="text-xs">Loading variants…</span>
      </div>
    );
  }

  if (variants.length === 0) {
    return <p className="text-xs text-render-subtle pl-4 py-2">No other attestations linked yet.</p>;
  }

  return (
    <ul className="mt-2 ml-4 border-l border-render-border pl-4 space-y-2">
      {variants.map((v) => (
        <li key={v.id} className="text-sm">
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            <span className="font-medium text-render-text">{v.woccon}</span>
            <span className="text-render-muted">{v.english}</span>
            {v.pos && <span className="text-xs text-render-subtle">({v.pos})</span>}
            {v.base_match_method && (
              <span className="text-[10px] text-render-subtle uppercase tracking-wide">
                {v.base_match_method.replace("_", " ")}
                {v.base_match_score != null ? ` ${(v.base_match_score * 100).toFixed(0)}%` : ""}
              </span>
            )}
          </div>
          {v.pronunciation && (
            <PronunciationGuide
              pronunciation={v.pronunciation}
              pronunciationAudioUrl={v.pronunciation_audio_url}
              className="text-xs mt-1"
            />
          )}
          <SourceCitation citation={v.citation} />
        </li>
      ))}
    </ul>
  );
}
