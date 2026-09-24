"""app/claims: reading claim sheets from Excel, PDF and scanned pictures (synthetic forms only)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pymupdf

from app.claims import (CLAIM_PERIOD, EMPTY, EXCEL, NO_FUTURE, ONE_MEANING, PDF_TEXT, SCANNED, SHEET_ORDER, UNDECIDED,
                        UNREADABLE, load_claim_rules, looks_like_claim_sheet, read_claim_file, sheet_kind)
from app.claims.amounts import read_amount
from app.claims.sheet_dates import read_dates
from app.errors import StageError
from tests.claim_fixtures import FIRST_DATA_ROW, form_grid, write_pdf_form, write_workbook

TODAY = date(2026, 9, 24)
RULES = load_claim_rules()

ENTRIES = [
    (datetime(2026, 8, 10), "Meals", {"Dinner": 750}),
    (datetime(2026, 8, 11), "Meals", {"Dinner": 760.5, "Breakfast": 200}),
    (datetime(2026, 8, 13), "Taxi", {"Travel": 1500}),
    (None, "parking", {"Other": 300}),
]


def items(sheet):
    return [(it.column, it.amount, it.date.value) for it in sheet.items]


class ExcelTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def book(self, tabs, active=None, name="claim.xlsx"):
        return write_workbook(self.folder / name, tabs, active)

    def test_every_expense_amount_is_one_item_with_its_rows_date(self):
        claim = read_claim_file(self.book({"Week": form_grid(ENTRIES)}), RULES, TODAY)
        self.assertEqual(claim.kind, EXCEL)
        sheet = claim.sheets[0]
        self.assertEqual(items(sheet), [
            ("Dinner", Decimal("750.00"), date(2026, 8, 10)),
            ("Breakfast", Decimal("200.00"), date(2026, 8, 11)),
            ("Dinner", Decimal("760.50"), date(2026, 8, 11)),
            ("Travel", Decimal("1500.00"), date(2026, 8, 13)),
            ("Other", Decimal("300.00"), None),
        ])
        self.assertEqual([it.row for it in sheet.items], [FIRST_DATA_ROW, 8, 8, 9, 10])
        self.assertEqual(sheet.grand_total, Decimal("3510.50"))
        self.assertEqual(sheet.currency, "KES")
        self.assertEqual(sheet.problems, [])

    def test_ledger_codes_in_the_header_never_become_amounts(self):
        sheet = read_claim_file(self.book({"Week": form_grid(ENTRIES)}), RULES, TODAY).sheets[0]
        self.assertNotIn(Decimal("4740150"), [it.amount for it in sheet.items])
        self.assertEqual(sheet.first_data_row, FIRST_DATA_ROW - 1)

    def test_the_name_line_holding_a_date_label_is_not_the_header(self):
        sheet = read_claim_file(self.book({"Week": form_grid(ENTRIES)}), RULES, TODAY).sheets[0]
        self.assertEqual(sheet.columns.date, 1)
        self.assertEqual(len(sheet.columns.expenses), 8)

    def test_dates_stored_swapped_by_the_excel_setting_are_read_right(self):
        # typed day-first (3/8, 5/8, 6/8, 9/8/2026) into an Excel set to month-first: saved as 8 March, 8 May...
        swapped = [(datetime(2026, d.day, d.month), "Meals", {"Dinner": 100 + i})
                   for i, d in enumerate([date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 9)])]
        sheet = read_claim_file(self.book({"Week1": form_grid(swapped)}), RULES, TODAY).sheets[0]
        self.assertEqual([it.date.value for it in sheet.items],
                         [date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 9)])
        self.assertTrue(all(it.date.how == CLAIM_PERIOD for it in sheet.items))

    def test_several_tabs_start_on_the_one_saved_last_and_skip_tabs_without_a_table(self):
        path = self.book({"Week1": form_grid(ENTRIES), "Notes": [["just", "notes"]], "Week2": form_grid(ENTRIES[:1])},
                         active="Week2")
        claim = read_claim_file(path, RULES, TODAY)
        self.assertEqual([s.name for s in claim.sheets], ["Week1", "Week2"])
        self.assertEqual(claim.sheets[claim.active].name, "Week2")
        self.assertEqual(claim.skipped, ["Notes"])

    def test_unreadable_amounts_become_items_with_a_reason_not_a_stop(self):
        bad = [(datetime(2026, 8, 10), "Meals", {"Dinner": 12.345, "Lunch": "abc", "Other": -5, "Hotel": "1,060.00"})]
        sheet = read_claim_file(self.book({"Week": form_grid(bad, total=False)}), RULES, TODAY).sheets[0]
        found = {it.column: (it.amount, it.problem) for it in sheet.items}
        self.assertEqual(found["Dinner"], (None, "the amount has more than two decimals"))
        self.assertEqual(found["Lunch"], (None, "not a number"))
        self.assertEqual(found["Other"], (None, "a negative amount"))
        self.assertEqual(found["Hotel"], (Decimal("1060.00"), None))
        self.assertIn("no Total row", sheet.problems[0])

    def test_rate_blank_or_zero_counts_as_one(self):
        for rate in (None, 0, 2):
            sheet = read_claim_file(self.book({"W": form_grid(ENTRIES[:1], rate=rate)}, name=f"r{rate}.xlsx"),
                                    RULES, TODAY).sheets[0]
            self.assertEqual(sheet.items[0].rate, Decimal(rate or 1))

    def test_a_workbook_without_any_claim_table_is_an_error(self):
        with self.assertRaises(StageError) as caught:
            read_claim_file(self.book({"Notes": [["hello"]]}), RULES, TODAY)
        self.assertIn("no claim table", caught.exception.detail)

    def test_old_xls_and_damaged_files_are_refused_with_a_reason(self):
        (self.folder / "old.xls").write_bytes(b"old")
        (self.folder / "broken.xlsx").write_bytes(b"not a workbook")
        with self.assertRaises(StageError) as old:
            read_claim_file(self.folder / "old.xls", RULES, TODAY)
        self.assertIn("save it as .xlsx", old.exception.detail)
        with self.assertRaises(StageError) as broken:
            read_claim_file(self.folder / "broken.xlsx", RULES, TODAY)
        self.assertEqual(broken.exception.stage, "claim sheet")
        self.assertEqual(broken.exception.file, "broken.xlsx")

    def test_a_totals_row_without_a_label_is_recognised_by_its_sums(self):
        grid = form_grid([(datetime(2026, 7, d), "Bakery", {"Daily Allowance": 48}) for d in range(16, 20)], total=False)
        sums = [None] * 15
        sums[10], sums[14] = 192, 192
        grid.insert(len(grid) - 2, sums)
        sheet = read_claim_file(self.book({"EA": grid}), RULES, TODAY).sheets[0]
        self.assertEqual(len(sheet.items), 4)
        self.assertEqual(sheet.grand_total, Decimal("192.00"))


class PdfTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def test_a_pdf_export_gives_the_same_items_as_the_workbook(self):
        grid = form_grid(ENTRIES)
        excel = read_claim_file(write_workbook(self.folder / "c.xlsx", {"W": grid}), RULES, TODAY).sheets[0]
        pdf_path = write_pdf_form(self.folder / "c.pdf", grid)
        self.assertEqual(sheet_kind(pdf_path, RULES), PDF_TEXT)
        self.assertTrue(looks_like_claim_sheet(pdf_path, RULES))
        pdf = read_claim_file(pdf_path, RULES, TODAY)
        self.assertEqual(items(pdf.sheets[0]), items(excel))
        self.assertEqual(pdf.sheets[0].grand_total, excel.grand_total)

    def test_a_scanned_sheet_read_through_its_ocr_words_gives_the_same_items(self):
        grid = form_grid(ENTRIES)
        pdf_path = write_pdf_form(self.folder / "c.pdf", grid)
        dpi = 200
        with pymupdf.open(pdf_path) as doc:
            scale = dpi / 72
            words = [(w[0] * scale, w[1] * scale, w[2] * scale, w[3] * scale, w[4]) for w in doc[0].get_text("words")]
            picture = self.folder / "scan.png"
            doc[0].get_pixmap(dpi=dpi).save(picture)
        self.assertEqual(sheet_kind(picture, RULES), SCANNED)
        with self.assertRaises(StageError):
            read_claim_file(picture, RULES, TODAY)          # a picture needs its OCR words first
        scanned = read_claim_file(picture, RULES, TODAY, scanned_words={1: words}, dpi=dpi)
        self.assertEqual(items(scanned.sheets[0]), items(read_claim_file(pdf_path, RULES, TODAY).sheets[0]))

    def test_a_receipt_pdf_does_not_look_like_a_claim_sheet(self):
        doc = pymupdf.open()
        page = doc.new_page()
        for i in range(30):
            page.insert_text((20, 20 + i * 10), f"TOTAL {i}00.00 THANK YOU")
        doc.save(self.folder / "receipt.pdf")
        doc.close()
        self.assertFalse(looks_like_claim_sheet(self.folder / "receipt.pdf", RULES))


class DateTests(unittest.TestCase):
    def read(self, cells, today=TODAY):
        return read_dates(cells, today, RULES)

    def test_a_part_above_twelve_fixes_the_order_for_the_whole_sheet(self):
        got = self.read(["6/10/2026", "6/13/2026", "7/2/2026"])
        self.assertEqual([g.value for g in got], [date(2026, 6, 10), date(2026, 6, 13), date(2026, 7, 2)])
        self.assertEqual(got[0].how, SHEET_ORDER)
        self.assertEqual(got[1].how, ONE_MEANING)

    def test_no_reading_after_the_day_of_checking(self):
        got = self.read(["9/3/2026", "10/3/2026"], today=date(2026, 3, 20))   # 9-10 Mar, or 3 Sep / 3 Oct: not yet
        self.assertEqual([g.value for g in got], [date(2026, 3, 9), date(2026, 3, 10)])
        self.assertEqual(got[0].how, NO_FUTURE)

    def test_both_orders_past_and_within_one_period_stay_undecided(self):
        got = self.read(["3/9/2026", "4/9/2026"], today=date(2026, 9, 20))    # 3-4 Sep, or 9 Mar / 9 Apr
        self.assertEqual([g.value for g in got], [None, None])
        self.assertTrue(all(g.open for g in got))

    def test_the_claim_period_decides_when_both_orders_are_past(self):
        got = self.read(["3/8/2026", "5/8/2026", "9/8/2026"])     # 3-9 Aug, or 8 Mar - 8 Sep (too long for one claim)
        self.assertEqual([g.value for g in got], [date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 9)])
        self.assertEqual(got[0].how, CLAIM_PERIOD)

    def test_an_undecidable_date_keeps_both_readings_and_is_never_guessed(self):
        got = self.read(["3/4/2026"])                               # 3 Apr or 4 Mar: both past, both one claim
        self.assertIsNone(got[0].value)
        self.assertEqual(got[0].how, UNDECIDED)
        self.assertEqual(set(got[0].candidates), {date(2026, 4, 3), date(2026, 3, 4)})
        self.assertTrue(got[0].open)

    def test_forms_ocr_slips_blank_and_rubbish(self):
        got = self.read(["12-Jul-26", "Jun 12, 2026", "2026-08-03", "1O/08/2026", "", None, "soon", "-"])
        self.assertEqual([g.value for g in got[:4]],
                         [date(2026, 7, 12), date(2026, 6, 12), date(2026, 8, 3), date(2026, 8, 10)])
        self.assertEqual([g.how for g in got[4:]], [EMPTY, EMPTY, UNREADABLE, EMPTY])

    def test_excel_serial_numbers_are_dates(self):
        got = self.read([46244])                                    # 2026-08-10
        self.assertEqual(got[0].value, date(2026, 8, 10))


class AmountTests(unittest.TestCase):
    def test_amounts(self):
        cases = {2406.94: Decimal("2406.94"), 750: Decimal("750.00"), "1,060.00": Decimal("1060.00"),
                 "KES 500": Decimal("500.00"), 0: None, "-": None, None: None}
        for value, expected in cases.items():
            self.assertEqual(read_amount(value, RULES)[0], expected, value)
        self.assertEqual(read_amount(4340.9400000000005, RULES, calculated=True)[0], Decimal("4340.94"))
        self.assertIsNotNone(read_amount(4340.9400000000005, RULES)[1], "a typed amount is never rounded silently")


if __name__ == "__main__":
    unittest.main()
