"""Shared loaders and normalization for cognate/correspondence pipelines."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_COGNATES = ROOT / "woccon_language/cognate_sets/rudes_carter_seed.json"
DEFAULT_REGISTRY = ROOT / "woccon_language/correspondences/registry.json"
DEFAULT_ALIGNMENTS = ROOT / "woccon_language/cognate_sets/alignments.json"
DEFAULT_DICTIONARY = ROOT / "woccon_language/dictionary.json"


def norm_form(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^\w]", "", (s or "").lower())


def norm_lawson(s: Optional[str]) -> str:
    return norm_form(s)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cognate_sets(path: Path = DEFAULT_COGNATES) -> List[Dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, list):
        return data
    return data.get("sets") or []


def load_registry(path: Path = DEFAULT_REGISTRY) -> Dict[str, Any]:
    return load_json(path)


def registry_rules(envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
    return envelope.get("rules") or []


def load_alignments(path: Path = DEFAULT_ALIGNMENTS) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "alignments": []}
    return load_json(path)


def load_dictionary(path: Path = DEFAULT_DICTIONARY) -> List[Dict[str, Any]]:
    data = load_json(path)
    return data.get("lexicon") or []


def effective_lawson(row: Dict[str, Any]) -> Optional[str]:
    return row.get("lawson_form_corrected") or row.get("lawson_form")


def app1_certain(cognates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        c
        for c in cognates
        if c.get("rudes_appendix") == 1
        and c.get("evidence_tier") == "certain"
        and c.get("woccon_reconstituted")
        and c.get("catawba_form")
        and not str(c.get("catawba_form", "")).startswith("|")
    ]
