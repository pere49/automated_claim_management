"""app/checking: pairing claimed amounts with receipt pages (synthetic claims and receipts only).

A receipt page is built from lines of text; "|" separates segments on a line
(so a label and its value can be separate segments, as OCR returns them).
Colours follow rule B (D34): red = no valid receipt, yellow = a receipt whose
date or amount does not match.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from datetime import date, datetime
from decimal import Decimal

from app.checking import (ALREADY_PAIRED, AMOUNT_UNREADABLE, CAUTION, DATE_CONTRADICTED, DATE_MISSING, DOUBLE_CLAIM,
                          GREEN, GREY, NO_DATE, NO_PIN, NOT_FOUND, NOT_TOTAL, OTHER_BUYER, P_AMOUNT, P_DATE,
                          P_NO_RECEIPT, P_OTHER_BUYER, P_PIN, P_REPEATED, P_UNREADABLE, PAIRED, PASS, POSSIBLE_ONLY,
                          RED, REVIEW, YELLOW, analyse_receipts, check_claim, decide, find_all, load_checking_rules)
from app.claims import load_claim_rules
from app.claims.sheet_builder import build_sheet
from app.layout import group_rows, load_row_rules
from app.matching import AMOUNT, DATE, load_matching_rules, prepare_page, search_page, Query
from tests.claim_fixtures import form_grid
from tests.fakes import FAKE_PIN, word

TODAY = date(2026, 9, 24)
MATCHING, CHECKING, CLAIMS, ROWS = load_matching_rules(), load_checking_rules(), load_claim_rules(), load_row_rules()


def receipt(*lines: str):
    words = []
    for r, line in enumerate(lines):
        left = 10.0
        for part in line.split("|"):
            text = part.strip()
            width = 9.0 * len(text)
            words.append(word(text, left, 20 + r * 30, width=width, height=12))
            left += width + 30
    return prepare_page(group_rows(words, ROWS), MATCHING)


def sheet(entries, rate=None, total=True):
    grid = form_grid(entries, rate=rate, total=total)
    return build_sheet("W", grid, list(range(1, len(grid) + 1)), CLAIMS, TODAY)


def check(claim, pages, pin=FAKE_PIN, pin_required=None, unread=()):
    facts = analyse_receipts(dict(enumerate(pages, 1)), len(pages) + len(unread), list(unread), pin, CHECKING, MATCHING)
    return check_claim(claim, facts, pin, pin_required, MATCHING)


def slip(amount: str, day: str, *, pin: bool = True, extra: tuple[str, ...] = ()) -> object:
    lines = ["SHOP LTD", f"DATE: {day}", f"TOTAL | {amount}", *extra]
    if pin:
        lines.append(f"Buyer PIN: {FAKE_PIN}")
    return receipt(*lines)


AUG10, AUG11, AUG14 = datetime(2026, 8, 10), datetime(2026, 8, 11), datetime(2026, 8, 14)


class PairingTests(unittest.TestCase):
    def test_amount_date_and_pin_on_one_page_is_green(self):
        result = check(sheet([(AUG10, "Meals", {"Dinner": 750})]), [slip("750.00", "10/08/2026")])
        r = result.items[0]
        self.assertEqual((r.status, r.colour, r.page, r.reason), (PASS, GREEN, 1, PAIRED))
        self.assertTrue(result.pin_required)
        self.assertEqual(result.pin.colour, GREEN)
        self.assertEqual({h.key for h in r.hits}, {"amount", "date", "pin"})
        self.assertEqual((r.problems, result.pages[1].colour, result.pages[1].lines), ((), GREEN, ("✓",)))

    def test_a_paired_page_leaves_every_later_search(self):
        claim = sheet([(AUG10, "Meals", {"Dinner": 750}), (AUG10, "Meals", {"Dinner": 750})])
        result = check(claim, [slip("750.00", "10/08/2026")])
        self.assertEqual([r.colour for r in result.items], [GREEN, RED])
        second = result.items[1]
        self.assertEqual((second.reason, second.problems, second.page), (ALREADY_PAIRED, (P_NO_RECEIPT,), None))
        self.assertIn("already paired with row 7", second.detail)

    def test_exact_amounts_are_paired_before_cents_dropped_ones(self):
        claim = sheet([(AUG10, "a", {"Lunch": 500}), (AUG10, "b", {"Dinner": 500.34})])
        result = check(claim, [slip("500.34", "10/08/2026"), slip("500.77", "10/08/2026")])
        self.assertEqual([(r.colour, r.page) for r in result.items], [(GREEN, 2), (GREEN, 1)])
        self.assertIn("cents dropped", result.items[0].detail)

    def test_cents_dropped_counts_but_never_upward(self):
        dropped = check(sheet([(AUG10, "a", {"Lunch": 500})]), [slip("500.34", "10/08/2026")])
        self.assertEqual(dropped.items[0].colour, GREEN)
        upward = check(sheet([(AUG10, "a", {"Lunch": 501})]), [slip("500.60", "10/08/2026")])
        r = upward.items[0]
        self.assertEqual((r.colour, r.reason, r.problems, r.page), (YELLOW, NOT_FOUND, (P_AMOUNT,), 1))
        self.assertEqual(r.lines, ("Amount 500.60 ≠ 501.00",), "linked by its date, the only free page with it")

    def test_the_amount_must_be_printed_as_the_total_not_as_cash_handed_over(self):
        page = slip("2,406.94", "03/08/2026", extra=("CASH | 3,000.00", "CHANGE | 593.06"))
        alone = check(sheet([(datetime(2026, 8, 3), "a", {"Other": 3000})]), [page])
        r = alone.items[0]
        self.assertEqual((r.colour, r.reason, r.problems), (YELLOW, NOT_TOTAL, (P_AMOUNT,)))
        self.assertEqual(r.lines, ("Amount 2,406.94 ≠ 3,000.00",))
        claim = sheet([(datetime(2026, 8, 3), "a", {"Other": 3000}), (datetime(2026, 8, 3), "b", {"Other": 2406.94})])
        both = check(claim, [page])
        self.assertEqual([(r.colour, r.problems) for r in both.items], [(RED, (P_NO_RECEIPT,)), (GREEN, ())])

    def test_a_total_label_standing_above_its_value_counts(self):
        page = receipt("telebirr", "Invoice No. | Payment date | Settled Amount",
                       "ABC123XYZ | 10-08-2026 12:30:00 | 460 Birr", "Total Paid Amount | 462 Birr")
        result = check(sheet([(AUG10, "Taxi", {"Travel": 460})]), [page], pin=None)
        self.assertEqual(result.items[0].colour, GREEN)

    def test_a_date_off_by_a_day_is_yellow_and_says_both_dates(self):
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [slip("750.00", "09/08/2026")])
        r = result.items[0]
        self.assertEqual((r.colour, r.reason, r.page, r.problems), (YELLOW, DATE_MISSING, 1, (P_DATE,)))
        self.assertIn("one day earlier", r.detail)
        self.assertEqual(result.pages[1].lines, ("Date 09 Aug ≠ 10 Aug",))

    def test_a_faded_decimal_is_yellow_and_another_buyers_pin_is_red(self):
        faded = receipt("SHOP", "DATE: 10/08/2026", "TOTAL | 430 00 KSh")
        result = check(sheet([(AUG10, "a", {"Dinner": 430})]), [faded], pin=None)
        r = result.items[0]
        self.assertEqual((r.status, r.colour, r.reason, r.problems), (CAUTION, YELLOW, POSSIBLE_ONLY, (P_AMOUNT,)))
        other = receipt("SHOP", "DATE: 10/08/2026", "TOTAL | 750.00", "Buyer PIN: B987654321C")
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [other], pin_required=False)
        r = result.items[0]
        self.assertEqual((r.colour, r.reason, r.problems), (RED, OTHER_BUYER, (P_OTHER_BUYER,)))
        self.assertEqual(result.pages[1].lines, ("PIN of another buyer",))


class LinkTests(unittest.TestCase):
    """Every amount linked to one page at most, every page to one amount (D35)."""

    def test_an_amount_on_no_page_is_linked_by_its_date_when_that_is_certain(self):
        result = check(sheet([(AUG14, "a", {"Dinner": 330})]), [slip("320.00", "14/08/2026")])
        r = result.items[0]
        self.assertEqual((r.colour, r.page, r.problems), (YELLOW, 1, (P_AMOUNT,)))
        self.assertIn(DATE, {h.key for h in r.hits}, "the date that linked it is highlighted")
        self.assertEqual(result.pages[1].item, 0)

    def test_two_pages_with_the_date_are_never_guessed_between(self):
        claim = sheet([(AUG14, "a", {"Dinner": 330})])
        result = check(claim, [slip("320.00", "14/08/2026"), slip("350.00", "14/08/2026")])
        self.assertEqual((result.items[0].colour, result.items[0].problems), (RED, (P_NO_RECEIPT,)))
        self.assertEqual([p.lines for p in result.pages.values()], [("Date · Amount",), ("Date · Amount",)])
        self.assertEqual([p.colour for p in result.pages.values()], [YELLOW, YELLOW])

    def test_two_amounts_with_one_page_of_their_date_are_never_guessed_between(self):
        claim = sheet([(AUG14, "a", {"Dinner": 330}), (AUG14, "b", {"Lunch": 450})])
        result = check(claim, [slip("320.00", "14/08/2026")])
        self.assertEqual([r.problems for r in result.items], [(P_NO_RECEIPT,), (P_NO_RECEIPT,)])
        self.assertIsNone(result.pages[1].item)

    def test_a_page_no_amount_uses_says_so_and_is_red_without_a_required_pin(self):
        claim = sheet([(AUG10, "a", {"Dinner": 750})])
        result = check(claim, [slip("750.00", "10/08/2026"), slip("99.00", "02/08/2026"),
                               slip("88.00", "03/08/2026", pin=False)])
        self.assertEqual([(p.colour, p.lines) for p in result.pages.values()],
                         [(GREEN, ("✓",)), (YELLOW, ("Date · Amount",)), (RED, ("Date · Amount", "PIN missing"))])

    def test_a_page_that_could_not_be_read_is_red(self):
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [slip("750.00", "10/08/2026")], unread=[2])
        self.assertEqual((result.pages[2].colour, result.pages[2].problems, result.pages[2].lines),
                         (RED, (P_UNREADABLE,), ("Unreadable",)))

    def test_no_page_is_ever_linked_to_two_amounts(self):
        claim = sheet([(AUG10, "a", {"Dinner": 750, "Lunch": 750}), (AUG10, "b", {"Other": 750}),
                       (AUG11, "c", {"Hotel": 999})])
        result = check(claim, [slip("750.00", "10/08/2026"), slip("750.00", "10/08/2026", pin=False),
                               slip("12.00", "11/08/2026")])
        pages = [r.page for r in result.items if r.page is not None]
        self.assertEqual(len(pages), len(set(pages)))
        self.assertTrue(all(result.pages[r.page].item == i for i, r in enumerate(result.items) if r.page))


class PinTests(unittest.TestCase):
    def test_pin_scan_sets_the_switch_and_a_missing_pin_is_red(self):
        claim = sheet([(AUG10, "a", {"Dinner": 750}), (AUG11, "b", {"Dinner": 760})])
        pages = [slip("750.00", "10/08/2026"), slip("760.00", "11/08/2026", pin=False)]
        result = check(claim, pages)
        self.assertTrue(result.pin_required)
        r = result.items[1]
        self.assertEqual((r.colour, r.reason, r.problems, r.lines), (RED, NO_PIN, (P_PIN,), ("PIN missing",)))
        self.assertEqual((result.pin.colour, result.pin.text), (RED, "missing"))

    def test_flipping_the_switch_only_decides_again(self):
        claim = sheet([(AUG11, "b", {"Dinner": 760})])
        facts = analyse_receipts({1: slip("760.00", "11/08/2026", pin=False), 2: slip("1.00", "01/08/2026")}, 2, [],
                                 FAKE_PIN, CHECKING, MATCHING)
        findings = find_all(claim, facts, FAKE_PIN, MATCHING)
        self.assertEqual(decide(claim, findings, facts, True).items[0].reason, NO_PIN)
        off = decide(claim, findings, facts, False)
        self.assertEqual(off.items[0].colour, GREEN)
        self.assertEqual(off.pin.colour, GREY)

    def test_no_pin_anywhere_means_not_required(self):
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [slip("750.00", "10/08/2026", pin=False)])
        self.assertFalse(result.pin_required)
        self.assertEqual((result.items[0].colour, result.pin.colour), (GREEN, GREY))


class RepeatTests(unittest.TestCase):
    def test_a_repeated_page_claimed_once_leaves_the_claim_green_and_the_copy_red(self):
        page = slip("750.00", "10/08/2026", extra=("TIME 12:30",))
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [page, page])
        self.assertEqual(result.items[0].colour, GREEN)
        self.assertEqual(result.repeats, [(1, 2)])
        r = result.repeated_pages
        self.assertEqual((r.colour, r.text, r.note), (RED, "p. 2", "repeats p. 1"))
        self.assertEqual((result.pages[2].colour, result.pages[2].lines), (RED, ("Repeated p. 1",)))

    def test_one_repeated_receipt_for_two_claims_is_red_on_both(self):
        page = slip("750.00", "10/08/2026", extra=("TIME 12:30",))
        claim = sheet([(AUG10, "a", {"Dinner": 750}), (AUG10, "b", {"Dinner": 750})])
        result = check(claim, [page, page])
        self.assertEqual([(r.colour, r.reason, r.page) for r in result.items],
                         [(RED, DOUBLE_CLAIM, 1), (RED, DOUBLE_CLAIM, 2)])
        self.assertTrue(all(P_REPEATED in r.problems for r in result.items))
        self.assertEqual(result.repeated_pages.colour, RED)
        self.assertEqual(result.totals.approved, Decimal("0.00"))

    def test_unread_pages_keep_the_statuses_from_green(self):
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [slip("750.00", "10/08/2026")], unread=[2])
        self.assertEqual(result.items[0].colour, GREEN)
        self.assertEqual((result.verification.colour, result.verification.text), (RED, "p. 2"))
        self.assertEqual(result.repeated_pages.colour, YELLOW)


class DateAndCellTests(unittest.TestCase):
    def test_an_undecided_date_is_settled_by_the_receipt(self):
        claim = sheet([("3/4/2026", "a", {"Dinner": 750})])            # 3 Apr or 4 Mar: the sheet cannot tell
        self.assertTrue(claim.items[0].date.open)
        result = check(claim, [slip("750.00", "03/04/2026")])          # the receipt is dated 3 Apr
        self.assertEqual((result.items[0].colour, result.items[0].date_used), (GREEN, date(2026, 4, 3)))

    def test_a_date_the_receipt_contradicts_goes_to_the_officer(self):
        claim = sheet([("6/10/2026", "a", {"Dinner": 750}), ("6/13/2026", "b", {"Lunch": 5})])   # read month-first
        self.assertEqual(claim.items[0].date.value, date(2026, 6, 10))
        result = check(claim, [slip("750.00", "06/10/2026")])          # the receipt: 6 October, day-first
        r = result.items[0]
        self.assertEqual((r.colour, r.reason, r.problems), (YELLOW, DATE_CONTRADICTED, (P_DATE,)))

    def test_no_date_and_unreadable_amount(self):
        claim = sheet([(None, "a", {"Dinner": 750}), (AUG10, "b", {"Lunch": "abc"})], total=False)
        result = check(claim, [slip("750.00", "10/08/2026")])
        self.assertEqual([r.reason for r in result.items], [NO_DATE, AMOUNT_UNREADABLE])
        self.assertIn("the amount is on page 1", result.items[0].detail)
        self.assertEqual((result.items[0].colour, result.items[0].lines), (YELLOW, ("Date: none on the sheet",)))
        self.assertEqual(result.items[1].problems, (P_NO_RECEIPT,))


class TotalsTests(unittest.TestCase):
    def test_sums_with_and_without_a_rate(self):
        claim = sheet([(AUG10, "a", {"Dinner": 750}), (AUG11, "b", {"Dinner": 760})])
        result = check(claim, [slip("750.00", "10/08/2026")])
        t = result.totals
        self.assertEqual((t.claimed, t.grand_total, t.approved), (Decimal("1510.00"), Decimal("1510.00"),
                                                                  Decimal("750.00")))
        doubled = sheet([(AUG10, "a", {"Dinner": 750})], rate=2)
        t = check(doubled, [slip("750.00", "10/08/2026")]).totals
        self.assertEqual(t.claimed, Decimal("1500.00"))
        self.assertEqual(t.rows_disagreeing, [7], "the form's own row Total ignores the Rate")

    def test_the_one_total_status(self):
        verified = [slip("750.00", "10/08/2026")]
        self.assertEqual(check(sheet([(AUG10, "a", {"Dinner": 750})]), verified).total.text, "Total matched")
        wrong_total = sheet([(AUG10, "a", {"Dinner": 750})])
        wrong_total.grand_total = Decimal("800.00")                    # the sheet's Total typed wrong
        self.assertEqual(self.total(wrong_total, verified), (YELLOW, "Excel mistake"))
        self.assertEqual(self.total(sheet([(AUG10, "a", {"Dinner": 750})], rate=2), verified),
                         (YELLOW, "Excel mistake"), "a row's own Total does not add up")
        self.assertEqual(self.total(sheet([(AUG10, "a", {"Dinner": 750})], total=False), verified),
                         (YELLOW, "No total"))
        unverified = sheet([(AUG10, "a", {"Dinner": 750}), (AUG11, "b", {"Dinner": 760})])
        self.assertEqual(self.total(unverified, verified), (RED, "Not matched"))
        self.assertIn("verified 750.00", check(unverified, verified).total.detail)
        self.assertEqual(check(unverified, verified).total.note, "750.00 of 1,510.00")
        self.assertEqual(check(sheet([(AUG10, "a", {"Dinner": 750})]), verified).total.note, "750.00")
        self.assertEqual(check(wrong_total, verified).total.note, "amounts 750.00 · sheet 800.00")

    def total(self, claim, pages):
        status = check(claim, pages).total
        return status.colour, status.text

    def test_verification_lists_the_failing_pages_and_counts_amounts_without_a_receipt(self):
        claim = sheet([(AUG10, "a", {"Dinner": 750}), (AUG11, "b", {"Dinner": 760}), (AUG14, "c", {"Hotel": 999})])
        result = check(claim, [slip("750.00", "10/08/2026"), slip("760.00", "12/08/2026")])
        v = result.verification
        self.assertEqual((v.colour, v.text, v.note), (RED, "p. 2", "1 no receipt"))
        self.assertIn("Hotel (999.00)", v.detail)
        only_missing = check(sheet([(AUG14, "c", {"Hotel": 999})]), []).verification
        self.assertEqual((only_missing.text, only_missing.note), ("1 no receipt", ""))

    def test_everything_verified_is_green(self):
        result = check(sheet([(AUG10, "a", {"Dinner": 750})]), [slip("750.00", "10/08/2026")])
        self.assertEqual((result.verification.colour, result.verification.text), (GREEN, "all verified"))
        self.assertEqual(result.total.colour, GREEN)


class IndexAndBoundaryTests(unittest.TestCase):
    def test_the_amount_index_never_hides_a_page_the_full_search_would_find(self):
        pages = {1: slip("1,060.00", "12/08/2026"), 2: receipt("TOTAL 1060 KSh"), 3: receipt("430 00 KSh"),
                 4: slip("500.34", "10/08/2026"), 5: receipt("nothing here")}
        facts = analyse_receipts(pages, 5, [], None, CHECKING, MATCHING)
        for amount in ("1060", "430", "500", "500.34", "77"):
            value = Decimal(amount)
            full = {n for n, p in pages.items() if any(h.key == AMOUNT for h in search_page(p, Query(amount=value),
                                                                                          MATCHING))}
            self.assertLessEqual(full, set(facts.pages_for(value, MATCHING)), amount)

    def test_the_shown_receipt_total_ignores_ocr_slips_and_reads_whole_birr(self):
        pages = {1: receipt("TOTAL | 1O1AL:±1.300.02 | 760.01"), 2: receipt("Total Paid Amount | 1,306 Birr")}
        facts = analyse_receipts(pages, 2, [], None, CHECKING, MATCHING)
        self.assertEqual(facts.printed_total, {1: Decimal("760.01"), 2: Decimal("1306.00")})

    def test_broken_colour_and_badge_rules_are_config_errors(self):
        import json
        import tempfile
        from pathlib import Path
        from app.checking.rules import DEFAULT_CHECKING_RULES
        from app.errors import StageError
        good = json.loads(DEFAULT_CHECKING_RULES.read_text(encoding="utf-8"))
        cases = {
            "red_problems": ["no_receipt", "colour"],
            "badge_lines": {**good["badge_lines"], "amount": "Amount {receipt}"},        # {claimed} missing
            "badge_date_format": 5,
        }
        with tempfile.TemporaryDirectory() as folder:
            for key, value in cases.items():
                path = Path(folder) / "rules.json"
                path.write_text(json.dumps({**good, key: value}), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(StageError) as caught:
                    load_checking_rules(path)
                self.assertEqual(caught.exception.stage, "config")
                self.assertIn(key, caught.exception.summary)

    def test_the_decision_package_loads_no_ocr_image_or_window_code(self):
        code = ("import sys, app.checking; print(sorted(m for m in ('cv2', 'pymupdf', 'openpyxl', 'PySide6', 'numpy', "
                "'app.ocr', 'app.gui') if m in sys.modules))")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
