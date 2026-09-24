"""The window (main_window.py and its panes), off-screen, with FakeReader.

Fake pages read "TOTAL n00.00" / "THANK YOU" / "DATE:0n/08/2026", plus
"PIN: A012345678Z" on even pages (tests/fakes.py) — all fabricated.
"""

from __future__ import annotations

import dataclasses
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app.tests.qt import qt_app, wait_until  # sets the off-screen platform first

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QPushButton

from app.errors import StageError
from app.gui import application, search_controller
from app.gui.application import build_window, install_exception_hook
from app.gui.main_window import MainWindow
from app.gui.settings import load_settings
from app.gui.startup_failure_window import StartupFailureWindow
from app.tests.fakes import FAKE_PIN, FakeReader, make_pdf


class WindowTestCase(unittest.TestCase):
    def setUp(self):
        qt_app()
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)
        make_pdf(self.folder / "b.pdf", 3)
        make_pdf(self.folder / "A.PDF", 3)
        for name in ["claim.xlsx", "photo.jpg", "notes.txt"]:
            (self.folder / name).write_bytes(b"synthetic")
        (self.folder / "sub.pdf").mkdir()  # a folder, not a file
        self.answers: list[bool] = []
        self.questions: list[str] = []

    def tearDown(self):
        self._dir.cleanup()

    def window(self, reader: FakeReader | None = None, folder: Path | None = None,
               read_ahead: bool = False) -> MainWindow:
        settings = dataclasses.replace(load_settings(), working_folder=folder or self.folder, read_ahead=read_ahead)
        w = MainWindow(settings, reader or FakeReader())
        w.confirm = self._confirm
        w.resize(1280, 800)
        w.show()
        w.start()
        self.addCleanup(self._close, w)
        return w

    def _confirm(self, title: str, text: str) -> bool:
        self.questions.append(title)
        return self.answers.pop(0) if self.answers else True

    def _close(self, w: MainWindow) -> None:
        w.confirm = lambda *a: True
        w.close()

    def open(self, w: MainWindow, name: str) -> None:
        w.files.file_chosen.emit(self.folder / name)
        self.assertTrue(wait_until(lambda: not w.session.busy), "the document never finished")
        wait_until(lambda: False, 0.05)  # let the view settle

    def search(self, w: MainWindow, when: date | None = None, amount: str = "", pin: str = "") -> None:
        panel = w.search_panel
        panel.date_field.setDate(QDate(when.year, when.month, when.day) if when else panel.date_field.minimumDate())
        panel.amount.setText(amount)
        panel.pin.setText(pin)
        panel.search_button.click()
        wait_until(lambda: False, 0.05)


