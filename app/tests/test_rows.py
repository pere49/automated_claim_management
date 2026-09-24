"""Grouping OCR segments into printed rows (app/layout/rows.py)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.errors import StageError
from app.layout import RowRules, group_rows, load_row_rules, ungrouped_rows
from app.tests.fakes import word

RULES = RowRules(same_row_offset_per_height=0.5, max_overlap_per_height=0.5,
                 wide_gap_per_height=1.5, wide_gap_text="    ")


def texts(rows):
    return [r.text for r in rows]


class GroupRowsTests(unittest.TestCase):
    def test_segments_on_one_line_join_left_to_right(self):
        words = [word(".00", 150, 11), word("TOTAL", 10, 10), word("12,542", 100, 10)]
        self.assertEqual(texts(group_rows(words, RULES)), ["TOTAL    12,542 .00"])

    def test_separate_lines_stay_separate_top_to_bottom(self):
        words = [word("second", 10, 40), word("first", 10, 10)]
        self.assertEqual(texts(group_rows(words, RULES)), ["first", "second"])

    def test_small_vertical_wobble_still_same_row(self):
        words = [word("A", 10, 10), word("B", 60, 14)]  # centres 4 px apart, height 10
        self.assertEqual(len(group_rows(words, RULES)), 1)

    def test_value_between_two_lines_does_not_chain_them(self):
        # The real case from yem_p2.pdf: "9928" printed between "RECEIPT NUMBER:" and "DATE:...".
        # Centres 3 px apart each (height 10): without the overlap rule "9928" joins the first
        # line, the row's centre drifts down, and "DATE:" then joins it too.
        words = [word("RECEIPT NUMBER:", 10, 100, width=120), word("9928", 200, 103),
                 word("DATE:11/08/2026", 10, 106, width=120)]
        rows = texts(group_rows(words, RULES))
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(r.startswith("RECEIPT NUMBER:") for r in rows))
        self.assertIn("DATE:11/08/2026", rows)

    def test_close_segments_joined_with_single_space(self):
        words = [word("Food", 10, 10, width=40), word("court", 55, 10, width=40)]
        self.assertEqual(texts(group_rows(words, RULES)), ["Food court"])

    def test_empty_input(self):
        self.assertEqual(group_rows([], RULES), [])

    def test_keeps_original_segment_for_later_highlighting(self):
        original = word("TOTAL", 10, 10)
        self.assertIs(group_rows([original], RULES)[0].segments[0].source, original)

    def test_unusable_box_raises_layout_error(self):
        bad = SimpleNamespace(text="x", box=[["a", "b"]])
        with self.assertRaises(StageError) as ctx:
            group_rows([word("ok", 0, 0), bad], RULES)
        self.assertEqual(ctx.exception.stage, "layout")
        self.assertIn("segment 2", ctx.exception.summary)

    def test_ungrouped_fallback_keeps_every_segment(self):
        words = [word("b", 10, 40), word("a", 10, 10)]
        self.assertEqual(texts(ungrouped_rows(words)), ["b", "a"])


class LoadRowRulesTests(unittest.TestCase):
    def test_shipped_rules_load(self):
        rules = load_row_rules()
        self.assertGreater(rules.same_row_offset_per_height, 0)

    def test_invalid_values_rejected(self):
        good = {"same_row_offset_per_height": 0.5, "max_overlap_per_height": 0.5,
                "wide_gap_per_height": 1.5, "wide_gap_text": "  "}
        cases = {"same_row_offset_per_height": 0, "max_overlap_per_height": -1, "wide_gap_text": ""}
        with tempfile.TemporaryDirectory() as folder:
            for key, value in cases.items():
                path = Path(folder) / "rules.json"
                path.write_text(json.dumps({**good, key: value}), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(StageError) as ctx:
                    load_row_rules(path)
                self.assertIn(key, ctx.exception.summary)


if __name__ == "__main__":
    unittest.main()
