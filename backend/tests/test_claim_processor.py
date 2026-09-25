from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.claim_processor import ClaimProcessor, _structure_table
from tests.fakes import FakeReader, make_pdf


class ClaimProcessorTests(unittest.TestCase):
    def test_page_failures_are_returned_without_stopping_other_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = make_pdf(Path(folder) / "claim.pdf", pages=2)
            result = ClaimProcessor(reader=FakeReader(page_errors={1})).process_claim(path)

        self.assertEqual(result.status, "done")
        self.assertEqual([page.page for page in result.pages], [1, 2])
        self.assertTrue(result.pages[0].errors)
        self.assertFalse(result.pages[1].errors)
        self.assertEqual(result.suggested_decision, "REVIEW")

    def test_start_failure_is_structured_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as folder:
            path = make_pdf(Path(folder) / "claim.pdf", pages=1)
            result = ClaimProcessor(reader=FakeReader(start_error=True)).process_claim(path)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.suggested_decision, "REVIEW")
        self.assertEqual(len(result.errors), 1)
        self.assertIn("startup", result.errors[0])

    def test_invalid_query_is_structured(self):
        with tempfile.TemporaryDirectory() as folder:
            path = make_pdf(Path(folder) / "claim.pdf", pages=1)
            result = ClaimProcessor(reader=FakeReader()).process_claim(
                path, claim_date="not-a-date"
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.suggested_decision, "REVIEW")
        self.assertIn("query", result.errors[0])

    def test_extracts_claim_fields_from_labelled_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = make_pdf(Path(folder) / "claim.pdf", pages=1)
            reader = FakeReader()
            reader.read_page = lambda page: type(
                "PageResult",
                (),
                {
                    "words": [
                        type("Word", (), {"text": "Claimant: Ada Lovelace", "confidence": 1, "box": [[1, 1], [2, 1], [2, 2], [1, 2]], "page_box": [[1, 1], [2, 1], [2, 2], [1, 2]]})(),
                        type("Word", (), {"text": "Project: Analytical Engine", "confidence": 1, "box": [[1, 3], [2, 3], [2, 4], [1, 4]], "page_box": [[1, 3], [2, 3], [2, 4], [1, 4]]})(),
                        type("Word", (), {"text": "Date: 2026-09-10", "confidence": 1, "box": [[1, 5], [2, 5], [2, 6], [1, 6]], "page_box": [[1, 5], [2, 5], [2, 6], [1, 6]]})(),
                        type("Word", (), {"text": "TOTAL", "confidence": 1, "box": [[1, 7], [2, 7], [2, 8], [1, 8]], "page_box": [[1, 7], [2, 7], [2, 8], [1, 8]]})(),
                        type("Word", (), {"text": "485.50", "confidence": 1, "box": [[3, 7], [4, 7], [4, 8], [3, 8]], "page_box": [[3, 7], [4, 7], [4, 8], [3, 8]]})(),
                    ],
                    "error": None,
                    "warning": None,
                },
            )()
            result = ClaimProcessor(reader=reader).process_claim(path)

        self.assertEqual(result.extracted["individual_name"], "Ada Lovelace")
        self.assertEqual(result.extracted["project_name"], "Analytical Engine")
        self.assertEqual(result.extracted["claim_date"], "2026-09-10")
        self.assertEqual(result.extracted["claimed_amount"], "485.50")

    def test_structures_expense_table_and_preserves_total(self):
        table = [
            ["Expense Card", None, "August 2026"],
            ["Cardholder", "Ada Lovelace", "Project", "Analytical Engine"],
            ["Date", "Description", "Amount"],
            ["2026-08-01", "Travel", "12.50"],
            ["2026-08-02", "Supplies", "7.50"],
            ["Total", None, "20.00"],
        ]

        result = _structure_table(table)

        self.assertEqual(result["header"], ["Expense Card", "August 2026"])
        self.assertEqual(result["Document Details"]["Cardholder"], "Ada Lovelace")
        self.assertEqual(result["data_columns"], ["Date", "Description", "Amount"])
        self.assertEqual(len(result["data_rows"]), 2)
        self.assertEqual(result["Total"], "20.00")


if __name__ == "__main__":
    unittest.main()
