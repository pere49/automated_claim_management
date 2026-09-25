"""The open document, its cache and the background OCR
(document_session.py, document_cache.py, ocr_worker.py).

Every failure path is forced on purpose with FakeReader: engine start-up,
file loading, one page failing, one page crashing the reader, unusable row
rules. The cache is tested for what it promises: nothing lost on switching,
only missing pages read on return, a changed file read again, the page on
screen read first, and read-ahead of the other files.
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.qt import qt_app, wait_until  # sets the off-screen platform first

from app.errors import ERROR, WARNING, StageError
from app.gui import document_session
from app.gui.document_session import DocumentSession
from app.gui.ocr_worker import FAILED, FINISHED
from app.gui.settings import load_settings
from tests.fakes import FakeReader, make_pdf


class SessionHarness:
    """A DocumentSession plus a record of everything it signalled."""

    def __init__(self, reader: FakeReader, read_ahead: bool = False) -> None:
        qt_app()
        self.reader = reader
        settings = dataclasses.replace(load_settings(), read_ahead=read_ahead)
        self.session = DocumentSession(settings, reader)
        self.problems: list[tuple[StageError, str]] = []
        self.outcomes: list[str] = []
        self.session.problem.connect(lambda e, level: self.problems.append((e, level)))
        self.session.finished.connect(self.outcomes.append)
        self.session.start()

    def open_and_wait(self, path: Path) -> str:
        count = len(self.outcomes)
        assert self.session.open(path), "the file could not be opened"
        assert wait_until(lambda: len(self.outcomes) > count), "the document never finished"
        return self.outcomes[-1]

    def reads_of(self, path: Path) -> list[int]:
        return [n for name, n in self.reader.pages_read if name == path.name]

    def stages(self) -> list[str]:
        return [e.stage for e, _ in self.problems]

    def close(self) -> None:
        self.session.shutdown()


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.folder = Path(self._dir.name)

    def pdf(self, name: str, pages: int) -> Path:
        return make_pdf(self.folder / name, pages)

    def harness(self, reader: FakeReader, read_ahead: bool = False) -> SessionHarness:
        h = SessionHarness(reader, read_ahead)
        self.addCleanup(h.close)
        return h


class ReadingTests(SessionTestCase):
    def test_reads_every_page_and_groups_rows(self):
        h = self.harness(FakeReader())
        self.assertEqual(h.open_and_wait(self.pdf("doc.pdf", 3)), FINISHED)
        self.assertEqual(h.session.pages_read(), 3)
        self.assertFalse(h.session.busy)
        page2 = h.session.reading(2)
        self.assertEqual([r.text for r in page2.rows],
                         ["TOTAL    200.00", "THANK YOU", "DATE:02/08/2026", "PIN: A012345678Z"])
        self.assertTrue(page2.rows_grouped)
        self.assertEqual(h.problems, [])

    def test_one_failing_page_does_not_stop_the_rest(self):
        h = self.harness(FakeReader(page_errors={2}))
        self.assertEqual(h.open_and_wait(self.pdf("doc.pdf", 3)), FINISHED)
        self.assertEqual(h.session.pages_read(), 3)
        self.assertIsNotNone(h.session.reading(2).result.error)
        self.assertEqual(len(h.session.reading(3).rows), 3)
        self.assertEqual([(e.stage, e.page, level) for e, level in h.problems], [("ocr", 2, ERROR)])

    def test_reader_crash_on_one_page_is_contained(self):
        h = self.harness(FakeReader(crash_pages={1}))
        self.assertEqual(h.open_and_wait(self.pdf("doc.pdf", 3)), FINISHED)
        error = h.session.reading(1).result.error
        self.assertEqual((error.stage, error.page), ("ocr", 1))
        self.assertIn("simulated crash", error.full_text)
        self.assertEqual(h.session.pages_read(), 3)

    def test_file_the_reader_cannot_load_fails_cleanly(self):
        h = self.harness(FakeReader(load_error=True))
        self.assertEqual(h.open_and_wait(self.pdf("broken.pdf", 2)), FAILED)
        self.assertEqual(h.session.pages_read(), 0)
        self.assertEqual(h.stages(), ["load"])

    def test_file_that_is_not_a_pdf_is_refused_before_reading(self):
        h = self.harness(FakeReader())
        bad = self.folder / "corrupt.pdf"
        bad.write_bytes(b"%PDF-1.4 not really a pdf")
        self.assertFalse(h.session.open(bad))
        self.assertIsNone(h.session.path)
        self.assertEqual(h.stages(), ["display"])
        self.assertEqual(h.reader.pages_read, [])

    def test_engine_that_cannot_start_fails_cleanly(self):
        h = self.harness(FakeReader(start_error=True))
        self.assertEqual(h.open_and_wait(self.pdf("doc.pdf", 1)), FAILED)
        self.assertIn("startup", h.stages())
        self.assertTrue(all(level == ERROR for _, level in h.problems))

    def test_unusable_row_rules_fall_back_to_ungrouped_text(self):
        broken = StageError("config", "config file is not valid JSON", file="row_rules.json")
        with mock.patch.object(document_session, "load_row_rules", side_effect=broken):
            h = self.harness(FakeReader())
        self.assertEqual(h.open_and_wait(self.pdf("doc.pdf", 1)), FINISHED)
        page = h.session.reading(1)
        self.assertFalse(page.rows_grouped)
        self.assertEqual(len(page.rows), 4)  # one per segment, nothing lost
        self.assertEqual(h.stages(), ["config"])

    def test_grouping_failure_on_a_page_is_a_warning_not_a_loss(self):
        def failing_group_rows(*_args):
            raise StageError("layout", "text segment 1 has an unusable position box")

        with mock.patch.object(document_session, "group_rows", side_effect=failing_group_rows):
            h = self.harness(FakeReader())
            self.assertEqual(h.open_and_wait(self.pdf("doc.pdf", 2)), FINISHED)
        self.assertEqual([(e.stage, e.page, level) for e, level in h.problems],
                         [("layout", 1, WARNING), ("layout", 2, WARNING)])
        self.assertEqual(len(h.session.reading(1).rows), 4)


class CacheTests(SessionTestCase):
    def test_reopening_a_read_file_reads_nothing_again(self):
        h = self.harness(FakeReader())
        first, second = self.pdf("first.pdf", 2), self.pdf("second.pdf", 2)
        h.open_and_wait(first)
        h.open_and_wait(second)
        self.assertEqual(h.open_and_wait(first), FINISHED)
        self.assertEqual(h.reads_of(first), [1, 2], "a cached file must not be read twice")
        self.assertEqual(h.session.pages_read(), 2)

    def test_switching_mid_read_keeps_finished_pages_and_resumes_the_rest(self):
        h = self.harness(FakeReader(delay=0.05))
        first, second = self.pdf("first.pdf", 8), self.pdf("second.pdf", 2)
        h.session.open(first)
        self.assertTrue(wait_until(lambda: h.session.pages_read() >= 2))
        self.assertEqual(h.open_and_wait(second), FINISHED)
        read_before = len(h.reads_of(first))
        self.assertLess(read_before, 8, "the first file should have been interrupted")
        self.assertEqual(h.session.cache.get(first).pages_read, read_before, "finished pages were lost")
        self.assertEqual(h.open_and_wait(first), FINISHED)
        self.assertEqual(sorted(h.reads_of(first)), list(range(1, 9)), "each page read exactly once")

    def test_a_file_changed_on_disk_is_read_again(self):
        h = self.harness(FakeReader())
        doc, other = self.pdf("doc.pdf", 1), self.pdf("other.pdf", 1)
        h.open_and_wait(doc)
        h.open_and_wait(other)
        make_pdf(doc, 2)                                   # replaced with a different file
        stat = doc.stat()
        os.utime(doc, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        self.assertEqual(h.open_and_wait(doc), FINISHED)
        self.assertEqual(h.session.page_count, 2)
        self.assertEqual(h.reads_of(doc), [1, 1, 2])

    def test_failed_pages_are_retried_when_the_file_is_opened_again(self):
        reader = FakeReader(page_errors={2})
        h = self.harness(reader)
        doc, other = self.pdf("doc.pdf", 3), self.pdf("other.pdf", 1)
        h.open_and_wait(doc)
        h.open_and_wait(other)
        reader.page_errors = set()                         # the problem has gone away
        h.open_and_wait(doc)
        self.assertEqual(h.reads_of(doc), [1, 2, 3, 2])
        self.assertIsNone(h.session.reading(2).result.error)

    def test_page_on_screen_is_read_next(self):
        h = self.harness(FakeReader(delay=0.05))
        doc = self.pdf("doc.pdf", 8)
        h.session.open(doc)
        self.assertTrue(wait_until(lambda: h.session.pages_read() >= 1))
        h.session.set_viewed_page(7)
        self.assertTrue(wait_until(lambda: not h.session.busy))
        order = h.reads_of(doc)
        self.assertLessEqual(order.index(7), 2, f"page 7 should be read almost at once, order was {order}")
        self.assertEqual(sorted(order), list(range(1, 9)))


class ReadAheadTests(SessionTestCase):
    def test_other_files_are_read_in_the_background(self):
        h = self.harness(FakeReader(), read_ahead=True)
        files = [self.pdf(f"{c}.pdf", 2) for c in "abc"]
        h.session.set_read_ahead_files(files)
        self.assertTrue(wait_until(lambda: all(h.session.cache.get(f) and h.session.cache.get(f).complete
                                               for f in files)))
        self.assertEqual(h.open_and_wait(files[1]), FINISHED)
        self.assertEqual(h.reads_of(files[1]), [1, 2], "an already read file must open without reading")

    def test_opening_a_file_takes_over_from_read_ahead(self):
        h = self.harness(FakeReader(delay=0.05), read_ahead=True)
        background, wanted = self.pdf("a.pdf", 20), self.pdf("z.pdf", 2)
        h.session.set_read_ahead_files([background, wanted])
        self.assertTrue(wait_until(lambda: h.reads_of(background)))
        self.assertEqual(h.open_and_wait(wanted), FINISHED)
        self.assertLess(len(h.reads_of(background)), 20, "read-ahead should have yielded")
        self.assertTrue(wait_until(lambda: h.session.cache.get(background).complete),
                        "read-ahead should resume afterwards")

    def test_a_broken_file_is_not_retried_in_a_loop(self):
        h = self.harness(FakeReader(load_error=True), read_ahead=True)
        h.session.set_read_ahead_files([self.pdf("a.pdf", 1), self.pdf("b.pdf", 1)])
        self.assertTrue(wait_until(lambda: h.stages().count("load") >= 2))
        wait_until(lambda: False, 0.5)  # give any unwanted retry time to happen
        self.assertEqual(h.stages().count("load"), 2)


if __name__ == "__main__":
    unittest.main()
