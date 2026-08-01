"""Persist raw Drive sources and processed text for bulk ingest."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("drive_ingest_archive")

MANIFEST_FILENAME = "manifest.json"
GOOGLE_DOCS_MIME = "application/vnd.google-apps.document"
PDF_MIME = "application/pdf"


def sources_dir() -> str:
    return os.environ.get("INGEST_SOURCES_DIR", "data/ingest_sources")


def text_cache_dir() -> str:
    return os.environ.get("INGEST_TEXT_CACHE_DIR", "data/ingest_text_cache")


def _sanitize_modified(modified_time: str) -> str:
    return re.sub(r"[^\w\-]", "_", modified_time or "")[:64]


def _archive_basename(file_id: str, modified_time: str) -> str:
    return f"{file_id}_{_sanitize_modified(modified_time)}"


def archive_local_name(file_id: str, modified_time: str, mime_type: str) -> str:
    ext = ".txt" if mime_type == GOOGLE_DOCS_MIME else ".pdf"
    return f"{_archive_basename(file_id, modified_time)}{ext}"


def _manifest_path() -> str:
    return os.path.join(sources_dir(), MANIFEST_FILENAME)


def _text_cache_path(file_id: str, modified_time: str) -> str:
    return os.path.join(text_cache_dir(), f"{_archive_basename(file_id, modified_time)}.json")


def load_manifest() -> Dict[str, Any]:
    path = _manifest_path()
    if not os.path.isfile(path):
        return {"entries": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            return data
        if isinstance(data, dict):
            return {"entries": data}
    except Exception as e:
        log.warning("Could not load manifest %s: %s", path, e)
    return {"entries": {}}


def save_manifest_entry(entry: Dict[str, Any]) -> None:
    os.makedirs(sources_dir(), exist_ok=True)
    manifest = load_manifest()
    entries = manifest.setdefault("entries", {})
    file_id = entry.get("file_id")
    if not file_id:
        return
    entries[file_id] = entry
    with open(_manifest_path(), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def get_manifest_entry(file_id: str, modified_time: str) -> Optional[Dict[str, Any]]:
    entry = load_manifest().get("entries", {}).get(file_id)
    if not entry:
        return None
    if entry.get("modified_time") != modified_time:
        return None
    local_file = entry.get("local_file")
    if not local_file:
        return None
    full = os.path.join(sources_dir(), local_file)
    if not os.path.isfile(full):
        return None
    return entry


def read_archived_bytes(file_id: str, modified_time: str) -> Optional[bytes]:
    entry = get_manifest_entry(file_id, modified_time)
    if not entry:
        return None
    path = os.path.join(sources_dir(), entry["local_file"])
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        log.warning("Could not read archived source %s: %s", path, e)
        return None


def archive_source(
    *,
    file_id: str,
    modified_time: str,
    path: str,
    mime_type: str,
    data: bytes,
    source_url: Optional[str] = None,
) -> str:
    os.makedirs(sources_dir(), exist_ok=True)
    local_file = archive_local_name(file_id, modified_time, mime_type)
    dest = os.path.join(sources_dir(), local_file)
    with open(dest, "wb") as f:
        f.write(data)
    entry = {
        "file_id": file_id,
        "modified_time": modified_time,
        "path": path,
        "source_url": source_url or f"https://drive.google.com/file/d/{file_id}/view",
        "local_file": local_file,
        "mime_type": mime_type,
        "sha256": hashlib.sha256(data).hexdigest(),
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    save_manifest_entry(entry)
    log.info("Archived source %s -> %s", path, local_file)
    return local_file


def load_text_cache(file_id: str, modified_time: str) -> Optional[Dict[str, Any]]:
    path = _text_cache_path(file_id, modified_time)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("file_id") == file_id and data.get("modified_time") == modified_time:
            return data
    except Exception as e:
        log.warning("Could not load text cache %s: %s", path, e)
    return None


def save_text_cache(
    *,
    file_id: str,
    modified_time: str,
    path: str,
    text: str,
    text_method: str,
) -> None:
    os.makedirs(text_cache_dir(), exist_ok=True)
    payload = {
        "file_id": file_id,
        "modified_time": modified_time,
        "path": path,
        "text": text,
        "text_method": text_method,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_path = _text_cache_path(file_id, modified_time)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    log.info("Saved text cache for %s (%d chars, %s)", path, len(text or ""), text_method)
