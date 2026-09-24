"""The window in Stage C: claim sheet slot, checking, colours, status, PIN switch, tour (off-screen).

Receipts are read by FakeReader: page n reads "TOTAL n00.00" / "DATE:0n/08/2026",
with "PIN: A012345678Z" on even pages. The claim sheet is a synthetic workbook
in the owner's template layout (tests/claim_fixtures.py). All values fabricated.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from tests.qt import qt_app, wait_until  # sets the off-screen platform first

from app.checking import GREEN, NO_PIN, NOT_FOUND, PAIRED, YELLOW
from app.gui.main_window import MainWindow
from app.gui.settings import load_settings
from tests.claim_fixtures import form_grid, write_pdf_form, write_workbook
from tests.fakes import FAKE_PIN, FakeReader, make_pdf

ENTRIES = [
    (datetime(2026, 8, 1), "Meals", {"Dinner": 100}),     # page 1: no PIN printed
    (datetime(2026, 8, 2), "Meals", {"Lunch": 200}),      # page 2: PIN printed
    (datetime(2026, 8, 3), "Taxi", {"Travel": 300}),      # page 3: no PIN printed
    (datetime(2026, 8, 13), "Hotel", {"Hotel": 999}),     # on no receipt
]


class ClaimWindowTestCase(unittest.TestCase):
    def setUp(self):
        qt_app()
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)
        make_pdf(self.folder / "receipts.pdf", 3)
        write_workbook(self.folder / "claim.xlsx", {"Week": form_grid(ENTRIES)})
        (self.folder / ".env").write_text(f"COMPANY_PINS={FAKE_PIN}\n", encoding="utf-8")

    def tearDown(self):
        self._dir.cleanup()

    def window(self, **changes) -> MainWindow:
        values = dict(working_folder=self.folder, read_ahead=False, tour_auto_start=False, tour_green_ms=20,
                      tour_yellow_ms=20, company_pin_file=self.folder / ".env")
        settings = dataclasses.replace(load_settings(), **{**values, **changes})
        w = MainWindow(settings, FakeReader(), today=lambda: date(2026, 9, 24))
        w.confirm = lambda *a: True
        w.resize(1400, 900)
        w.show()
        w.start()
        self.addCleanup(w.close)
        return w

    def click(self, w: MainWindow, name: str) -> None:
        w.files.file_chosen.emit(self.folder / name)
        wait_until(lambda: not w.session.busy)
        wait_until(lambda: False, 0.05)

    def checked(self, w: MainWindow) -> list:
        self.click(w, "claim.xlsx")
        self.click(w, "receipts.pdf")
        self.assertTrue(wait_until(lambda: w.claims.result is not None), "the claim was never checked")
        return w.claims.result.items


class SlotAndCheckTests(ClaimWindowTestCase):
    def test_an_excel_click_fills_the_claim_sheet_slot_and_shows_its_amounts(self):
        w = self.window()
        self.click(w, "claim.xlsx")
        self.assertEqual(w.claims.sheet_path, self.folder / "claim.xlsx")
        self.assertIn("claim.xlsx", w.files.sheet_slot.text())
        self.assertIsNone(w.session.path, "a claim sheet is not opened as receipts")
        self.assertEqual(len(w.claims.sheet.items), 4)
        self.assertGreater(w.sheet_grid.model.rowCount(), 4)
        self.assertIn("Choose the receipts PDF", w.sheet_grid.reason.text())

    def test_the_claim_is_checked_when_the_receipts_have_been_read(self):
        w = self.window()
        items = self.checked(w)
        self.assertEqual([(r.colour, r.reason) for r in items],
                         [(YELLOW, NO_PIN), (GREEN, PAIRED), (YELLOW, NO_PIN), (YELLOW, NOT_FOUND)])
        self.assertEqual(w.status_strip.texts, ["Verification: manual check required: 3 to check, Grand total 2 "
                                                "does not match", "PIN: not detected on 2 matched receipts",
                                                "Repeated pages: none"])
        self.assertTrue(w.status_strip.pin_yes.isChecked(), "the PIN is on a page: the switch starts on Yes")
        self.assertIn("Grand total 1", w.sheet_grid.total_1.text())
        self.assertIn("1,599.00", w.sheet_grid.total_1.text())
        self.assertIn("verified 200.00", w.sheet_grid.total_2.text())

    def test_nothing_is_checked_before_every_receipt_page_has_been_read(self):
        w = self.window()
        w.session._worker._reader.delay = 0.3
        self.click(w, "claim.xlsx")
        w.files.file_chosen.emit(self.folder / "receipts.pdf")
        seen = []
        w.claims.checked.connect(lambda result: seen.append((result is not None, w.session.pages_read())))
        self.assertTrue(wait_until(lambda: w.session.pages_read() >= 1))
        self.assertIsNone(w.claims.result)
        self.assertIn("Reading the receipts", w.sheet_grid.reason.text())
        self.assertTrue(wait_until(lambda: w.claims.result is not None))
        self.assertTrue(all(pages == 3 for checked, pages in seen if checked), seen)

    def test_receipts_first_then_the_sheet_also_checks(self):
        w = self.window()
        self.click(w, "receipts.pdf")
        self.click(w, "claim.xlsx")
        self.assertTrue(wait_until(lambda: w.claims.result is not None))
        self.assertIn("receipts.pdf", w.files.receipts_slot.text())

    def test_the_pin_switch_decides_again_without_searching(self):
        w = self.window()
        self.checked(w)
        w.status_strip.pin_no.click()
        wait_until(lambda: False, 0.05)
        self.assertEqual([r.colour for r in w.claims.result.items], [GREEN, GREEN, GREEN, YELLOW])
        self.assertIn("PIN: not required", w.status_strip.texts)

    def test_a_text_pdf_claim_sheet_goes_to_the_slot_too(self):
        write_pdf_form(self.folder / "claim sheet.pdf", form_grid(ENTRIES))
        w = self.window()
        self.click(w, "claim sheet.pdf")
        self.assertEqual(w.claims.sheet_path, self.folder / "claim sheet.pdf")
        self.assertEqual(len(w.claims.sheet.items), 4)

    def test_a_workbook_with_several_claim_sheets_shows_tabs(self):
        write_workbook(self.folder / "claim.xlsx", {"Week1": form_grid(ENTRIES[:1]), "Week2": form_grid(ENTRIES)},
                       active="Week2")
        w = self.window()
        items = self.checked(w)
        self.assertTrue(w.sheet_grid.tabs.isVisible())
        self.assertEqual(w.sheet_grid.tabs.currentIndex(), 1)
        self.assertEqual(len(items), 4)
        w.sheet_grid.tabs.setCurrentIndex(0)
        self.assertTrue(wait_until(lambda: w.claims.result is not None and len(w.claims.result.items) == 1))


class ShowingTests(ClaimWindowTestCase):
    def test_choosing_an_amount_shows_its_receipt_page_with_its_highlights(self):
        w = self.window()
        self.checked(w)
        w.sheet_grid.item_selected.emit(2)
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 3))
        self.assertGreaterEqual(w.page_pane.view.highlight_count, 2)
        self.assertIn("Row 9", w.sheet_grid.reason.text())
        self.assertIn("not the company PIN", w.sheet_grid.reason.text())

    def test_the_tour_walks_every_amount_and_stops_at_the_last(self):
        w = self.window()
        self.checked(w)
        shown = []
        w.tour.show_item.connect(shown.append)
        w.status_strip.auto.click()
        self.assertTrue(wait_until(lambda: not w.tour.running and len(shown) == 4))
        self.assertEqual(shown, [0, 1, 2, 3])
        self.assertEqual(w.status_strip.auto.text(), "▶ Auto")

    def test_a_manual_choice_pauses_the_tour_and_auto_resumes_where_it_stopped(self):
        w = self.window(tour_green_ms=400, tour_yellow_ms=400)
        self.checked(w)
        shown = []
        w.tour.show_item.connect(shown.append)
        w.status_strip.auto.click()
        self.assertTrue(wait_until(lambda: shown == [0]))
        w.sheet_grid.item_selected.emit(3)
        self.assertFalse(w.tour.running)
        w.status_strip.auto.click()
        self.assertTrue(wait_until(lambda: len(shown) >= 2))
        self.assertEqual(shown[1], 1, "Auto resumes after the last amount the tour showed")

    def test_next_to_check_jumps_over_the_green_amounts(self):
        w = self.window()
        self.checked(w)
        shown = []
        w.tour.show_item.connect(shown.append)
        for _ in range(3):
            w.status_strip.next.click()
        self.assertEqual(shown, [0, 2, 3])

    def test_the_tour_starts_by_itself_when_so_configured(self):
        w = self.window(tour_auto_start=True)
        shown = []
        w.tour.show_item.connect(shown.append)
        self.checked(w)
        self.assertTrue(wait_until(lambda: len(shown) == 4))


class FailureTests(ClaimWindowTestCase):
    def test_a_broken_workbook_is_reported_and_nothing_breaks(self):
        (self.folder / "broken.xlsx").write_bytes(b"not a workbook")
        w = self.window()
        self.click(w, "broken.xlsx")
        self.assertIsNone(w.claims.claim)
        self.assertTrue(any("claim sheet:" in e.summary and "broken.xlsx" in e.summary for e in w.errors.entries))
        self.assertIn("Choose a claim sheet", w.sheet_grid.message.text())

    def test_no_company_pin_file_turns_the_pin_checks_off_and_says_so(self):
        (self.folder / ".env").unlink()
        w = self.window()
        items = self.checked(w)
        self.assertTrue(any("no company PIN is set" in e.summary for e in w.errors.entries))
        self.assertEqual([r.colour for r in items], [GREEN, GREEN, GREEN, YELLOW])
        self.assertIn("PIN: not required", w.status_strip.texts)
        self.assertFalse(w.status_strip.pin_yes.isEnabled())

    def test_an_unreadable_receipt_page_keeps_every_status_from_green(self):
        w = self.window()
        w.session._worker._reader.page_errors = {3}
        items = self.checked(w)
        self.assertEqual(items[2].reason, NOT_FOUND)
        self.assertIn("1 receipt page unread", w.status_strip.texts[0])
        self.assertIn("unread pages were not checked", w.status_strip.texts[2])

    def test_a_failure_inside_the_checking_is_reported_once_and_nothing_breaks(self):
        from unittest import mock
        from app.gui import claim_session
        w = self.window()
        with mock.patch.object(claim_session, "find_all", side_effect=RuntimeError("simulated")):
            self.click(w, "claim.xlsx")
            self.click(w, "receipts.pdf")
            wait_until(lambda: False, 0.1)
        self.assertIsNone(w.claims.result)
        errors = [e for e in w.errors.entries if "checking:" in e.summary]
        self.assertEqual(len(errors), 1)
        self.assertIn("simulated", errors[0].full_text)
        self.assertNotIn("100.00", errors[0].full_text, "no claim values in an error")

    def test_unusable_checking_rules_say_why_the_claim_is_not_checked(self):
        from unittest import mock
        from app.errors import StageError
        from app.gui import claim_session
        broken = StageError("config", "config file is not valid JSON", file="checking_rules.json")
        with mock.patch.object(claim_session, "load_checking_rules", side_effect=broken):
            w = self.window()
        self.click(w, "claim.xlsx")
        self.assertIn("cannot be checked", w.sheet_grid.reason.text())
        self.assertTrue(any("checking_rules.json" in e.summary for e in w.errors.entries))

    def test_the_bottom_tabs_keep_the_ocr_text_and_the_search(self):
        w = self.window()
        self.assertEqual([w.bottom_tabs.tabText(i) for i in range(w.bottom_tabs.count())], ["OCR text", "Search"])


if __name__ == "__main__":
    unittest.main()
