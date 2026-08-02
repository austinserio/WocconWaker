"""SQLAlchemy models and session factory."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from panel_api.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="worker")  # admin, worker, member
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserInvitation(Base):
    __tablename__ = "user_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64))
    invited_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    title: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(32))  # upload, drive_link, drive_folder
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    drive_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    short_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pub_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    container_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(256), nullable=True)
    place: Mapped[str | None] = mapped_column(String(128), nullable=True)
    citation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vocab_base: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    text_extraction_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    extraction_focus: Mapped[str] = mapped_column(String(32), default="general")
    grammar_lineage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    uploader: Mapped["User | None"] = relationship("User")
    pending_lexicon: Mapped[list["PendingLexicon"]] = relationship(back_populates="source_document")
    pending_rules: Mapped[list["PendingRule"]] = relationship(back_populates="source_document")


class PendingLexicon(Base):
    __tablename__ = "pending_lexicon"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_documents.id"), nullable=True
    )
    woccon: Mapped[str] = mapped_column(String(512))
    english: Mapped[str] = mapped_column(String(1024))
    pos: Mapped[str] = mapped_column(String(64), default="unknown")
    pronunciation: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    duplicate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    base_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_match_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    match_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    teaching_unit: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    word_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lesson_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    source_document: Mapped["SourceDocument | None"] = relationship(back_populates="pending_lexicon")


class PendingRule(Base):
    __tablename__ = "pending_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_documents.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(32))  # grammar, pronunciation, cultural
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    duplicate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grammar_domain: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    pos_tag: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    construction_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    grammar_lineage: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    rule_kind: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    correspondence_status: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    source_document: Mapped["SourceDocument | None"] = relationship(back_populates="pending_rules")


class CanonicalLexicon(Base):
    __tablename__ = "canonical_lexicon"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    woccon: Mapped[str] = mapped_column(String(512), index=True)
    english: Mapped[str] = mapped_column(String(1024))
    pos: Mapped[str] = mapped_column(String(64), default="unknown")
    pronunciation: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_documents.id"), nullable=True
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    woccon_normalized: Mapped[str] = mapped_column(String(512), index=True)
    teaching_unit: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    word_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lesson_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_base_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    base_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    base_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_match_method: Mapped[str | None] = mapped_column(String(32), nullable=True)


class CanonicalRule(Base):
    __tablename__ = "canonical_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    category: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    legacy_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    content_normalized: Mapped[str] = mapped_column(Text, default="")
    grammar_domain: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    pos_tag: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    construction_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    grammar_lineage: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    rule_kind: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    correspondence_status: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance_status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class CognateSet(Base):
    __tablename__ = "cognate_sets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gloss: Mapped[str] = mapped_column(String(512), index=True)
    lawson_form: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lawson_form_corrected: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lawson_gloss: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    woccon_reconstituted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    catawba_form: Mapped[str | None] = mapped_column(String(512), nullable=True)
    catawba_dialect: Mapped[str | None] = mapped_column(String(32), nullable=True)
    proto_siouan: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evidence_tier: Mapped[str] = mapped_column(String(32), index=True)
    rudes_appendix: Mapped[int] = mapped_column(Integer, index=True)
    rudes_item: Mapped[int] = mapped_column(Integer)
    citation_short: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_lexicon_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("canonical_lexicon.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    canonical_lexicon: Mapped["CanonicalLexicon | None"] = relationship("CanonicalLexicon")
    rule_examples: Mapped[list["CognateRuleExample"]] = relationship(
        back_populates="cognate_set", cascade="all, delete-orphan"
    )


class CorrespondenceRule(Base):
    __tablename__ = "correspondence_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_kind: Mapped[str] = mapped_column(String(32), index=True)
    lhs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rhs: Mapped[str | None] = mapped_column(String(64), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correspondence_status: Mapped[str] = mapped_column(String(16), index=True)
    grammar_lineage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    examples: Mapped[list["CognateRuleExample"]] = relationship(
        back_populates="correspondence_rule", cascade="all, delete-orphan"
    )


class CognateRuleExample(Base):
    __tablename__ = "cognate_rule_examples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    cognate_set_id: Mapped[str] = mapped_column(String(64), ForeignKey("cognate_sets.id"), index=True)
    correspondence_rule_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("correspondence_rules.id"), index=True
    )
    alignment_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    cognate_set: Mapped["CognateSet"] = relationship(back_populates="rule_examples")
    correspondence_rule: Mapped["CorrespondenceRule"] = relationship(back_populates="examples")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, connect_args=connect_args)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def _ensure_classification_columns() -> None:
    """Add classification columns to existing DBs created before migration 002."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    new_cols_rules = [
        ("grammar_domain", "VARCHAR(32)"),
        ("pos_tag", "VARCHAR(32)"),
        ("construction_type", "VARCHAR(32)"),
    ]
    new_cols_lexicon = [
        ("teaching_unit", "VARCHAR(32)"),
        ("word_class", "VARCHAR(32)"),
        ("lesson_band", "VARCHAR(32)"),
    ]
    with engine.connect() as conn:
        for table in ("pending_rules", "canonical_rules"):
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, typ in new_cols_rules:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
        for table in ("pending_lexicon", "canonical_lexicon"):
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, typ in new_cols_lexicon:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
            conn.commit()


