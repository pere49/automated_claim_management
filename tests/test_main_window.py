"""The Stage A window (main_window.py and its panes), off-screen, with FakeReader."""

from __future__ import annotations

import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.qt import qt_app, wait_until  # sets the off-screen platform first

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPushButton

from app.errors import StageError
from app.gui import application
from app.gui.application import build_window, install_exception_hook
from app.gui.main_window import MainWindow
from app.gui.settings import load_settings
from app.gui.startup_failure_window import StartupFailureWindow
from tests.fakes import FakeReader, make_pdf


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
        self.assertEqual(w.ocr_panel.text, "TOTAL    100.00\nTHANK YOU")
        self.assertEqual(sum(1 for name, _ in reader.pages_read if name == "A.PDF"), 3)


class OpeningAndPagingTests(WindowTestCase):
    def test_opening_shows_first_page_and_its_reading(self):
        w = self.window()
        self.open(w, "b.pdf")
        self.assertEqual(w.page_pane.position_text, "Page 1 of 3")
        self.assertEqual(w.ocr_panel.text, "TOTAL    100.00\nTHANK YOU")
        self.assertIn("3 text segments in 2 rows", w.ocr_panel.status)
        self.assertIn("b.pdf: 3 of 3 pages read.", w._status.text())

    def test_raw_previous_and_next_stay_within_the_document(self):
        w = self.window()
        self.open(w, "b.pdf")
        for _ in range(5):
            w.page_pane.next_requested.emit()
        self.assertEqual(w.page_pane.position_text, "Page 3 of 3")
        self.assertIn("300.00", w.ocr_panel.text)
        for _ in range(5):
            w.page_pane.previous_requested.emit()
        self.assertEqual(w.page_pane.position_text, "Page 1 of 3")

    def test_page_shows_at_once_while_its_text_is_still_being_read(self):
        w = self.window(FakeReader(delay=0.3))
        w.files.file_chosen.emit(self.folder / "b.pdf")
        w.page_pane.next_requested.emit()
        w.page_pane.next_requested.emit()
        self.assertEqual(w.page_pane.position_text, "Page 3 of 3")
        self.assertIn("Being read", w.ocr_panel.status)
        self.assertTrue(wait_until(lambda: "300.00" in w.ocr_panel.text))

    def test_failed_page_says_so_in_the_ocr_panel(self):
        w = self.window(FakeReader(page_errors={2}))
        self.open(w, "b.pdf")
        w.page_pane.next_requested.emit()
        self.assertIn("could not be read", w.ocr_panel.status)
        self.assertEqual(w.ocr_panel.text, "")
        self.assertIn("1 could not be read", w._status.text())
        self.assertEqual(len(w.errors.entries), 1)

    def test_file_the_reader_cannot_load_shows_message_and_error(self):
        w = self.window(FakeReader(load_error=True))
        self.open(w, "b.pdf")
        self.assertIn("Could not read b.pdf", w._status.text())
        self.assertIn("could not be read", w.ocr_panel.status)
        self.assertIn("load", w.errors.entries[0].summary)

    def test_corrupt_file_is_refused_and_the_open_file_stays(self):
        (self.folder / "c.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
        w = self.window()
        self.open(w, "b.pdf")
        w.files.file_chosen.emit(self.folder / "c.pdf")
        self.assertEqual(w.session.path, self.folder / "b.pdf")
        self.assertEqual(w.page_pane.position_text, "Page 1 of 3")
        self.assertIn("display", w.errors.entries[0].summary)


class SwitchingFilesTests(WindowTestCase):
    def test_switching_files_asks_nothing_and_loses_nothing(self):
        reader = FakeReader()
        w = self.window(reader)
        self.open(w, "b.pdf")
        self.open(w, "A.PDF")
        self.open(w, "b.pdf")
        self.assertEqual(self.questions, [])
        self.assertEqual(w.ocr_panel.text, "TOTAL    100.00\nTHANK YOU")
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


class StageScopeTests(WindowTestCase):
    def test_search_is_present_but_not_active(self):
        w = self.window()
        self.assertFalse(w.search_panel.search_button.isEnabled())
        for field in (w.search_panel.date_or_keyword, w.search_panel.pin, w.search_panel.total_amount):
            self.assertTrue(field.isVisible())

    def test_no_verify_decline_or_excel_row_controls(self):
        w = self.window()
        labels = {b.text().lower() for b in w.findChildren(QPushButton)}
        for absent in ("verify", "decline", "next row", "previous row"):
            self.assertFalse(any(absent in label for label in labels), absent)


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
