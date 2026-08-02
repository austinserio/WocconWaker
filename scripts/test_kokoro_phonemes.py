#!/usr/bin/env python3
"""Unit tests for Kokoro phoneme/stress pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panel_api.services.kokoro_phonemes import (  # noqa: E402
    _split_guide_syllables,
    prepare_kokoro_text_with_builder,
)


def test_split_syllables_stress_flags():
    parts = _split_guide_syllables("RUE-chay-ha")
    assert parts == [("RUE", True), ("chay", False), ("ha", False)]
    parts = _split_guide_syllables("cho-SAY")
    assert parts == [("cho", False), ("SAY", True)]


def test_prepare_kokoro_markdown_override():
    def fake(_guide):
        return "ɹˈu ʧA hɑ"

    out = prepare_kokoro_text_with_builder("RUE-chay-ha", phoneme_builder=fake)
    assert out == "[RUE-chay-ha](/ɹˈu ʧA hɑ/)"


def test_or_alternative_uses_first_branch():
    parts = _split_guide_syllables("(AY-JAH-OH) or (YAH)")
    assert parts[0][0] == "AY"


def main() -> int:
    test_split_syllables_stress_flags()
    test_prepare_kokoro_markdown_override()
    test_or_alternative_uses_first_branch()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
