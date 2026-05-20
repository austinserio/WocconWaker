const TOKEN_KEY = "woccon_panel_token";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const res = await fetch(`/api${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/panel/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return {} as T;
  return res.json();
}

export interface User {
  id: string;
  email: string;
  role: string;
}

export interface CanonicalRule {
  id: string;
  category: string;
  content: string;
  source_url?: string;
  sort_order: number;
  grammar_domain?: string | null;
  pos_tag?: string | null;
  construction_type?: string | null;
}

export interface LexiconEntry {
  id: string;
  woccon: string;
  english: string;
  pos: string;
  pronunciation?: string;
  source?: string;
  source_url?: string;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
}

export interface PendingLexicon {
  id: string;
  woccon: string;
  english: string;
  pos: string;
  status: string;
  duplicate_of_id?: string;
  duplicate_score?: number;
  source_url?: string;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
}

export interface PendingRule {
  id: string;
  category: string;
  content: string;
  status: string;
  duplicate_of_id?: string;
  duplicate_score?: number;
  source_url?: string;
  grammar_domain?: string | null;
  pos_tag?: string | null;
  construction_type?: string | null;
}

export interface SourceDocument {
  id: string;
  title: string;
  source_type: string;
  status: string;
  source_url?: string;
  error_message?: string;
  created_at: string;
}
