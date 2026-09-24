"""The window in Stage C: claim sheet shown as its PDF with row buttons, badges, status line, tour (off-screen).

Receipts are read by FakeReader: page n reads "TOTAL n00.00" / "DATE:0n/08/2026",
with "PIN: A012345678Z" on even pages. The claim sheet is a synthetic PDF in the
owner's template layout (tests/claim_fixtures.py). All values fabricated.

With the PIN required (it is on pages 2 and 4), the five claimed amounts are:
    row 1  Dinner 100 (1 Aug)  -> page 1, no PIN            red    "PIN missing"
    row 2  Lunch  200 (2 Aug)  -> page 2                    green
    row 2  Dinner 400 (2 Aug)  -> page 4, dated 4 Aug       yellow "Date 04 Aug ≠ 02 Aug"
    row 3  Travel 300 (3 Aug)  -> page 3, no PIN            red
    row 4  Hotel  999 (13 Aug) -> no page                   red    "No receipt found"
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from tests.qt import qt_app, wait_until  # sets the off-screen platform first

from app.checking import GREEN, P_NO_RECEIPT, RED, YELLOW
from app.gui.main_window import MainWindow
from app.gui.settings import load_settings
from tests.claim_fixtures import form_grid, write_pdf_form
from tests.fakes import FAKE_PIN, FakeReader, make_pdf

ENTRIES = [
    (datetime(2026, 8, 1), "Meals", {"Dinner": 100}),
    (datetime(2026, 8, 2), "Meals", {"Lunch": 200, "Dinner": 400}),
    (datetime(2026, 8, 3), "Taxi", {"Travel": 300}),
    (datetime(2026, 8, 13), "Hotel", {"Hotel": 999}),
]


class ClaimWindowTestCase(unittest.TestCase):
    def setUp(self):
        qt_app()
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)
        make_pdf(self.folder / "receipts.pdf", 4)
        write_pdf_form(self.folder / "claim.pdf", form_grid(ENTRIES))
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
        self.click(w, "claim.pdf")
        self.click(w, "receipts.pdf")
        self.assertTrue(wait_until(lambda: w.claims.result is not None), "the claim was never checked")
        return w.claims.result.items

    def rows(self, w: MainWindow) -> list[int]:
        """The claim rows' grid rows, top to bottom."""
        return [row.grid_row for row in w.claims.sheet.rows]

    def button_colours(self, w: MainWindow) -> list[str]:
        return [w.sheet_view.buttons[r].colour_name for r in self.rows(w)]


