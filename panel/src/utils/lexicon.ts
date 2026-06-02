import { LexiconEntry } from "../api";

export function normalizeEnglish(text: string): string {
  return (text || "")
    .toLowerCase()
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** True when two rows are the same word + gloss (case/punctuation insensitive). */
export function sameLexeme(a: LexiconEntry, b: LexiconEntry): boolean {
  const wocconMatch =
    (a.woccon || "").trim().toLowerCase() === (b.woccon || "").trim().toLowerCase();
  const englishMatch = normalizeEnglish(a.english) === normalizeEnglish(b.english);
  return wocconMatch && englishMatch;
}

export function sourceCount(entry: LexiconEntry): number {
  const variants = entry.variant_count ?? 0;
  return variants + 1;
}
