#!/usr/bin/env python3
"""Tests for check_rule_topic_coverage keyword matching."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_rule_topic_coverage import build_report, load_registry, topic_matches  # noqa: E402

REGISTRY = ROOT / "data" / "rule_topic_registry.json"

RESURRECTING_SNIPPETS = {
    "grammar_notes": [
        "Woccon has four independent modal modes: participial, imperative, interrogative, and independent modal suffix *-re·*.",
        "Alienable possession is marked with a suffix; inalienable possession uses a different pattern including *-wa·*.",
        "The twelve-vowel inventory includes short oral, long oral, and nasal series as in *wátupi*.",
        "Nasal vowels correspond to long oral vowels in cognate forms; *r̄ is defective word-initially.",
        "Full-root reduplication marks frequentive and intensive aspect.",
    ],
    "pronunciation_notes": [
        "Regressive nasal assimilation affects sequences like esaw and saraw.",
    ],
    "source_path": "Articles/Resurrecting Coastal Catawban.pdf",
}


class RuleTopicCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_registry(REGISTRY)

    def test_modal_modes_keyword(self) -> None:
        topic = self.registry["topics"]["modal_modes"]
        self.assertTrue(topic_matches(RESURRECTING_SNIPPETS["grammar_notes"][0], topic))

    def test_possession_keyword(self) -> None:
        topic = self.registry["topics"]["possession"]
        self.assertTrue(topic_matches(RESURRECTING_SNIPPETS["grammar_notes"][1], topic))

    def test_vowel_inventory_keyword(self) -> None:
        topic = self.registry["topics"]["vowel_inventory"]
        self.assertTrue(topic_matches(RESURRECTING_SNIPPETS["grammar_notes"][2], topic))

    def test_resurrecting_tier_a_mostly_covered(self) -> None:
        report = build_report(
            registry=self.registry,
            document_filter="Resurrecting",
            staging=None,
            live={
                "grammar": [
                    {"content": t, "citation": {"document_title": "Resurrecting Coastal Catawban"}}
                    for t in RESURRECTING_SNIPPETS["grammar_notes"]
                ],
                "pronunciation": [
                    {"content": t, "citation": {"document_title": "Resurrecting"}}
                    for t in RESURRECTING_SNIPPETS["pronunciation_notes"]
                ],
            },
        )
        tier_a = report["live"]["tier_a"]
        self.assertGreaterEqual(tier_a["covered"], 5)
        self.assertIn("compound_syntax", tier_a["gaps"])

    def test_staging_file_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Articles_Resurrecting.pdf.json"
            p.write_text(json.dumps(RESURRECTING_SNIPPETS), encoding="utf-8")
            report = build_report(
                registry=self.registry,
                document_filter="Resurrecting",
                staging=p,
            )
            self.assertIn("staging", report)
            self.assertGreaterEqual(report["staging"]["tier_a"]["covered"], 5)


if __name__ == "__main__":
    unittest.main()
