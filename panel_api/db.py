"""SQLAlchemy models and session factory."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
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
    role: Mapped[str] = mapped_column(String(32), default="reviewer")  # admin, reviewer, viewer
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
    teaching_unit: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    word_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lesson_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
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
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    woccon_normalized: Mapped[str] = mapped_column(String(512), index=True)
    teaching_unit: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    word_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lesson_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)


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


def get_db():
    """FastAPI dependency."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
