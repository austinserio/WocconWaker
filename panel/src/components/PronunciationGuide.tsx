import { useCallback, useEffect, useRef, useState } from "react";
import { cleanPronunciation, speakPronunciation, speechSupported } from "../utils/pronunciation";

export function PronunciationGuide({
  pronunciation,
  pronunciationAudioUrl,
  className = "text-xs text-render-subtle mt-1",
}: {
  pronunciation: string;
  pronunciationAudioUrl?: string | null;
  className?: string;
}) {
  const clean = cleanPronunciation(pronunciation);
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canSpeak = speechSupported() || !!pronunciationAudioUrl;

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, []);

  const listen = useCallback(() => {
    if (!clean) return;
    setSpeaking(true);

    if (pronunciationAudioUrl) {
      const audio = new Audio(pronunciationAudioUrl);
      audioRef.current = audio;
      const finish = () => {
        setSpeaking(false);
        if (audioRef.current === audio) {
          audioRef.current = null;
        }
      };
      audio.addEventListener("ended", finish, { once: true });
      audio.addEventListener("error", finish, { once: true });
      void audio.play().catch(() => {
        finish();
        if (speechSupported()) {
          speakPronunciation(clean);
          window.setTimeout(() => setSpeaking(false), 1200);
        }
      });
      return;
    }

    if (speechSupported()) {
      speakPronunciation(clean);
      window.setTimeout(() => setSpeaking(false), 1200);
      return;
    }

    setSpeaking(false);
  }, [clean, pronunciationAudioUrl]);

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
