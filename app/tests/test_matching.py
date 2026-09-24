"""The matcher (app/matching), on fabricated rows only.

Every rule decided from the search-criteria trial is pinned here by one or
more cases, in both directions: what must be found and what must not.
tools/search_criteria_trial/verify_app_matcher.py proves the same code
against the full trial (real pages included).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.errors import StageError
from app.layout import group_rows, load_row_rules
from app.matching import (AMOUNT, CORRECTED, DATE, EXACT, PIN, POSSIBLE, Query, QueryError, load_matching_rules,
                          normalise_pin, parse_typed_amount, prepare_page, search_document, search_page)
from app.matching.rules import DEFAULT_MATCHING_RULES
from app.tests.fakes import word

RULES = load_matching_rules()
ROW_RULES = load_row_rules()


def page(*lines):
    """Fabricated page: each line is a list of (text, x) segments on one printed row."""
    words = []
    for n, line in enumerate(lines):
        for text, x in line:
            words.append(word(text, x, 40 * n, width=len(text) * 10, height=20))
    return prepare_page(group_rows(words, ROW_RULES), RULES)


def strengths(p, **query):
    return [h.strength for h in search_page(p, Query(**query), RULES)]


def amount_found(p, value):
    return EXACT in strengths(p, amount=Decimal(value))


class TypedAmountTests(unittest.TestCase):
    def test_accepted_forms(self):
        for text, want in [("1200", "1200.00"), ("1,200", "1200.00"), ("1 200.50", "1200.50"),
                           ("KSh 1,200", "1200.00"), ("1,200.5", "1200.50"), ("1200 Birr", "1200.00"),
                           ("250/=", "250.00"), ("0.75", "0.75")]:
            with self.subTest(text=text):
                self.assertEqual(parse_typed_amount(text, RULES), Decimal(want))

    def test_refused_forms_say_why_without_repeating_the_value(self):
        for text, reason in [("1.200", "ambiguous"), ("1200,50", "comma"), ("0", "greater than zero"),
                             ("-50", "greater than zero"), ("12a", "digits"), ("", "empty"), ("1.2.3", "digits")]:
            with self.subTest(text=text), self.assertRaises(QueryError) as ctx:
                parse_typed_amount(text, RULES)
            self.assertIn(reason, str(ctx.exception))
            if text:
                self.assertNotIn(text, str(ctx.exception))

    def test_result_is_an_exact_decimal(self):
        self.assertIsInstance(parse_typed_amount("0.1", RULES), Decimal)


class AmountTests(unittest.TestCase):
    def test_found_with_cents_in_every_printing_style(self):
        cases = {
            "1,200.00": [[("TOTAL", 0), ("1,200.00", 300)]],
            "521.21": [[("Untaxed Amount", 0), ("521.21KSh", 300)]],
            "200.00": [[("Ksh200.00 sent to", 0)]],
            "1,060.00": [[("FOOD / DRINKS", 0), ("1,060.00B", 300)]],
            "446.00": [[("balance is Ksh446.00.", 0)]],
            "5.00": [[("Transaction cost, Ksh5.00.Amount you can", 0)]],
            "1,130.45": [[("Quality A4 Paper", 0), ("*1.130.45", 300)]],
            "760.01": [[("TOTAL:", 0), ("±760.01", 300)]],
            "6,175.00": [[("ETB 6175.0 has been debited", 0)]],
            "2,406.94": [[("TOTAL", 0), ("2.406.94", 300)]],
        }
        for value, lines in cases.items():
            with self.subTest(value=value):
                self.assertTrue(amount_found(page(*lines), value.replace(",", "")))

    def test_found_without_cents_only_with_context(self):
        self.assertTrue(amount_found(page([("5,000 Birr", 0)]), "5000"))
        self.assertTrue(amount_found(page([("ETB500", 0)]), "500"))
        self.assertTrue(amount_found(page([("200/=", 0)]), "200"))
        self.assertTrue(amount_found(page([("TOTAL", 0), ("1,200", 300)]), "1200"))
        self.assertTrue(amount_found(page([("CASH", 0), ("1,200 KSh", 300)]), "1200"))

    def test_never_inside_or_beside_something_else(self):
        traps = {
            "500": [[("PIN P0500123Q", 0)]],
            "604": [[("604", 0)]],
            "9928": [[("RECEIPT NUMBER:", 0), ("9928", 300)]],
            "575": [[("Total", 0), ("575 CREDIT", 200)]],
            "14": [[("Total", 0), ("14 items", 200)]],
            "1100": [[("Qty 1", 0), ("100.00", 400)]],
            "2026": [[("DATE:12/08/2026", 0)]],
            "760.01": [[("TOTAL", 0), ("760.00", 300)]],
            "7600": [[("TOTAL", 0), ("760.00", 300)]],
        }
        for value, lines in traps.items():
            with self.subTest(value=value):
                self.assertFalse(amount_found(page(*lines), value))

    def test_split_value_joined_only_at_a_decimal_tail(self):
        self.assertTrue(amount_found(page([("TOTAL", 0), ("12,542", 300), (".00", 363)]), "12542"))
        self.assertFalse(amount_found(page([("1", 0), ("100.00", 14)]), "1100"))

    def test_faded_decimal_point_is_only_possible(self):
        p = page([("CASH T2 -UC", 0), ("430 00 KSh", 300)])
        self.assertEqual(strengths(p, amount=Decimal("430")), [POSSIBLE])

    def test_every_occurrence_is_reported(self):
        p = page([("1x", 0), ("760.00", 300)], [("TOTAL", 0), ("760.00", 300)], [("CASH", 0), ("760.00", 300)])
        self.assertEqual(len(search_page(p, Query(amount=Decimal("760")), RULES)), 3)


class DateTests(unittest.TestCase):
    def found(self, d, *lines):
        return EXACT in strengths(page(*lines), date=d)

    def test_printed_forms(self):
        d = date(2026, 8, 3)
        for line in (["DATE:03/08/2026"], ["Date:", "03/08/2026"], ["on 3/8/26 at"], ["03-08-2026 23:55:12"],
                     ["03.08.2026"], ["2026-08-03"], ["Mon 03 August 2026"], ["03-Aug-26"],
                     ["Date:03/08/2026193:33:31"], ["Aug 3, 2026"]):
            with self.subTest(line=line):
                self.assertTrue(self.found(d, [(t, i * 200) for i, t in enumerate(line)]))

    def test_near_misses_are_not_found(self):
        d = date(2026, 8, 3)
        for text in ("DATE:08/03/2026", "DATE:04/08/2026", "DATE:03/08/2025", "DATE:03/08/20261", "No:103/08/2026"):
            with self.subTest(text=text):
                self.assertFalse(self.found(d, [(text, 0)]))


class PinTests(unittest.TestCase):
    PIN_ = "A012345678Z"

    def result(self, text):
        return strengths(page([(text, 0)]), pin=self.PIN_)

    def test_exact_and_label_forms(self):
        for text in ("PIN: A012345678Z", "BUYER PIN:A012345678Z", "pin a012345678z", "PinA012345678Z"):
            with self.subTest(text=text):
                self.assertEqual(self.result(text), [EXACT])

    def test_ocr_corrections_count_but_say_so(self):
        for text in ("PIN: AO12345678Z", "PIN: A812345678Z", "PIN: A012345678" + "2", "PIN: A0123456782"):
            with self.subTest(text=text):
                self.assertEqual(self.result(text), [CORRECTED])

    def test_different_pins_are_not_found(self):
        for text in ("PIN: A012385678Z", "PIN: A912345648Z", "PIN: A012345678Z9", "PIN: QA012345678Z",
                     "REFA012345678Z"):
            with self.subTest(text=text):
                self.assertEqual(self.result(text), [])

    def test_typed_pin_is_normalised(self):
        self.assertEqual(normalise_pin(" a012 345 678z "), self.PIN_)


class DocumentTests(unittest.TestCase):
    def pages(self):
        return {
            1: page([("TOTAL", 0), ("500.00", 300)]),
            2: page([("DATE:12/08/2026", 0)], [("TOTAL", 0), ("760.00", 300)], [("PIN: A012345678Z", 0)]),
            3: page([("TOTAL", 0), ("760.00", 300)], [("DATE:12/08/2026", 0)]),
            4: page([("DATE:12/08/2026", 0)], [("TOTAL", 0), ("760.00", 300)], [("PIN: A012345678Z", 0)]),
        }

    def test_page_with_every_key_is_chosen_and_others_named(self):
        q = Query(date=date(2026, 8, 12), amount=Decimal("760"), pin="A012345678Z")
        result = search_document(self.pages(), q, RULES)
        self.assertEqual(result.complete_pages(), [2, 4])
        self.assertEqual(result.best_page, 2)
        self.assertEqual(result.pages_with(AMOUNT), [2, 3, 4])
        self.assertEqual(result.pages_with(PIN), [2, 4])

    def test_most_keys_wins_when_no_page_has_all(self):
        q = Query(date=date(2026, 8, 12), amount=Decimal("760"), pin="B999999999Z")
        self.assertEqual(search_document(self.pages(), q, RULES).best_page, 2)

    def test_nothing_found_gives_no_page(self):
        q = Query(amount=Decimal("1.23"))
        self.assertIsNone(search_document(self.pages(), q, RULES).best_page)

    def test_neighbours_come_from_the_same_row_only(self):
        p = page([("TOTAL", 0), ("KES", 150), ("760.00", 300)], [("NEXT ROW", 0)])
        hit = search_page(p, Query(amount=Decimal("760")), RULES)[0]
        self.assertEqual([s.text for s in hit.neighbours], ["TOTAL", "KES"])
        self.assertEqual([s.text for s in hit.segments], ["760.00"])

    def test_places_are_in_page_order(self):
        q = Query(amount=Decimal("760"))
        self.assertEqual([n for n, _ in search_document(self.pages(), q, RULES).places()], [2, 3, 4])

    def test_one_broken_page_does_not_stop_the_rest(self):
        pages = self.pages()
        pages[3].amounts = None  # corrupt one page
        result = search_document(pages, Query(amount=Decimal("760")), RULES)
        self.assertEqual(result.pages_with(AMOUNT), [2, 4])
        self.assertEqual([e.stage for e in result.errors], ["matching"])
        self.assertEqual(result.errors[0].page, 3)

    def test_query_keys(self):
        self.assertEqual(Query(pin="", amount=Decimal("1")).keys, (AMOUNT,))
        self.assertEqual(Query(date=date(2026, 1, 1), pin="X").keys, (DATE, PIN))


class RulesFileTests(unittest.TestCase):
    def test_invalid_rules_are_refused(self):
        good = json.loads(DEFAULT_MATCHING_RULES.read_text(encoding="utf-8"))
        cases = {"currency_words": [], "tax_code_letters": ["AB"], "pin_formats": ["LDX"],
                 "tail_join_gap_per_height": 0, "neighbours_each_side": -1,
                 "month_names": {"1": ["Jan"]}, "lookalike_pairs": [["0"]]}
        with tempfile.TemporaryDirectory() as folder:
            for key, value in cases.items():
                path = Path(folder) / "rules.json"
                path.write_text(json.dumps({**good, key: value}), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(StageError) as ctx:
                    load_matching_rules(path)
                self.assertEqual(ctx.exception.stage, "config")


if __name__ == "__main__":
    unittest.main()
