"""Pydantic schemas for panel API."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


VALID_ROLES = frozenset({"admin", "worker", "member"})


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: str
    is_active: bool = True
    created_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfilePatchRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserInviteCreate(BaseModel):
    email: str
    role: str = "worker"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError("Invalid role")
        return v


class UserInviteOut(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    created_at: datetime
    invite_url: Optional[str] = None

    class Config:
        from_attributes = True


class UsersListResponse(BaseModel):
    users: List[UserOut]
    invitations: List[UserInviteOut]
    email_mode: str = "log"
    email_delivery_configured: bool = False


class UserRolePatch(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError("Invalid role")
        return v


class InvitePreviewOut(BaseModel):
    email: str
    role: str


class InviteAcceptRequest(BaseModel):
    token: str
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    detail: str


class SourceDocumentOut(BaseModel):
    id: str
    title: str
    source_type: str
    mime_type: Optional[str] = None
    source_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    counts: Optional[dict] = None
    short_title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[str] = None
    pub_title: Optional[str] = None
    container_title: Optional[str] = None
    publisher: Optional[str] = None
    place: Optional[str] = None
    citation_text: Optional[str] = None
    is_seed: bool = False
    is_vocab_base: bool = False
    progress_pct: Optional[int] = None
    progress_message: Optional[str] = None
    text_extraction_method: Optional[str] = None
    extraction_focus: Optional[str] = "general"
    grammar_lineage: Optional[str] = None
    work_group_key: Optional[str] = None
    work_group_label: Optional[str] = None
    merged_sources: Optional[List["MergedSourceOut"]] = None

    class Config:
        from_attributes = True


class MergedSourceOut(BaseModel):
    """Alternate scan of the same work, nested under the primary library entry."""
    id: str
    title: str
    source_type: str
    source_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    counts: Optional[dict] = None
    short_title: Optional[str] = None
    year: Optional[str] = None
    text_extraction_method: Optional[str] = None
    extraction_focus: Optional[str] = "general"
    grammar_lineage: Optional[str] = None
    progress_pct: Optional[int] = None
    progress_message: Optional[str] = None

    class Config:
        from_attributes = True


class SourceDocumentPatch(BaseModel):
    title: Optional[str] = None
    short_title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[str] = None
    pub_title: Optional[str] = None
    container_title: Optional[str] = None
    publisher: Optional[str] = None
    place: Optional[str] = None
    citation_text: Optional[str] = None


class CitationOut(BaseModel):
    short: str
    full: str
    page: Optional[int] = None
    page_end: Optional[int] = None
    excerpt: Optional[str] = None
    provenance_status: Optional[str] = None
    document_id: Optional[str] = None
    document_title: Optional[str] = None
    source_url: Optional[str] = None
    file_url: Optional[str] = None


class BaseMatchPreview(BaseModel):
    id: str
    woccon: str
    english: str
    score: Optional[float] = None
    method: Optional[str] = None


class DuplicateMatchPreview(BaseModel):
    id: str
    match_type: str  # canonical | pending
    woccon: Optional[str] = None
    english: Optional[str] = None
    pos: Optional[str] = None
    pronunciation: Optional[str] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    source_url: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None
    citation: Optional[CitationOut] = None


class PendingLexiconOut(BaseModel):
    id: str
    source_document_id: Optional[str] = None
    woccon: str
    english: str
    pos: str
    pronunciation: Optional[str] = None
    source_url: Optional[str] = None
    status: str
    reviewer_notes: Optional[str] = None
    duplicate_of_id: Optional[str] = None
    duplicate_score: Optional[float] = None
    duplicate_match: Optional[DuplicateMatchPreview] = None
    base_entry_id: Optional[str] = None
    base_match_score: Optional[float] = None
    base_match_method: Optional[str] = None
    match_status: Optional[str] = None
    base_match: Optional[BaseMatchPreview] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None
    citation: Optional[CitationOut] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PendingLexiconCreate(BaseModel):
    woccon: str
    english: str
    pos: str = "unknown"
    pronunciation: Optional[str] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    source_document_id: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    reviewer_notes: Optional[str] = None

    @field_validator("woccon", "english")
    @classmethod
    def strip_required(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("must not be empty")
        return s


class PendingLexiconPatch(BaseModel):
    woccon: Optional[str] = None
    english: Optional[str] = None
    pos: Optional[str] = None
    pronunciation: Optional[str] = None
    status: Optional[str] = None
    reviewer_notes: Optional[str] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None


class PendingRuleOut(BaseModel):
    id: str
    source_document_id: Optional[str] = None
    category: str
    content: str
    source_url: Optional[str] = None
    status: str
    reviewer_notes: Optional[str] = None
    duplicate_of_id: Optional[str] = None
    duplicate_score: Optional[float] = None
    duplicate_match: Optional[DuplicateMatchPreview] = None
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None
    grammar_lineage: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None
    citation: Optional[CitationOut] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PendingRuleCreate(BaseModel):
    category: str
    content: str
    source_document_id: Optional[str] = None
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    reviewer_notes: Optional[str] = None

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if s not in ("grammar", "pronunciation", "cultural"):
            raise ValueError("category must be grammar, pronunciation, or cultural")
        return s

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("content must not be empty")
        return s


class PendingRulePatch(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    reviewer_notes: Optional[str] = None
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None


class BulkStatusRequest(BaseModel):
    ids: List[str]
    status: str


class CanonicalRuleOut(BaseModel):
    id: str
    category: str
    content: str
    source_url: Optional[str] = None
    sort_order: int
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None
    grammar_lineage: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None
    citation: Optional[CitationOut] = None

    class Config:
        from_attributes = True


class RuleGroupOut(BaseModel):
    grammar_domain: str
    label: str
    count: int
    rules: List[CanonicalRuleOut]


class RuleReorderRequest(BaseModel):
    category: str
    ordered_ids: List[str]
    grammar_domain: Optional[str] = None


class CanonicalRulePatch(BaseModel):
    content: Optional[str] = None
    source_url: Optional[str] = None
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None


class LinkBaseRequest(BaseModel):
    base_entry_id: str


class CanonicalLexiconOut(BaseModel):
    id: str
    woccon: str
    english: str
    pos: str
    pronunciation: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    source_document_id: Optional[str] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None
    citation: Optional[CitationOut] = None
    is_base_entry: bool = False
    base_entry_id: Optional[str] = None
    base_match_score: Optional[float] = None
    base_match_method: Optional[str] = None
    variant_count: Optional[int] = None
    source_count: Optional[int] = None
    sort_order: Optional[int] = None

    class Config:
        from_attributes = True


class LexiconGroupOut(BaseModel):
    teaching_unit: str
    label: str
    count: int
    entries: List[CanonicalLexiconOut]


class CanonicalLexiconPatch(BaseModel):
    woccon: Optional[str] = None
    english: Optional[str] = None
    pos: Optional[str] = None
    pronunciation: Optional[str] = None
    source_url: Optional[str] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    source_page: Optional[int] = None
    source_page_end: Optional[int] = None
    source_excerpt: Optional[str] = None
    provenance_status: Optional[str] = None


class LexiconListResponse(BaseModel):
    items: List[CanonicalLexiconOut]
    total: int
    page: int
    page_size: int


class DriveLinkRequest(BaseModel):
    drive_url: str
    title: Optional[str] = None
    extraction_focus: Optional[str] = "general"
    grammar_lineage: Optional[str] = None


class ReextractRequest(BaseModel):
    extraction_focus: Optional[str] = None
    grammar_lineage: Optional[str] = None


class ReextractResponse(BaseModel):
    document_id: str
    status: str
    counts: dict
    locators_merged: dict


class BackfillCitationsResponse(BaseModel):
    sources_found: int
    dry_run: bool = False
    results: list
    export_paths: Optional[dict] = None


class VocabBaseSyncResponse(BaseModel):
    imported: int
    updated: int
    total: int
    document_id: str
    pronunciation: Optional[dict] = None


class CommitResponse(BaseModel):
    lexicon_committed: int
    rules_committed: int
    export_paths: dict
    reload_summary: dict


class AuditLogOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    user_id: Optional[str] = None
    user_display: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
