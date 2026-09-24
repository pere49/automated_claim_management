"""PROTOTYPE (tools/) — duplicate receipt pages: which checks flag them safely?

    .venv/Scripts/python.exe tools/duplicate_pages_trial/run_trial.py

Uses the saved OCR readings of every hand-checked page (the two earlier
trials' outputs) and their answer keys: two pages whose answer-key entries
are identical show the same receipt (15 pairs, all DIFFERENT captures of it —
the hard case); every other pair is two different receipts (2,065 pairs).
The checks live in checks.py, their settings in trial_config.json; this file
only scores them, and confirms the pairwise and indexed forms agree.

Measured 2026-09-24:
  whole-page word overlap                     unsafe: same receipt as low as 0.45, different up to 0.72
  text: near-identical wording (>= 0.90)      6 of 15, 0 wrong; the same scan repeated always
  moment: same date + time + shared amount    8 of 15, 0 wrong
  references: ONE number on these two only    13 of 15, 5 wrong (a shop's PO box, a TIN, a till
              serial, an account number, a plate: numbers of a party, not of the sale) -> rejected
  references: TWO OR MORE such numbers        10 of 15, 0 wrong
  text + moment + references                  13 of 15, 0 of 2,065 wrong
  invoice: value after an invoice-type label  8 of 15, 0 wrong; a value read on only 23 of 65 pages;
           adds nothing to the three above (13 of 15 either way). Reading the value from the
           label's printed row instead: telebirr prints labels as a table-header row with the
           values beneath; loosening the value to 1+ digit (its invoice numbers are mostly
           letters) lets garbled Amharic labels through: 190 wrong flags -> rejected
CORRECTION, same day, measured one document at a time as the application runs
the check (the numbers above counted "rare" across all 65 pages of many files,
where a shop's own numbers are on more than two pages; inside one claim's PDF
two receipts from the same shop share them). Found by the Stage C dry run on
the real week-1 claim (a restaurant visited twice, a shop visited twice):
  references (2+ numbers)            10 of 15; wrong 2 inside a document, 15 across  -> rejected
  references + same date             7 of 15; wrong 0 inside, 2 across               -> rejected
  references + same date + amount    7 of 15; wrong 0 inside, 2 across               -> rejected
  same date + shared amount          10 of 15; wrong 53 inside                        -> rejected
  text >= 0.60 + same date           8 of 15; wrong 1 inside, 3 across                -> rejected
  text + moment                      9 of 15; wrong 0 inside (387 pairs), 0 across (1,678)  <- chosen
Not used by the application.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from checks import Checks  # noqa: E402

from app.config_files import read_json_config  # noqa: E402
from app.errors import StageError  # noqa: E402
from app.layout import group_rows, load_row_rules  # noqa: E402

READINGS = [ROOT / "outputs/ocr_resolution_trial/readings.json", ROOT / "outputs/search_criteria_trial/readings_claims.json"]
ANSWER_KEYS = [ROOT / "tools/ocr_resolution_trial/private/ground_truth.json",
               ROOT / "tools/search_criteria_trial/private/ground_truth_claims.json"]
CHECKS = ("text", "moment", "references", "invoice")
COMBINATIONS = (("text", "moment", "references"), ("invoice",), ("text", "moment", "invoice"),
                ("text", "moment", "references", "invoice"))


def load_pages() -> tuple[list[str], list[list[str]], list[list[list[str]]], dict[str, dict]]:
    """(page names, each page's segment texts, the same grouped into printed
    rows, answer key) — one reading per hand-checked page."""
    truth: dict[str, dict] = {}
    for path in ANSWER_KEYS:
        truth.update(json.loads(path.read_text(encoding="utf-8"))["pages"])
    pages: dict[str, list[dict]] = {}
    for path in READINGS:
        for variant in json.loads(path.read_text(encoding="utf-8")).values():
            for p in variant:
                if p["page"] in truth and "(2)" not in p["page"] and p["page"] not in pages:
                    pages[p["page"]] = p["words"]
    names = sorted(pages)
    row_rules = load_row_rules()
    rows = []
    for n in names:
        try:
            grouped = group_rows([SimpleNamespace(text=w["text"], box=w["box"]) for w in pages[n]], row_rules)
            rows.append([[seg.text for seg in row.segments] for row in grouped])
        except StageError:   # an unusable box: fall back to one segment per row
            rows.append([[w["text"]] for w in pages[n]])
    return names, [[w["text"] for w in pages[n]] for n in names], rows, truth


def identity(t: dict) -> tuple:
    return tuple(tuple(sorted(t.get(k, []))) for k in ("amounts", "dates", "ids"))


def main() -> None:
    cfg = read_json_config(HERE / "trial_config.json", {"invoice_labels": list, "text_similarity_min": float})
    checks = Checks(cfg)
    names, segments, rows, truth = load_pages()
    fps = [checks.fingerprint(s, r) for s, r in zip(segments, rows)]
    pairs = list(itertools.combinations(range(len(names)), 2))
    same = {p for p in pairs if identity(truth[names[p[0]]]) == identity(truth[names[p[1]]])}
    diff = set(pairs) - same
    print(f"{len(names)} pages; {len(same)} pairs showing the same receipt; {len(diff)} pairs of different receipts")
    with_invoice = sum(1 for f in fps if f.invoices)
    print(f"pages where an invoice-type label and its value were read: {with_invoice} of {len(names)}\n")

    flagged = {}
    for check in CHECKS:
        a, b = checks.pairwise(fps, check), checks.indexed(fps, check)
        assert a == b, f"{check}: pairwise and indexed forms disagree ({len(a ^ b)} pairs)"
        flagged[check] = a
    for th in cfg["text_thresholds_compared"]:
        assert checks.pairwise(fps, "text", th) == checks.indexed(fps, "text", th), f"text {th}: forms disagree"
    print("pairwise and indexed forms flag identical pairs for every check\n")

    def report(label: str, found: set) -> None:
        print(f"{label:44} caught {len(found & same):2}/{len(same)}; different receipts flagged {len(found & diff)}/{len(diff)}")

    for check in CHECKS:
        report(f"check: {check}", flagged[check])
    for th in cfg["text_thresholds_compared"]:
        report(f"   text at {th:.2f}", checks.pairwise(fps, "text", th))
    single = dict(cfg, shared_references_min=1)
    report("   references with ONE shared number", Checks(single).indexed(fps, "references"))
    for label, variant in (("   invoice, value on the label's printed row", {"invoice_value_from": "row"}),
                           ("   invoice, label's row or the next row", {"invoice_value_from": "row", "invoice_next_row": True})):
        other = Checks(dict(cfg, **variant))
        other_fps = [other.fingerprint(s, r) for s, r in zip(segments, rows)]
        print(f"{label}: value read on {sum(1 for f in other_fps if f.invoices)} pages")
        report(label, other.indexed(other_fps, "invoice"))
    print()
    for combo in COMBINATIONS:
        report(" + ".join(combo), set().union(*(flagged[c] for c in combo)))
    print("\nsame scan repeated inside one PDF: identical OCR text -> always caught by 'text'")
    by_document(checks, fps, names, same, diff, cfg)


def by_document(checks: Checks, fps: list, names: list[str], same: set, diff: set, cfg: dict) -> None:
    """As the application runs the check: within one receipts document at a time.
    "Rare" is counted inside that document; a same-receipt pair whose two
    captures sit in different files is judged as if both files were one PDF."""
    docs = [n.split("#")[0] for n in names]
    within = {p for p in diff if docs[p[0]] == docs[p[1]]}
    across = diff - within
    single = Checks(dict(cfg, shared_references_min=1))
    flagged = {c: _per_document(checks, fps, docs, c) for c in ("text", "moment", "references")}
    flagged["references (1 number)"] = _per_document(single, fps, docs, "references")
    shared_date = {p for p in same | diff if fps[p[0]].dates & fps[p[1]].dates}
    flagged["references + same date"] = flagged["references"] & shared_date
    print(f"\n--- one document at a time (as the app runs it): {len(within)} different-receipt pairs inside "
          f"a document, {len(across)} across documents (judged as one PDF)")

    def report(label: str, found: set) -> None:
        print(f"{label:44} caught {len(found & same):2}/{len(same)}; wrong inside a document "
              f"{len(found & within)}/{len(within)}; wrong across {len(found & across)}/{len(across)}")

    for label, found in flagged.items():
        report(f"check: {label}", found)
    for combo in (("text", "moment"), ("text", "moment", "references"), ("text", "moment", "references + same date")):
        report(" + ".join(combo), set().union(*(flagged[c] for c in combo)))


def _per_document(checks: Checks, fps: list, docs: list[str], check: str) -> set:
    members_of: dict[str, list[int]] = {}
    for i, d in enumerate(docs):
        members_of.setdefault(d, []).append(i)
    order = sorted(members_of)
    found = set()
    for k, da in enumerate(order):
        for db in order[k:]:
            members = members_of[da] + ([] if da == db else members_of[db])
            for x, y in checks.indexed([fps[i] for i in members], check):
                i, j = sorted((members[x], members[y]))
                if da == db or docs[i] != docs[j]:
                    found.add((i, j))
    return found


if __name__ == "__main__":
    main()
