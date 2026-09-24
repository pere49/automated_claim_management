"""app/claims: reading claim sheets from a PDF (exported or scanned) — synthetic forms only."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pymupdf

from app.claims import (CLAIM_PERIOD, EMPTY, NO_FUTURE, ONE_MEANING, PDF_TEXT, SCANNED, SHEET_ORDER, UNDECIDED,
                        UNREADABLE, load_claim_rules, looks_like_claim_sheet, read_claim_file, sheet_kind)
from app.claims.amounts import read_amount
from app.claims.sheet_builder import build_sheet
from app.claims.sheet_dates import read_dates
from app.errors import StageError
from tests.claim_fixtures import form_grid, write_pdf_form

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


def scanned_copy(pdf_path: Path, folder: Path, dpi: int = 200):
    """The PDF's page as a picture, and its words in the picture's pixels (standing in for OCR)."""
    with pymupdf.open(pdf_path) as doc:
        scale = dpi / 72
        words = [(w[0] * scale, w[1] * scale, w[2] * scale, w[3] * scale, w[4]) for w in doc[0].get_text("words")]
        picture = folder / "scan.png"
        doc[0].get_pixmap(dpi=dpi).save(picture)
    return picture, words


class PdfTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def pdf(self, grid, name="claim.pdf") -> Path:
        return write_pdf_form(self.folder / name, grid)

    def read(self, grid, name="claim.pdf"):
        return read_claim_file(self.pdf(grid, name), RULES, TODAY)


class ReadingTests(PdfTestCase):
    def test_every_expense_amount_is_one_item_with_its_rows_date(self):
        claim = self.read(form_grid(ENTRIES))
        self.assertEqual(claim.kind, PDF_TEXT)
        sheet = claim.sheets[0]
        self.assertEqual(items(sheet), [
            ("Dinner", Decimal("750.00"), date(2026, 8, 10)),
            ("Breakfast", Decimal("200.00"), date(2026, 8, 11)),
            ("Dinner", Decimal("760.50"), date(2026, 8, 11)),
            ("Travel", Decimal("1500.00"), date(2026, 8, 13)),
            ("Other", Decimal("300.00"), None),
        ])
        first = sheet.items[0].row
        self.assertEqual([it.row for it in sheet.items], [first, first + 1, first + 1, first + 2, first + 3])
        self.assertEqual(sheet.grand_total, Decimal("3510.50"))
        self.assertEqual(sheet.currency, "KES")
        self.assertEqual(sheet.problems, [])

    def test_ledger_codes_in_the_header_never_become_amounts(self):
        sheet = self.read(form_grid(ENTRIES)).sheets[0]
        self.assertNotIn(Decimal("4740150"), [it.amount for it in sheet.items])

    def test_the_name_line_holding_a_date_label_is_not_the_header(self):
        sheet = self.read(form_grid(ENTRIES)).sheets[0]
        self.assertEqual(sheet.grid[sheet.header_row][sheet.columns.date], "Date")
        self.assertEqual(len(sheet.columns.expenses), 8)

    def test_pages_without_a_claim_table_are_skipped_and_named(self):
        path = self.pdf(form_grid(ENTRIES))
        with pymupdf.open(path) as doc:
            notes = doc.new_page(0)
            for i in range(25):
                notes.insert_text((20, 30 + i * 12), f"notes line {i} about the trip")
            doc.save(self.folder / "two.pdf")
        claim = read_claim_file(self.folder / "two.pdf", RULES, TODAY)
        self.assertEqual([s.name for s in claim.sheets], ["page 2"])
        self.assertEqual(claim.skipped, ["page 1"])
        self.assertEqual(claim.sheets[0].place.page, 2)

    def test_unreadable_amounts_become_items_with_a_reason_not_a_stop(self):
        bad = [(datetime(2026, 8, 10), "Meals", {"Dinner": "12.345", "Lunch": "abc", "Other": "-5",
                                                "Hotel": "1,060.00"})]
        sheet = self.read(form_grid(bad, total=False)).sheets[0]
        found = {it.column: (it.amount, it.problem) for it in sheet.items}
        self.assertEqual(found["Dinner"], (None, "not a number"))
        self.assertEqual(found["Lunch"], (None, "not a number"))
        self.assertEqual(found["Other"], (None, "a negative amount"))
        self.assertEqual(found["Hotel"], (Decimal("1060.00"), None))
        self.assertIn("no Total row", sheet.problems[0])

    def test_rate_blank_or_zero_counts_as_one(self):
        for rate in (None, 0, 2):
            sheet = self.read(form_grid(ENTRIES[:1], rate=rate), name=f"r{rate}.pdf").sheets[0]
            self.assertEqual(sheet.items[0].rate, Decimal(rate or 1))

    def test_a_totals_row_without_a_label_is_recognised_by_its_sums(self):
        grid = form_grid([(datetime(2026, 7, d), "Bakery", {"Daily Allowance": 48}) for d in range(16, 20)], total=False)
        sums = [None] * 15
        sums[10], sums[14] = 192, 192
        grid.insert(len(grid) - 2, sums)
        sheet = self.read(grid).sheets[0]
        self.assertEqual(len(sheet.items), 4)
        self.assertEqual(sheet.grand_total, Decimal("192.00"))


class ColumnRangeTests(unittest.TestCase):
    """Every column from Motor to Other counts, whatever it is called (D40)."""

    def test_a_column_added_between_motor_and_other_counts(self):
        grid = form_grid([(datetime(2026, 8, 10), "Trip", {"Dinner": 750})])
        for row in grid:
            row.insert(12, None)                       # a column the form did not have, just before Other
        grid[3][12] = "Parking fees"
        grid[6][12] = 45
        sheet = build_sheet("W", grid, list(range(1, len(grid) + 1)), RULES, TODAY)
        self.assertEqual([(it.column, it.amount) for it in sheet.items],
                         [("Dinner", Decimal("750.00")), ("Parking fees", Decimal("45.00"))])

    def test_a_range_naming_an_unknown_column_is_a_config_error(self):
        import json
        from app.claims.rules import DEFAULT_CLAIM_RULES
        good = json.loads(DEFAULT_CLAIM_RULES.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            for ends in (["Motor Vehicle Fuel", "Parking"], ["Other", "Other"], ["Motor Vehicle Fuel"]):
                path = Path(folder) / "rules.json"
                path.write_text(json.dumps({**good, "expense_range": ends}), encoding="utf-8")
                with self.subTest(ends=ends), self.assertRaises(StageError) as caught:
                    load_claim_rules(path)
                self.assertIn("expense_range", caught.exception.summary)

    def test_without_both_ends_only_the_named_columns_count(self):
        grid = form_grid([(datetime(2026, 8, 10), "Trip", {"Dinner": 750, "Hotel": 900})])
        grid[3][12] = "Sundries"                       # no "Other" header: the range has no end
        grid[6][12] = 45
        sheet = build_sheet("W", grid, list(range(1, len(grid) + 1)), RULES, TODAY)
        self.assertEqual([it.column for it in sheet.items], ["Dinner", "Hotel"])


class PlaceTests(PdfTestCase):
    """Where the table sits on the page: the window points at rows and cells with it (D36, D39)."""

    def page_words(self, path: Path):
        with pymupdf.open(path) as doc:
            page = doc[0]
            return page.rect.width, page.rect.height, page.get_text("words")

    def test_each_amounts_cell_holds_its_printed_value(self):
        path = self.pdf(form_grid(ENTRIES))
        sheet = read_claim_file(path, RULES, TODAY).sheets[0]
        width, height, words = self.page_words(path)
        for it, text in zip(sheet.items, ["750.00", "200.00", "760.50", "1,500.00", "300.00"]):
            cell = sheet.place.cell(it.grid_row, it.grid_col)
            word = next(w for w in words if w[4] == text)
            x, y = (word[0] + word[2]) / 2 / width, (word[1] + word[3]) / 2 / height
            self.assertTrue(cell.left < x < cell.right and cell.top < y < cell.bottom, text)
            band = sheet.place.row_band(it.grid_row)
            self.assertTrue(band.left <= cell.left and cell.right <= band.right)

    def test_the_printed_area_holds_every_word_and_leaves_the_margins(self):
        path = self.pdf(form_grid(ENTRIES))
        p = read_claim_file(path, RULES, TODAY).sheets[0].place.printed
        width, height, words = self.page_words(path)
        self.assertTrue(0 < p.left < p.right < 1 and 0 < p.top < p.bottom < 1)
        for w in words:
            self.assertTrue(p.left <= w[0] / width + 1e-6 and w[2] / width <= p.right + 1e-6, w[4])
            self.assertTrue(p.top <= w[1] / height + 1e-6 and w[3] / height <= p.bottom + 1e-6, w[4])

    def test_a_scanned_sheet_places_its_cells_where_the_pdf_does(self):
        pdf_path = self.pdf(form_grid(ENTRIES))
        picture, words = scanned_copy(pdf_path, self.folder)
        scanned = read_claim_file(picture, RULES, TODAY, scanned_words={1: words}, dpi=200).sheets[0]
        text = read_claim_file(pdf_path, RULES, TODAY).sheets[0]
        for a, b in zip(scanned.items, text.items):
            ca, cb = scanned.place.cell(a.grid_row, a.grid_col), text.place.cell(b.grid_row, b.grid_col)
            for u, v in ((ca.left, cb.left), (ca.top, cb.top), (ca.right, cb.right), (ca.bottom, cb.bottom)):
                self.assertAlmostEqual(u, v, delta=0.01)


class FileTests(PdfTestCase):
    def test_a_scanned_sheet_read_through_its_ocr_words_gives_the_same_items(self):
        pdf_path = self.pdf(form_grid(ENTRIES))
        picture, words = scanned_copy(pdf_path, self.folder)
        self.assertEqual(sheet_kind(pdf_path, RULES), PDF_TEXT)
        self.assertTrue(looks_like_claim_sheet(pdf_path, RULES))
        self.assertEqual(sheet_kind(picture, RULES), SCANNED)
        with self.assertRaises(StageError):
            read_claim_file(picture, RULES, TODAY)          # a picture needs its OCR words first
        scanned = read_claim_file(picture, RULES, TODAY, scanned_words={1: words}, dpi=200)
        self.assertEqual(items(scanned.sheets[0]), items(read_claim_file(pdf_path, RULES, TODAY).sheets[0]))

    def test_a_receipt_pdf_does_not_look_like_a_claim_sheet(self):
        doc = pymupdf.open()
        page = doc.new_page()
        for i in range(30):
            page.insert_text((20, 20 + i * 10), f"TOTAL {i}00.00 THANK YOU")
        doc.save(self.folder / "receipt.pdf")
        doc.close()
        self.assertFalse(looks_like_claim_sheet(self.folder / "receipt.pdf", RULES))
        with self.assertRaises(StageError) as caught:
            read_claim_file(self.folder / "receipt.pdf", RULES, TODAY)
        self.assertIn("no claim table", caught.exception.detail)

    def test_excel_and_damaged_files_are_refused_with_a_reason(self):
        for name in ("claim.xlsx", "old.xls"):
            (self.folder / name).write_bytes(b"a workbook")
            self.assertFalse(looks_like_claim_sheet(self.folder / name, RULES))
            with self.assertRaises(StageError) as caught:
                read_claim_file(self.folder / name, RULES, TODAY)
            self.assertIn("use the PDF of the claim sheet", caught.exception.detail)
        (self.folder / "broken.pdf").write_bytes(b"not a pdf")
        with self.assertRaises(StageError) as broken:
            read_claim_file(self.folder / "broken.pdf", RULES, TODAY)
        self.assertEqual((broken.exception.stage, broken.exception.file), ("claim sheet", "broken.pdf"))


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

    def test_date_cells_and_serial_numbers_are_dates(self):
        got = self.read([46244, datetime(2026, 8, 10)])            # 2026-08-10 both
        self.assertEqual([g.value for g in got], [date(2026, 8, 10), date(2026, 8, 10)])


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
