import { useCallback, useState } from "react";
import { cleanPronunciation, speakPronunciation, speechSupported } from "../utils/pronunciation";

export function PronunciationGuide({
  pronunciation,
  className = "text-xs text-render-subtle mt-1",
}: {
  pronunciation: string;
  className?: string;
}) {
  const clean = cleanPronunciation(pronunciation);
  const [speaking, setSpeaking] = useState(false);
  const canSpeak = speechSupported();

  const listen = useCallback(() => {
    if (!clean) return;
    setSpeaking(true);
    speakPronunciation(clean);
    window.setTimeout(() => setSpeaking(false), 1200);
  }, [clean]);

  if (!clean) return null;

  return (
    <p className={`${className} flex flex-wrap items-center gap-2`}>
      <span className="font-mono text-render-muted">/{clean}/</span>
      {canSpeak && (
        <button
          type="button"
          onClick={listen}
          disabled={speaking}
          className="text-[10px] uppercase tracking-wide text-render-muted hover:text-white border border-render-border rounded-full px-2 py-0.5 transition-colors disabled:opacity-50"
          aria-label={`Listen to pronunciation: ${clean}`}
        >
          {speaking ? "Playing…" : "Listen"}
        </button>
      )}
    </p>
  );
}