def _ensure_provenance_columns() -> None:
    """Add provenance columns to existing DBs created before migration 004."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    doc_cols = [
        ("short_title", "VARCHAR(256)"),
        ("authors", "TEXT"),
        ("year", "VARCHAR(16)"),
        ("pub_title", "VARCHAR(512)"),
        ("container_title", "VARCHAR(512)"),
        ("publisher", "VARCHAR(256)"),
        ("place", "VARCHAR(128)"),
        ("citation_text", "TEXT"),
        ("is_seed", "BOOLEAN DEFAULT 0"),
    ]
    locator_cols = [
        ("source_page", "INTEGER"),
        ("source_page_end", "INTEGER"),
        ("source_excerpt", "TEXT"),
        ("source_chunk_index", "INTEGER"),
        ("provenance_status", "VARCHAR(16)"),
    ]
    with engine.connect() as conn:
        if "source_documents" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("source_documents")}
            for col, typ in doc_cols:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE source_documents ADD COLUMN {col} {typ}"))
        for table in ("pending_lexicon", "pending_rules", "canonical_lexicon", "canonical_rules"):
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, typ in locator_cols:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
            if table == "canonical_lexicon" and "source_document_id" not in existing:
                conn.execute(text("ALTER TABLE canonical_lexicon ADD COLUMN source_document_id VARCHAR(36)"))
        conn.commit()


def _ensure_progress_columns() -> None:
    """Add extraction progress columns to source_documents."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    cols = [
        ("progress_pct", "INTEGER"),
        ("progress_message", "VARCHAR(256)"),
    ]
    with engine.connect() as conn:
        if "source_documents" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("source_documents")}
        for col, typ in cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE source_documents ADD COLUMN {col} {typ}"))
        conn.commit()


def _ensure_vocab_base_columns() -> None:
    """Add vocab-base columns to existing DBs created before migration 007."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    with engine.connect() as conn:
        if "source_documents" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("source_documents")}
            if "is_vocab_base" not in existing:
                conn.execute(text("ALTER TABLE source_documents ADD COLUMN is_vocab_base BOOLEAN DEFAULT 0"))
        for table, cols in (
            (
                "canonical_lexicon",
                [
                    ("is_base_entry", "BOOLEAN DEFAULT 0"),
                    ("base_entry_id", "VARCHAR(36)"),
                    ("base_match_score", "FLOAT"),
                    ("base_match_method", "VARCHAR(32)"),
                ],
            ),
            (
                "pending_lexicon",
                [
                    ("base_entry_id", "VARCHAR(36)"),
                    ("base_match_score", "FLOAT"),
                    ("base_match_method", "VARCHAR(32)"),
                    ("match_status", "VARCHAR(16)"),
                ],
            ),
        ):
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, typ in cols:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
        conn.commit()


def _ensure_text_extraction_method_column() -> None:
    """Add text_extraction_method to source_documents."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    with engine.connect() as conn:
        if "source_documents" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("source_documents")}
        if "text_extraction_method" not in existing:
            conn.execute(text("ALTER TABLE source_documents ADD COLUMN text_extraction_method VARCHAR(16)"))
        conn.commit()


