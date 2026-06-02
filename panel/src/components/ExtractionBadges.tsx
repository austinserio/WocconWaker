const BADGE_STYLES: Record<string, string> = {
  vocabulary: "bg-emerald-500/15 text-emerald-200 border-emerald-500/25",
  grammar: "bg-sky-500/15 text-sky-200 border-sky-500/25",
  pronunciation: "bg-violet-500/15 text-violet-200 border-violet-500/25",
  cultural: "bg-amber-500/15 text-amber-200 border-amber-500/25",
};

const BADGE_LABELS: Record<string, string> = {
  vocabulary: "Vocabulary",
  grammar: "Grammar",
  pronunciation: "Pronunciation",
  cultural: "Culture",
};

export type ExtractedCounts = {
  vocabulary?: number;
  grammar?: number;
  pronunciation?: number;
  cultural?: number;
};

export function ExtractionBadges({ extracted }: { extracted?: ExtractedCounts | null }) {
  if (!extracted) return null;

  const items = (Object.keys(BADGE_LABELS) as Array<keyof typeof BADGE_LABELS>).filter(
    (key) => (extracted[key] ?? 0) > 0
  );
  if (!items.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-2">
      {items.map((key) => (
        <span
          key={key}
          className={`badge border text-xs ${BADGE_STYLES[key]}`}
          title={`${extracted[key]} item${extracted[key] === 1 ? "" : "s"}`}
        >
          {BADGE_LABELS[key]}
          <span className="opacity-70 ml-1">{extracted[key]}</span>
        </span>
      ))}
    </div>
  );
}