class SlotAndCheckTests(ClaimWindowTestCase):
    def test_a_claim_sheet_pdf_is_shown_as_itself_with_a_button_per_row(self):
        w = self.window()
        self.click(w, "claim.pdf")
        self.assertEqual(w.claims.sheet_path, self.folder / "claim.pdf")
        self.assertIn("claim.pdf", w.files.sheet_slot.text())
        self.assertIsNone(w.session.path, "a claim sheet is not opened as receipts")
        self.assertEqual(len(w.claims.sheet.items), 5)
        self.assertIsNotNone(w.sheet_view.canvas.picture, "the sheet's page is drawn")
        self.assertEqual(sorted(w.sheet_view.buttons), self.rows(w))
        self.assertTrue(all(b.colour_name == "grey" and not b.enabled for b in w.sheet_view.buttons.values()))
        self.assertIn("Choose the receipts PDF", w.sheet_view.message.text())

    def test_the_claim_is_checked_when_the_receipts_have_been_read(self):
        w = self.window()
        items = self.checked(w)
        self.assertEqual([r.colour for r in items], [RED, GREEN, YELLOW, RED, RED])
        self.assertEqual(w.status_cards.texts, {"Verification": "red: p. 1, 3, 4 | 1 no receipt",
                                                "Total grand": "red: Not matched | 200.00 of 1,999.00",
                                                "Repeated": "green: none"})
        self.assertTrue(w.receipts_header.pin_toggle.isChecked(), "the PIN is on a page: the toggle starts on")
        self.assertEqual(w.receipts_header.pin_state, "on: red", "on, and red: the PIN is missing on some receipts")
        self.assertEqual((w.status_cards.verification.value.full_text, w.status_cards.repeats.value.full_text),
                         ("p. 1, 3, 4", "None"), "page lists as they are, words capitalised")
        self.assertEqual(self.button_colours(w), [RED, YELLOW, RED, RED])
        self.assertFalse(w.sheet_view.message.isVisible())

    def test_every_receipt_page_carries_its_badge(self):
        w = self.window()
        self.checked(w)
        badges = w.page_pane.view.badges
        self.assertEqual({n: b.lines for n, b in badges.items()},
                         {1: ("PIN missing",), 2: ("✓",), 3: ("PIN missing",), 4: ("Date 04 Aug ≠ 02 Aug",)})
        colours = w._settings.status_colours
        self.assertEqual({n: b.fill.name() for n, b in badges.items()},
                         {1: colours[RED], 2: colours[GREEN], 3: colours[RED], 4: colours[YELLOW]})

    def test_failed_amounts_are_tinted_and_one_with_no_receipt_says_so(self):
        w = self.window()
        items = self.checked(w)
        failed = [r for r in items if r.colour != GREEN]
        labels = [m for m in w.sheet_view.marks if m.childItems()]
        self.assertEqual(len(w.sheet_view.marks), len(failed) + 1)
        self.assertEqual([m.childItems()[0].text() for m in labels], ["No receipt found"])
        self.assertEqual(sum(P_NO_RECEIPT in r.problems for r in items), 1)

    def test_nothing_is_checked_before_every_receipt_page_has_been_read(self):
        w = self.window()
        w.session._worker._reader.delay = 0.3
        self.click(w, "claim.pdf")
        w.files.file_chosen.emit(self.folder / "receipts.pdf")
        seen = []
        w.claims.checked.connect(lambda result: seen.append((result is not None, w.session.pages_read())))
        self.assertTrue(wait_until(lambda: w.session.pages_read() >= 1))
        self.assertIsNone(w.claims.result)
        self.assertIn("Reading the receipts", w.sheet_view.message.text())
        self.assertEqual(w.page_pane.view.badges, {}, "no badges before the check")
        self.assertTrue(wait_until(lambda: w.claims.result is not None))
        self.assertTrue(all(pages == 4 for checked, pages in seen if checked), seen)

    def test_receipts_first_then_the_sheet_also_checks(self):
        w = self.window()
        self.click(w, "receipts.pdf")
        self.click(w, "claim.pdf")
        self.assertTrue(wait_until(lambda: w.claims.result is not None))
        self.assertIn("receipts.pdf", w.files.receipts_slot.text())

    def test_the_pin_switch_decides_again_without_searching(self):
        w = self.window()
        self.checked(w)
        w.receipts_header.pin_toggle.click()
        wait_until(lambda: False, 0.05)
        self.assertEqual([r.colour for r in w.claims.result.items], [GREEN, GREEN, YELLOW, GREEN, RED])
        self.assertEqual(w.receipts_header.pin_state, "off")
        self.assertEqual(self.button_colours(w), [GREEN, YELLOW, GREEN, RED])
        self.assertEqual(w.page_pane.view.badges[1].lines, ("✓",))

    def test_the_layout_titles_each_side_and_puts_the_cards_under_the_sheet(self):
        w = self.window()
        self.checked(w)
        self.assertIs(w.receipts_header.parentWidget(), w.page_pane.parentWidget())
        self.assertIs(w.status_cards.parentWidget(), w.sheet_view.parentWidget())
        self.assertLess(w.page_pane.parentWidget().layout().indexOf(w.receipts_header),
                        w.page_pane.parentWidget().layout().indexOf(w.page_pane), "the header is above the receipts")
        self.assertLess(w.sheet_view.parentWidget().layout().indexOf(w.sheet_view),
                        w.sheet_view.parentWidget().layout().indexOf(w.status_cards), "the cards are under the sheet")
        self.assertEqual(w.receipts_header.title.text(), "<b>Receipt claim:</b> receipts.pdf")
        self.assertEqual(w.sheet_view.title.text(), "<b>Claim sheet:</b> claim.pdf")
        self.assertEqual([c.title.text() for c in (w.status_cards.verification, w.status_cards.total,
                                                    w.status_cards.repeats)], ["VERIFICATION", "TOTAL GRAND", "REPEATED"])

    def test_a_long_list_of_failing_pages_never_widens_a_pane(self):
        from app.checking import Status
        w = self.window()
        self.checked(w)
        widths, least = w._review.sizes(), w.status_cards.minimumSizeHint().width()
        pages = "p. " + ", ".join(map(str, range(1, 80)))
        w.status_cards.show_check(dataclasses.replace(w.claims.result, verification=Status(RED, pages)))
        wait_until(lambda: False, 0.1)
        self.assertEqual(w.status_cards.minimumSizeHint().width(), least, "the words shrink, the cards do not grow")
        self.assertEqual(w._review.sizes(), widths)
        self.assertTrue(w.status_cards.verification.value.text().endswith("…"))
        self.assertEqual(w.status_cards.total.value.full_text, "Not matched")
        self.assertEqual(w.status_cards.texts["Verification"], f"red: {pages}")
        self.assertIn(pages, w.status_cards.verification.toolTip() + pages)


