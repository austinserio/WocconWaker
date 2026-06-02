/** Strip wrapping parentheses/slashes from pronunciation guides. */
export function cleanPronunciation(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let s = raw.trim();
  if (!s) return null;
  if (s.startsWith("(") && s.endsWith(")")) {
    s = s.slice(1, -1).trim();
  }
  if (s.startsWith("/") && s.endsWith("/") && s.length > 2) {
    s = s.slice(1, -1).trim();
  }
  return s.replace(/\s+/g, " ").trim() || null;
}

export function speechSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** Speak a community phonetic guide (hyphens → pauses for clearer TTS). */
export function speakPronunciation(guide: string): void {
  if (!speechSupported()) return;
  const text = guide.replace(/-/g, " ").trim();
  if (!text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.88;
  utterance.lang = "en-US";
  window.speechSynthesis.speak(utterance);
}