def _ensure_extraction_config_columns() -> None:
    """Add extraction_focus / grammar_lineage to source_documents and rules tables."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    with engine.connect() as conn:
        if "source_documents" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("source_documents")}
            if "extraction_focus" not in existing:
                conn.execute(
                    text("ALTER TABLE source_documents ADD COLUMN extraction_focus VARCHAR(32) DEFAULT 'general'")
                )
            if "grammar_lineage" not in existing:
                conn.execute(text("ALTER TABLE source_documents ADD COLUMN grammar_lineage VARCHAR(32)"))
        for table in ("pending_rules", "canonical_rules"):
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if "grammar_lineage" not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN grammar_lineage VARCHAR(32)"))
        conn.commit()


def _ensure_content_hash_column() -> None:
    """Add content_hash to source_documents for upload deduplication."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    with engine.connect() as conn:
        if "source_documents" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("source_documents")}
        if "content_hash" not in existing:
            conn.execute(text("ALTER TABLE source_documents ADD COLUMN content_hash VARCHAR(64)"))
        conn.commit()


def _ensure_users_auth_schema() -> None:
    """Add user profile columns, invitation/reset tables, and role slug migration."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    with engine.connect() as conn:
        if "users" in insp.get_table_names():
            existing = {c["name"] for c in insp.get_columns("users")}
            for col, typ in (
                ("first_name", "VARCHAR(128)"),
                ("last_name", "VARCHAR(128)"),
                ("is_active", "BOOLEAN DEFAULT 1"),
            ):
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typ}"))
            conn.execute(text("UPDATE users SET role = 'worker' WHERE role = 'reviewer'"))
            conn.execute(text("UPDATE users SET role = 'member' WHERE role = 'viewer'"))
        if "user_invitations" not in insp.get_table_names():
            conn.execute(
                text(
                    """
                    CREATE TABLE user_invitations (
                        id VARCHAR(36) PRIMARY KEY,
                        email VARCHAR(255) NOT NULL,
                        role VARCHAR(32) NOT NULL,
                        token_hash VARCHAR(64) NOT NULL,
                        invited_by VARCHAR(36),
                        expires_at DATETIME NOT NULL,
                        accepted_at DATETIME,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX ix_user_invitations_email ON user_invitations (email)"))
        if "password_reset_tokens" not in insp.get_table_names():
            conn.execute(
                text(
                    """
                    CREATE TABLE password_reset_tokens (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL,
                        token_hash VARCHAR(64) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        used_at DATETIME,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        conn.commit()


def _ensure_rule_kind_columns() -> None:
    """Add rule_kind / correspondence_status to rules tables."""
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    cols = [
        ("rule_kind", "VARCHAR(32)"),
        ("correspondence_status", "VARCHAR(16)"),
    ]
    with engine.connect() as conn:
        for table in ("pending_rules", "canonical_rules"):
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, typ in cols:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
        conn.commit()


def _ensure_comparative_tables() -> None:
    """Create comparative tables on existing DBs (Phase 5)."""
    Base.metadata.create_all(
        bind=get_engine(),
        tables=[
            CognateSet.__table__,
            CorrespondenceRule.__table__,
            CognateRuleExample.__table__,
        ],
    )


def init_db() -> None:
    """Create tables if missing."""
    settings = get_settings()
    import os

    os.makedirs(settings.woccon_upload_dir, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite:///", "")
        if db_path and not db_path.startswith(":"):
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    Base.metadata.create_all(bind=get_engine())
    _ensure_classification_columns()
    _ensure_provenance_columns()
    _ensure_progress_columns()
    _ensure_text_extraction_method_column()
    _ensure_vocab_base_columns()
    _ensure_extraction_config_columns()
    _ensure_content_hash_column()
    _ensure_rule_kind_columns()
    _ensure_users_auth_schema()
    _ensure_comparative_tables()


def get_db():
    """FastAPI dependency."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