class ShowingTests(ClaimWindowTestCase):
    def test_a_row_button_shows_its_amounts_in_turn_and_comes_back_to_the_first(self):
        w = self.window()
        self.checked(w)
        button = w.sheet_view.buttons[self.rows(w)[1]]
        shown = []
        for _ in range(3):
            button.click()
            wait_until(lambda: False, 0.05)
            shown.append((w.sheet_view.current_item, w.page_pane.current_page))
        self.assertEqual(shown, [(1, 2), (2, 4), (1, 2)])
        self.assertEqual(w.sheet_view.current_row, self.rows(w)[1])

    def test_an_amount_with_no_receipt_is_shown_on_the_sheet_only(self):
        w = self.window()
        self.checked(w)
        w.sheet_view.buttons[self.rows(w)[3]].click()
        wait_until(lambda: False, 0.05)
        self.assertEqual(w.sheet_view.current_item, 4)
        self.assertIn("No receipt found", w._status.text())

    def test_every_claimed_amounts_highlights_stay_on_the_pages_while_scrolling(self):
        w = self.window()
        items = self.checked(w)
        expected = sum(len(r.hits) for r in items if r.page is not None)
        self.assertGreater(expected, 4)
        count = w.page_pane.view.highlight_count
        self.assertGreaterEqual(count, expected)
        for page in (4, 1, 3):
            w.page_pane.go_to_page(page)
            wait_until(lambda: False, 0.05)
            self.assertEqual(w.page_pane.view.highlight_count, count)

    def test_scrolling_the_receipts_brings_their_row_to_the_middle_of_the_sheet(self):
        w = self.window()
        w.resize(1400, 420)                          # a short window: the sheet has to scroll
        self.checked(w)
        rows = self.rows(w)
        w.page_pane.go_to_page(3)
        self.assertTrue(wait_until(lambda: w.sheet_view.current_row == rows[2]))
        w.page_pane.go_to_page(4)
        self.assertTrue(wait_until(lambda: w.sheet_view.current_row == rows[1]))
        where = w.sheet_view.canvas.verticalScrollBar().value()
        w.page_pane.go_to_page(2)                    # the same row's other receipt: the sheet does not move
        wait_until(lambda: w.page_pane.current_page == 2)
        wait_until(lambda: False, 0.1)
        self.assertEqual((w.sheet_view.current_row, w.sheet_view.canvas.verticalScrollBar().value()), (rows[1], where))

    def test_the_tour_walks_every_amount_and_stops_at_the_last(self):
        w = self.window()
        self.checked(w)
        shown = []
        w.tour.show_item.connect(shown.append)
        w.receipts_header.auto.click()
        self.assertTrue(wait_until(lambda: not w.tour.running and len(shown) == 5))
        self.assertEqual(shown, [0, 1, 2, 3, 4])
        self.assertEqual(w.receipts_header.auto.text(), "▶ Auto")

    def test_a_row_button_pauses_the_tour_and_auto_resumes_where_it_stopped(self):
        w = self.window(tour_green_ms=400, tour_yellow_ms=400)
        self.checked(w)
        shown = []
        w.tour.show_item.connect(shown.append)
        w.receipts_header.auto.click()
        self.assertTrue(wait_until(lambda: shown == [0]))
        w.sheet_view.buttons[self.rows(w)[3]].click()
        self.assertFalse(w.tour.running)
        w.receipts_header.auto.click()
        self.assertTrue(wait_until(lambda: len(shown) >= 2))
        self.assertEqual(shown[1], 1, "Auto resumes after the last amount the tour showed")

    def test_next_to_check_jumps_over_the_green_amounts(self):
        w = self.window()
        self.checked(w)
        shown = []
        w.tour.show_item.connect(shown.append)
        for _ in range(3):
            w.receipts_header.next.click()
        self.assertEqual(shown, [0, 2, 3])

    def test_the_tour_starts_by_itself_when_so_configured(self):
        w = self.window(tour_auto_start=True)
        shown = []
        w.tour.show_item.connect(shown.append)
        self.checked(w)
        self.assertTrue(wait_until(lambda: len(shown) == 5))