class FileListTests(WindowTestCase):
    def test_lists_only_claim_documents_by_name(self):
        w = self.window()  # Excel (until Stage C), text files and folders are not listed
        self.assertEqual(w.files.file_names(), ["A.PDF", "b.pdf", "photo.jpg"])

    def test_missing_working_folder_is_an_error_not_a_crash(self):
        w = self.window(folder=self.folder / "does-not-exist")
        self.assertEqual(w.files.file_names(), [])
        self.assertEqual(len(w.errors.entries), 1)
        self.assertIn("] files: ", w.errors.entries[0].summary)
        self.assertEqual(w.tabs.tabText(1), "Errors (1)")

    def test_file_list_can_be_hidden_and_shown(self):
        w = self.window()
        w.toggle_files.setChecked(False)
        self.assertFalse(w.files.isVisible())
        w.toggle_files.setChecked(True)
        self.assertTrue(w.files.isVisible())

    def test_file_list_shows_which_files_are_read(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.assertEqual(w.files.state_of("b.pdf"), "read")
        self.assertEqual(w.files.state_of("A.PDF"), "")

    def test_read_ahead_reads_the_other_files_in_the_background(self):
        reader = FakeReader()
        w = self.window(reader, read_ahead=True)
        self.assertTrue(wait_until(lambda: w.files.state_of("A.PDF") == "read" and w.files.state_of("b.pdf") == "read"))
        self.open(w, "A.PDF")
        self.assertTrue(w.ocr_panel.text.startswith("TOTAL    100.00"))
        self.assertEqual(sum(1 for name, _ in reader.pages_read if name == "A.PDF"), 3)


class ViewerTests(WindowTestCase):
    def test_opening_shows_the_first_page_and_its_reading(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.assertEqual(w.page_pane.position_text, "Page 1 of 3")
        self.assertEqual(w.ocr_panel.text, "TOTAL    100.00\nTHANK YOU\nDATE:01/08/2026")
        self.assertIn("4 text segments in 3 rows", w.ocr_panel.status)
        self.assertIn("b.pdf: 3 of 3 pages read.", w._status.text())

    def test_previous_and_next_page_move_through_the_scroll(self):
        w = self.window()
        self.open(w, "b.pdf")
        for expected in (2, 3, 3):
            w.page_pane._next.click()
            wait_until(lambda: False, 0.05)
            self.assertEqual(w.page_pane.current_page, expected)
        self.assertEqual(w.page_pane.position_text, "Page 3 of 3")
        self.assertIn("300.00", w.ocr_panel.text, "the OCR panel follows the page in view")
        for _ in range(3):
            w.page_pane._prev.click()
            wait_until(lambda: False, 0.05)
        self.assertEqual(w.page_pane.current_page, 1)

    def test_scrolling_changes_the_page_in_view(self):
        w = self.window()
        self.open(w, "b.pdf")
        bar = w.page_pane.view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 3))
        self.assertIn("300.00", w.ocr_panel.text)

    def test_only_pages_near_the_screen_are_drawn(self):
        make_pdf(self.folder / "long.pdf", 12)
        w = self.window()
        self.open(w, "long.pdf")
        drawn = w.page_pane.view.drawn_pages
        self.assertIn(1, drawn)
        self.assertLessEqual(len(drawn), 5, f"too many pages kept in memory: {drawn}")
        w.page_pane.go_to_page(12)
        self.assertTrue(wait_until(lambda: 12 in w.page_pane.view.drawn_pages))
        self.assertNotIn(1, w.page_pane.view.drawn_pages, "far pages must be released")

    def test_page_shows_at_once_while_its_text_is_still_being_read(self):
        w = self.window(FakeReader(delay=0.3))
        w.files.file_chosen.emit(self.folder / "b.pdf")
        wait_until(lambda: False, 0.05)
        w.page_pane.go_to_page(3)
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 3))
        self.assertIn("Being read", w.ocr_panel.status)
        self.assertTrue(wait_until(lambda: "300.00" in w.ocr_panel.text))

    def test_failed_page_says_so_in_the_ocr_panel(self):
        w = self.window(FakeReader(page_errors={2}))
        self.open(w, "b.pdf")
        w.page_pane.go_to_page(2)
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 2))
        self.assertIn("could not be read", w.ocr_panel.status)
        self.assertIn("1 could not be read", w._status.text())
        self.assertEqual(len(w.errors.entries), 1)

    def test_file_the_reader_cannot_load_shows_message_and_error(self):
        w = self.window(FakeReader(load_error=True))
        self.open(w, "b.pdf")
        self.assertIn("Could not read b.pdf", w._status.text())
        self.assertIn("load", w.errors.entries[-1].summary)

    def test_corrupt_file_is_refused_and_the_open_file_stays(self):
        (self.folder / "c.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
        w = self.window()
        self.open(w, "b.pdf")
        w.files.file_chosen.emit(self.folder / "c.pdf")
        self.assertEqual(w.session.path, self.folder / "b.pdf")
        self.assertEqual(w.page_pane.position_text, "Page 1 of 3")
        self.assertIn("display", w.errors.entries[0].summary)

    def test_a_page_that_cannot_be_drawn_is_reported_once(self):
        w = self.window()
        reported = []
        w.page_pane.problem.connect(lambda e, level: reported.append(e.page))

        def cannot_draw(number):
            raise StageError("display", "could not display this page")

        with mock.patch.object(w.session, "render", side_effect=cannot_draw):
            self.open(w, "b.pdf")
            for page in (2, 3, 1, 2):
                w.page_pane.go_to_page(page)
                wait_until(lambda: False, 0.1)
        self.assertEqual(sorted(reported), [1, 2, 3], "each page that cannot be drawn is reported once, by number")


class SwitchingFilesTests(WindowTestCase):
    def test_switching_files_asks_nothing_and_loses_nothing(self):
        reader = FakeReader()
        w = self.window(reader)
        self.open(w, "b.pdf")
        self.open(w, "A.PDF")
        self.open(w, "b.pdf")
        self.assertEqual(self.questions, [])
        self.assertTrue(w.ocr_panel.text.startswith("TOTAL    100.00"))
        self.assertEqual(sum(1 for name, _ in reader.pages_read if name == "b.pdf"), 3, "b.pdf was read twice")

    def test_switching_while_still_reading_resumes_later(self):
        reader = FakeReader(delay=0.05)
        make_pdf(self.folder / "b.pdf", 12)
        w = self.window(reader)
        w.files.file_chosen.emit(self.folder / "b.pdf")
        self.assertTrue(wait_until(lambda: w.session.pages_read() >= 1))
        self.open(w, "A.PDF")
        self.open(w, "b.pdf")
        self.assertEqual(sorted(n for name, n in reader.pages_read if name == "b.pdf"), list(range(1, 13)))

    def test_clicking_the_open_file_again_does_nothing(self):
        reader = FakeReader()
        w = self.window(reader)
        self.open(w, "b.pdf")
        w.files.file_chosen.emit(self.folder / "b.pdf")
        self.assertEqual(len(reader.pages_read), 3)

    def test_closing_with_readings_asks_first(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.answers = [False]
        w.close()
        self.assertTrue(w.isVisible())
        self.assertEqual(self.questions, ["Close the application?"])

    def test_closing_with_nothing_read_does_not_ask(self):
        w = self.window()
        w.close()
        self.assertEqual(self.questions, [])
        self.assertFalse(w.isVisible())


class SearchTests(WindowTestCase):
    def test_all_three_keys_found_shows_that_page_with_highlights(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, date(2026, 8, 2), "200", FAKE_PIN)
        self.assertEqual(w.page_pane.current_page, 2)
        lines = w.search_panel.result_lines
        self.assertIn("Date 02/08/2026: found on page 2 (1 place)", lines)
        self.assertIn("Amount 200.00: found on page 2 (1 place)", lines)
        self.assertIn(f"PIN {FAKE_PIN}: found on page 2 (1 place)", lines)
        self.assertIn("Every searched key is on page 2; showing page 2.", lines)
        self.assertIn("Searched all 3 pages.", lines)
        self.assertGreaterEqual(w.page_pane.view.highlight_count, 3)
        self.assertEqual(w.search_panel.match_position.text(), "match 1 of 3")

    def test_search_covers_every_page_and_steps_through_matches(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, pin=FAKE_PIN)  # only on page 2 of 3 — add a 4-page file for two places
        make_pdf(self.folder / "four.pdf", 4)
        self.open(w, "four.pdf")
        self.search(w, pin=FAKE_PIN)
        self.assertIn(f"PIN {FAKE_PIN}: found on pages 2 and 4 (2 places)", w.search_panel.result_lines)
        self.assertEqual(w.page_pane.current_page, 2)
        w.search_panel.next_button.click()
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 4))
        self.assertEqual(w.search_panel.match_position.text(), "match 2 of 2")
        w.search_panel.next_button.click()
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 2), "Next match wraps round")

    def test_no_page_with_every_key_shows_the_best_and_says_so(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, date(2026, 8, 3), "200", "")
        self.assertIn("No page has every searched key; showing page 2 (1 of 2 keys).", w.search_panel.result_lines)

    def test_nothing_found_moves_nothing(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, amount="999")
        self.assertIn("Amount 999.00: not found", w.search_panel.result_lines)
        self.assertIn("Nothing found.", w.search_panel.result_lines)
        self.assertEqual(w.page_pane.view.highlight_count, 0)
        self.assertEqual(w.page_pane.current_page, 1)

    def test_invalid_input_is_explained_and_not_searched(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, amount="1.200")
        self.assertIn("ambiguous", w.search_panel.message.text())
        self.assertNotIn("1.200", w.search_panel.message.text())
        self.assertEqual(w.search_panel.result_lines, [])
        self.search(w)
        self.assertIn("at least one", w.search_panel.message.text())

    def test_search_without_a_document_asks_for_one(self):
        w = self.window()
        self.search(w, amount="100")
        self.assertEqual(w.search_panel.message.text(), "Open a file first.")

    def test_search_updates_as_pages_are_read(self):
        w = self.window(FakeReader(delay=0.25))
        w.files.file_chosen.emit(self.folder / "b.pdf")
        self.assertTrue(wait_until(lambda: w.session.pages_read() >= 1))
        self.search(w, amount="300")
        self.assertTrue(any("still reading" in line for line in w.search_panel.result_lines))
        self.assertTrue(wait_until(lambda: "Amount 300.00: found on page 3 (1 place)" in w.search_panel.result_lines))
        self.assertTrue(wait_until(lambda: w.page_pane.current_page == 3), "the first find is brought into view")
        self.assertTrue(wait_until(lambda: "Searched all 3 pages." in w.search_panel.result_lines))

    def test_moving_through_pages_does_not_search_again(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, amount="100")
        with mock.patch.object(w.search, "run") as run:
            w.page_pane.go_to_page(3)
            wait_until(lambda: False, 0.1)
        run.assert_not_called()

    def test_clear_removes_results_highlights_and_fields(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, amount="100")
        w.search_panel.clear_button.click()
        self.assertEqual(w.page_pane.view.highlight_count, 0)
        self.assertEqual(w.search_panel.result_lines, [])
        self.assertEqual(w.search_panel.amount.text(), "")

    def test_opening_another_file_clears_the_search(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, amount="100")
        self.open(w, "A.PDF")
        self.assertEqual(w.page_pane.view.highlight_count, 0)
        self.assertEqual(w.search_panel.result_lines, [])

    def test_a_page_that_cannot_be_searched_is_reported_once_and_the_rest_are_searched(self):
        w = self.window()
        real = search_controller.prepare_page

        def failing(rows, rules):
            if rows and rows[0].text.startswith("TOTAL    200.00"):
                raise RuntimeError("simulated")
            return real(rows, rules)

        with mock.patch.object(search_controller, "prepare_page", side_effect=failing):
            self.open(w, "b.pdf")
            self.search(w, date(2026, 8, 3))
            self.search(w, amount="300")
            self.search(w, date(2026, 8, 3))
        self.assertIn("Date 03/08/2026: found on page 3 (1 place)", w.search_panel.result_lines)
        matching = [e for e in w.errors.entries if "matching" in e.summary]
        self.assertEqual(len(matching), 1)
        self.assertIn("page 2", matching[0].summary)
        self.assertNotIn("03/08/2026", matching[0].full_text)

    def test_pages_are_prepared_before_the_search_so_searching_is_only_lookups(self):
        w = self.window()
        self.open(w, "b.pdf")
        wait_until(lambda: False, 0.1)
        with mock.patch.object(search_controller, "prepare_page") as prepare:
            self.search(w, amount="200")
        prepare.assert_not_called()
        self.assertIn("Amount 200.00: found on page 2 (1 place)", w.search_panel.result_lines)

    def test_a_match_without_a_page_position_is_reported_not_silently_dropped(self):
        w = self.window(FakeReader(no_page_boxes=True))
        self.open(w, "b.pdf")
        self.search(w, amount="200")
        self.assertIn("Amount 200.00: found on page 2 (1 place)", w.search_panel.result_lines)
        self.assertEqual(w.page_pane.view.highlight_count, 0)
        self.assertTrue(any("could not be placed" in e.summary for e in w.errors.entries))
        self.assertEqual(w.page_pane.current_page, 2, "the page is still brought into view")

    def test_unusable_matching_rules_disable_search_and_say_why(self):
        broken = StageError("config", "config file is not valid JSON", file="matching_rules.json")
        with mock.patch.object(search_controller, "load_matching_rules", side_effect=broken):
            w = self.window()
        self.assertFalse(w.search_panel.search_button.isEnabled())
        self.assertIn("unavailable", w.search_panel.message.text())
        self.assertIn("matching_rules.json", w.errors.entries[0].summary)


