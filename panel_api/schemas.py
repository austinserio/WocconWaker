"""Pydantic schemas for panel API."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "reviewer"


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

    class Config:
        from_attributes = True


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
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


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
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PendingRulePatch(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    reviewer_notes: Optional[str] = None
    grammar_domain: Optional[str] = None
    pos_tag: Optional[str] = None
    construction_type: Optional[str] = None


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


class CanonicalLexiconOut(BaseModel):
    id: str
    woccon: str
    english: str
    pos: str
    pronunciation: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    teaching_unit: Optional[str] = None
    word_class: Optional[str] = None
    lesson_band: Optional[str] = None

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


class LexiconListResponse(BaseModel):
    items: List[CanonicalLexiconOut]
    total: int
    page: int
    page_size: int


class DriveLinkRequest(BaseModel):
    drive_url: str
    title: Optional[str] = None


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
    created_at: datetime

    class Config:
        from_attributes = True
