"""Normalize community pronunciation guides for storage and display."""
import re


def normalize_pronunciation(value: str | None) -> str | None:
    """Strip wrapping parentheses, slashes, and whitespace from a pronunciation guide."""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    # Remove outer parens: (rue-sa-may) -> rue-sa-may
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    # Remove IPA-style slashes: /foo/ -> foo
    if s.startswith("/") and s.endswith("/") and len(s) > 2:
        s = s[1:-1].strip()
    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s or None
