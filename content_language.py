"""Classify Drive source documents by the language of the material they contain.

The corpus holds Woccon primary sources next to Catawba comparative sources. Catawba is a
related but distinct language: its vocabulary is *evidence for* reconstructing Woccon and must
never become Woccon vocabulary. Nothing in the pipeline tracked language before, so a Catawba
word list dropped into the Drive folder would have been handed to the Woccon extraction prompt
and merged into `dictionary_unified.json` as though Lawson had recorded it.

Classification is by Drive **folder**, matched on whole path segments. Substring matching would
be actively dangerous here: `Articles/Resurrecting Coastal Catawban - ... Woccon Language` is a
Woccon source whose title contains "Catawba".
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

WOCCON = "woccon"
CATAWBA = "catawba"
CONTEXT = "context"

CONTENT_LANGUAGES = (WOCCON, CATAWBA, CONTEXT)

# Folders whose contents are Catawba-language material (comparative evidence only).
DEFAULT_CATAWBA_FOLDERS = ("catawba language",)
# Folders holding non-linguistic material: tribal history, governance, news, business.
DEFAULT_CONTEXT_FOLDERS = ("catawba nation - context",)


def _folders_from_env(var: str, default: Iterable[str]) -> tuple:
    raw = (os.getenv(var) or "").strip()
    if not raw:
        return tuple(default)
    return tuple(p.strip().lower() for p in raw.split("|") if p.strip())


def _segments(path: Optional[str]) -> list:
    return [seg.strip().lower() for seg in (path or "").replace("\\", "/").split("/") if seg.strip()]


def classify_path(path: Optional[str]) -> str:
    """Return the content language for a Drive path such as "Catawba Language/Speck-...pdf"."""
    segs = _segments(path)
    if not segs:
        return WOCCON
    # The final segment is the filename; only parent folders decide language.
    folders = set(segs[:-1]) if len(segs) > 1 else set()
    if folders & set(_folders_from_env("CATAWBA_FOLDER_NAMES", DEFAULT_CATAWBA_FOLDERS)):
        return CATAWBA
    if folders & set(_folders_from_env("CONTEXT_FOLDER_NAMES", DEFAULT_CONTEXT_FOLDERS)):
        return CONTEXT
    return WOCCON


def allows_woccon_lexicon(language: Optional[str]) -> bool:
    """Only Woccon sources may contribute entries to the Woccon lexicon."""
    return (language or WOCCON) == WOCCON


def is_woccon_source(path: Optional[str]) -> bool:
    return allows_woccon_lexicon(classify_path(path))


def staging_dir_for(language: Optional[str], woccon_dir: str) -> str:
    """Catawba extractions are staged separately so they can never be merged by mistake."""
    if (language or WOCCON) == CATAWBA:
        return os.getenv("CATAWBA_STAGING_DIR") or os.path.join(
            os.path.dirname(woccon_dir.rstrip("/")) or ".", "catawba_staging"
        )
    return woccon_dir