class StageScopeTests(WindowTestCase):
    def test_no_verify_decline_or_excel_row_controls(self):
        w = self.window()
        labels = {b.text().lower() for b in w.findChildren(QPushButton)}
        for absent in ("verify", "decline", "next row", "previous row"):
            self.assertFalse(any(absent in label for label in labels), absent)

    def test_no_verdict_is_shown(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.search(w, date(2026, 8, 2), "200", FAKE_PIN)
        text = " ".join(w.search_panel.result_lines).upper()
        for verdict in ("PASS", "CAUTION", "REVIEW"):
            self.assertNotIn(verdict, text)


class ErrorBoundaryTests(WindowTestCase):
    def test_exception_in_a_slot_goes_to_the_error_tab(self):
        w = self.window()
        saved = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", saved)
        install_exception_hook(w.report)

        def broken_slot():
            raise RuntimeError("deliberate failure in a window slot")

        QTimer.singleShot(0, broken_slot)
        self.assertTrue(wait_until(lambda: w.errors.entries))
        entry = w.errors.entries[0]
        self.assertIn("gui:", entry.summary)
        self.assertIn("deliberate failure", entry.full_text)
        self.assertIn("Traceback", entry.full_text)

    def test_error_tab_newest_first_and_counted(self):
        w = self.window()
        w.report(StageError("ocr", "first"))
        w.report(StageError("ocr", "second"))
        self.assertEqual(w.tabs.tabText(1), "Errors (2)")
        self.assertIn("second", w.errors._list.item(0).text())

    def test_broken_settings_open_the_startup_failure_window(self):
        broken = StageError("config", "config file is not valid JSON", file="gui_settings.json")
        with mock.patch.object(application, "load_settings", side_effect=broken):
            window = build_window()
        self.addCleanup(window.close)
        self.assertIsInstance(window, StartupFailureWindow)
        self.assertIn("gui_settings.json", window.errors.entries[0].summary)


if __name__ == "__main__":
    unittest.main()
