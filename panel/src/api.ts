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
    if (token) {
      clearToken();
      window.location.href = "/panel/login";
    }
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
  first_name?: string | null;
  last_name?: string | null;
  display_name: string;
  is_active?: boolean;
  created_at?: string;
}

export interface CitationOut {
  short: string;
  full: string;
  page?: number | null;
  page_end?: number | null;
  excerpt?: string | null;
  provenance_status?: string | null;
  document_id?: string | null;
  document_title?: string | null;
  source_url?: string | null;
  file_url?: string | null;
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
  grammar_lineage?: string | null;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  provenance_status?: string | null;
  citation?: CitationOut | null;
}

export interface LexiconEntry {
  id: string;
  woccon: string;
  english: string;
  pos: string;
  pronunciation?: string;
  pronunciation_audio_url?: string | null;
  source?: string;
  source_url?: string;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  provenance_status?: string | null;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
  citation?: CitationOut | null;
  is_base_entry?: boolean;
  base_entry_id?: string | null;
  base_match_score?: number | null;
  base_match_method?: string | null;
  variant_count?: number | null;
  source_count?: number | null;
  sort_order?: number | null;
}

export interface LexiconListResponse {
  items: LexiconEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface BaseMatchPreview {
  id: string;
  woccon: string;
  english: string;
  score?: number | null;
  method?: string | null;
}

export interface DuplicateMatchPreview {
  id: string;
  match_type: "canonical" | "pending" | string;
  woccon?: string | null;
  english?: string | null;
  pos?: string | null;
  pronunciation?: string | null;
  pronunciation_audio_url?: string | null;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
  category?: string | null;
  content?: string | null;
  status?: string | null;
  source_url?: string | null;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  provenance_status?: string | null;
  citation?: CitationOut | null;
}

export interface PendingLexicon {
  id: string;
  woccon: string;
  english: string;
  pos: string;
  pronunciation?: string;
  pronunciation_audio_url?: string | null;
  status: string;
  reviewer_notes?: string;
  duplicate_of_id?: string;
  duplicate_score?: number;
  duplicate_match?: DuplicateMatchPreview | null;
  base_entry_id?: string | null;
  base_match_score?: number | null;
  base_match_method?: string | null;
  match_status?: string | null;
  base_match?: BaseMatchPreview | null;
  source_url?: string;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  provenance_status?: string | null;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
  citation?: CitationOut | null;
}

export interface PendingRule {
  id: string;
  category: string;
  content: string;
  status: string;
  reviewer_notes?: string;
  duplicate_of_id?: string;
  duplicate_score?: number;
  duplicate_match?: DuplicateMatchPreview | null;
  source_url?: string;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  provenance_status?: string | null;
  grammar_domain?: string | null;
  pos_tag?: string | null;
  construction_type?: string | null;
  grammar_lineage?: string | null;
  citation?: CitationOut | null;
}

export interface PendingCatawba {
  id: string;
  source_document_id?: string | null;
  catawba: string;
  english: string;
  pos: string;
  woccon_cited?: string | null;
  source_url?: string;
  status: string;
  reviewer_notes?: string;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  provenance_status?: string | null;
  citation?: CitationOut | null;
  created_at: string;
}

export interface PendingCatawbaSource {
  document_id: string;
  title: string;
  staging_path?: string | null;
  short_title?: string | null;
  year?: string | null;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  staging_vocabulary: number;
}

export interface PendingCatawbaStats {
  total_pending: number;
  total_approved: number;
  total_rejected: number;
  sources: PendingCatawbaSource[];
  link_review?: {
    queue_path?: string;
    total?: number;
    scholar_conflict?: number;
    gloss_only?: number;
    generated_at?: string;
  } | null;
}

export interface PendingCatawbaListResponse {
  items: PendingCatawba[];
  total: number;
  page: number;
  page_size: number;
}

export type ComparativeLinkType = "new_cognate" | "seed_gap" | "scholar_conflict" | "crosscheck";
export type ComparativeLinkDecision = "approved" | "rejected" | "alias" | "unsure";

export type SameWordConfidence = "high" | "medium" | "low" | "risky";

export interface SameWordPrefixWarning {
  detected: boolean;
  form_a_prefix?: string | null;
  form_b_prefix?: string | null;
  form_a_label?: string | null;
  form_b_label?: string | null;
  stem_similarity?: number | null;
  message?: string | null;
}

export interface SameWordCheck {
  form_similarity: number;
  comparison?: string | null;
  woccon_staging_similarity?: number | null;
  rudes_staging_similarity?: number | null;
  prefix_warning?: SameWordPrefixWarning | null;
  pos_warning?: {
    detected: boolean;
    woccon_pos?: string | null;
    staging_pos?: string | null;
    message?: string | null;
  } | null;
  woccon_pos?: string | null;
  staging_pos?: string | null;
  gloss_only_risk: boolean;
  source_gloss?: string | null;
  source_excerpt?: string | null;
  review_prompt: string;
  same_word_confidence: SameWordConfidence;
}

export interface ComparativeLink {
  item_key: string;
  item_type: ComparativeLinkType;
  gloss: string;
  woccon?: string | null;
  lawson_form?: string | null;
  woccon_reconstituted?: string | null;
  rudes_catawba?: string | null;
  staging_catawba?: string | null;
  woccon_pos?: string | null;
  catawba_pos?: string | null;
  pos_clash?: boolean | null;
  recommended_action?: string | null;
  source?: string | null;
  source_path?: string | null;
  seed_id?: string | null;
  match_kind?: string | null;
  form_similarity?: number | null;
  confidence?: string | null;
  action?: string | null;
  rudes_appendix?: number | null;
  evidence_tier?: string | null;
  priority?: number | null;
  decision?: ComparativeLinkDecision | null;
  reviewer_note?: string | null;
  decided_at?: string | null;
  status: "open" | "resolved";
  same_word_check?: SameWordCheck | null;
  seed_apply?: {
    updated_catawba: number;
    aliases_added: number;
    new_rows: number;
    skipped: number;
  } | null;
  seed_pool_size?: number | null;
}

export interface ComparativeLinkStats {
  total: number;
  open: number;
  resolved: number;
  generated_at?: string | null;
  instructions?: string | null;
  queue_path?: string | null;
  by_type: Record<
    string,
    { total: number; open: number; resolved: number }
  >;
  same_word?: Partial<Record<SameWordConfidence, number>> | null;
  seed_pool_size?: number | null;
  panel_decisions_applied_at?: string | null;
}

export interface CatawbaGrammarDraft {
  id: string;
  draft_type: "morpheme" | "compound" | "sense" | string;
  status: string;
  confidence?: string | null;
  source_path?: string | null;
  source_excerpt?: string | null;
  payload: Record<string, unknown>;
  reviewer_note?: string | null;
  created_at?: string | null;
  decided_at?: string | null;
}

export interface CatawbaGrammarStats {
  pending: number;
  approved_morphemes: number;
  approved_compounds: number;
  approved_senses: number;
}

export interface StagingSyncResponse {
  documents_registered: number;
  documents_updated: number;
  catawba_pending_imported: number;
  catawba_sources: number;
  woccon_sources: number;
  context_sources: number;
  errors: string[];
}

export interface PendingLexiconCreate {
  woccon: string;
  english: string;
  pos?: string;
  pronunciation?: string | null;
  pronunciation_audio_url?: string | null;
  teaching_unit?: string | null;
  word_class?: string | null;
  lesson_band?: string | null;
  source_document_id?: string | null;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  reviewer_notes?: string | null;
}

export interface PendingRuleCreate {
  category: string;
  content: string;
  source_document_id?: string | null;
  grammar_domain?: string | null;
  pos_tag?: string | null;
  construction_type?: string | null;
  source_page?: number | null;
  source_page_end?: number | null;
  source_excerpt?: string | null;
  reviewer_notes?: string | null;
}

export interface MergedSource {
  id: string;
  title: string;
  source_type: string;
  source_url?: string;
  status: string;
  error_message?: string;
  created_at: string;
  short_title?: string;
  year?: string;
  counts?: SourceDocument["counts"];
  text_extraction_method?: string | null;
  extraction_focus?: string | null;
  grammar_lineage?: string | null;
  progress_pct?: number | null;
  progress_message?: string | null;
}

export interface SourceDocument {
  id: string;
  title: string;
  source_type: string;
  status: string;
  source_url?: string;
  error_message?: string;
  created_at: string;
  short_title?: string;
  authors?: string;
  year?: string;
  pub_title?: string;
  container_title?: string;
  publisher?: string;
  place?: string;
  citation_text?: string;
  is_seed?: boolean;
  is_vocab_base?: boolean;
  counts?: {
    base_entries?: number;
    variants_from_other_sources?: number;
    unmatched_pending?: number;
    variants_linked?: number;
    extracted?: {
      vocabulary?: number;
      grammar?: number;
      pronunciation?: number;
      cultural?: number;
    };
  };
  progress_pct?: number | null;
  progress_message?: string | null;
  text_extraction_method?: string | null;
  extraction_focus?: string | null;
  grammar_lineage?: string | null;
  /** woccon | catawba | context. Catawba sources are comparative evidence, not Woccon vocabulary. */
  content_language?: string | null;
  staging_path?: string | null;
  has_pdf?: boolean;
  has_staging?: boolean;
  work_group_key?: string | null;
  work_group_label?: string | null;
  merged_sources?: MergedSource[];
}

export interface RuleTopicTierSummary {
  covered: number;
  total: number;
  gaps: string[];
  covered_ids?: string[];
}

export interface RulesCaptureDocAudit {
  live?: {
    tier_a?: RuleTopicTierSummary;
    tier_b?: RuleTopicTierSummary;
    tier_c?: RuleTopicTierSummary;
  };
  unknowns?: string[];
}

export interface RulesCaptureAudit {
  generated_at?: string;
  documents?: Record<string, RulesCaptureDocAudit>;
}

export interface CognateRuleExample {
  id: string;
  correspondence_rule_id: string;
  alignment?: Array<{ w_span?: string; c_span?: string; rule_id?: string }> | null;
}

export interface CognateSet {
  id: string;
  gloss: string;
  lawson_form?: string | null;
  lawson_form_corrected?: string | null;
  lawson_gloss?: string | null;
  woccon_reconstituted?: string | null;
  catawba_form?: string | null;
  catawba_dialect?: string | null;
  proto_siouan?: string | null;
  evidence_tier: string;
  rudes_appendix: number;
  rudes_item: number;
  citation_short?: string | null;
  source_path?: string | null;
  source_url?: string | null;
  notes?: string | null;
  canonical_lexicon_id?: string | null;
  rule_examples: CognateRuleExample[];
}

export interface CognateSetListResponse {
  items: CognateSet[];
  total: number;
  page: number;
  page_size: number;
}

export interface CorrespondenceRule {
  id: string;
  rule_kind: string;
  lhs?: string | null;
  rhs?: string | null;
  environment?: string | null;
  direction?: string | null;
  correspondence_status: string;
  grammar_lineage?: string | null;
  source: string;
  notes?: string | null;
  provenance_text?: string | null;
  example_cognate_ids: string[];
}

export interface CorrespondenceRuleListResponse {
  items: CorrespondenceRule[];
  total: number;
  page: number;
  page_size: number;
}