class FailureTests(ClaimWindowTestCase):
    def test_a_broken_claim_pdf_is_reported_and_nothing_breaks(self):
        (self.folder / "broken.pdf").write_bytes(b"not a pdf")
        w = self.window()
        w.files.sheet_requested.emit(self.folder / "broken.pdf")
        wait_until(lambda: False, 0.05)
        self.assertIsNone(w.claims.claim)
        self.assertTrue(any("claim sheet:" in e.summary and "broken.pdf" in e.summary for e in w.errors.entries))
        self.assertIn("Choose a claim sheet", w.sheet_view.message.text())

    def test_an_excel_file_is_refused_with_a_reason(self):
        (self.folder / "claim.xlsx").write_bytes(b"a workbook")
        w = self.window()
        self.assertNotIn("claim.xlsx", w.files.file_names())
        w.files.sheet_requested.emit(self.folder / "claim.xlsx")
        wait_until(lambda: False, 0.05)
        self.assertIsNone(w.claims.claim)
        self.assertTrue(any("use the PDF of the claim sheet" in e.summary for e in w.errors.entries))

    def test_a_claim_page_that_cannot_be_drawn_is_reported_and_the_claim_is_still_checked(self):
        from app.errors import StageError

        def broken(*args):
            raise StageError("display", "could not display this page", file="claim.pdf", page=1,
                             cause=RuntimeError("simulated"))

        w = self.window()
        w.sheet_view._render = broken
        items = self.checked(w)
        self.assertEqual(len(items), 5)
        self.assertIsNone(w.sheet_view.canvas.picture)
        self.assertIn("could not be drawn", w.sheet_view.message.text())
        self.assertTrue(any("display:" in e.summary and "simulated" in e.full_text for e in w.errors.entries))
        self.assertEqual(w.status_cards.texts["Total grand"], "red: Not matched | 200.00 of 1,999.00",
                         "the statuses still work")
        w.receipts_header.next.click()                   # the tour still works without the picture
        wait_until(lambda: False, 0.05)
        self.assertEqual((w.sheet_view.current_item, w.page_pane.current_page), (0, 1))

    def test_no_company_pin_file_turns_the_pin_checks_off_and_says_so(self):
        (self.folder / ".env").unlink()
        w = self.window()
        items = self.checked(w)
        self.assertTrue(any("no company PIN is set" in e.summary for e in w.errors.entries))
        self.assertEqual([r.colour for r in items], [GREEN, GREEN, YELLOW, GREEN, RED])
        self.assertEqual(w.receipts_header.pin_state, "off")
        self.assertFalse(w.receipts_header.pin_toggle.isEnabled())

    def test_an_unreadable_receipt_page_is_red_and_keeps_every_status_from_green(self):
        w = self.window()
        w.session._worker._reader.page_errors = {3}
        items = self.checked(w)
        self.assertIn(P_NO_RECEIPT, items[3].problems)
        self.assertEqual(w.page_pane.view.badges[3].lines, ("Unreadable",))
        self.assertIn("p. 1, 3", w.status_cards.texts["Verification"])
        self.assertEqual(w.status_cards.texts["Repeated"], "yellow: not checked")

    def test_a_failure_inside_the_checking_is_reported_once_and_nothing_breaks(self):
        from unittest import mock
        from app.gui import claim_session
        w = self.window()
        with mock.patch.object(claim_session, "find_all", side_effect=RuntimeError("simulated")):
            self.click(w, "claim.pdf")
            self.click(w, "receipts.pdf")
            wait_until(lambda: False, 0.1)
        self.assertIsNone(w.claims.result)
        errors = [e for e in w.errors.entries if "checking:" in e.summary]
        self.assertEqual(len(errors), 1)
        self.assertIn("simulated", errors[0].full_text)
        self.assertNotIn("100.00", errors[0].full_text, "no claim values in an error")
        self.assertEqual(w.page_pane.view.badges, {})

    def test_unusable_checking_rules_say_why_the_claim_is_not_checked(self):
        from unittest import mock
        from app.errors import StageError
        from app.gui import claim_session
        broken = StageError("config", "config file is not valid JSON", file="checking_rules.json")
        with mock.patch.object(claim_session, "load_checking_rules", side_effect=broken):
            w = self.window()
        self.click(w, "claim.pdf")
        self.assertIn("cannot be checked", w.sheet_view.message.text())
        self.assertTrue(any("checking_rules.json" in e.summary for e in w.errors.entries))

    def test_the_ocr_text_and_the_search_are_gone(self):
        from PySide6.QtWidgets import QTabWidget
        w = self.window()
        self.assertFalse(hasattr(w, "bottom_tabs") or hasattr(w, "search_panel") or hasattr(w, "ocr_panel"))
        self.assertEqual([t.tabText(i) for t in w.findChildren(QTabWidget) for i in range(t.count())],
                         ["Review", "Errors (0)"])


if __name__ == "__main__":
    unittest.main()
