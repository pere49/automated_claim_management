"""PROTOTYPE (tools/) — date trial: score every rule on thousands of fabricated sheets.

    .venv/Scripts/python.exe tools/date_parsing_trial/run_trial.py

Per rule, over every dated row: read correctly, read WRONG, or left for the
officer. "Wrong and confirmed by a receipt" counts the wrong readings that a
receipt carrying the row's amount happens to show — the ones that could turn
into a wrong PASS; every other wrong reading only fails to find its receipt.
Ranked by wrong-and-confirmed, then wrong, then left for the officer.

Measured 2026-09-24, second round (4,000 sheets, 50,282 dated rows, each
sheet checked 0-365 days after its last receipt; step rules in combo_rules.py,
including the owner's two methods):
  R10u  99.67% correct, 2 wrong, 1 wrong-and-confirmed, 0.33% officer  <- recommended
        (the owner's method 1 + no reading after the day of checking + one
        claim period + the receipt + the guard; every file type handled alike)
  R10s  99.63% correct, 2 wrong, 1 confirmed, 0.37% officer
  R11   R10u + the owner's method 2 over all dates: 6 wrong
  U2    method 1 + method 2 over all dates, no future dates: 248 wrong
  U1    the owner's methods as described (the last listed date's closeness
        to today): 742 wrong, 10 confirmed — wrong even when the claim is
        checked within 30 days (201): for past dates "closer to today" means
        "the later reading", which fails when the flipped reading is later
        but not yet in the future, and the last listed date is not always
        the latest; it also reads the real Week1 sheet as 8 Mar-8 Sep
  R9    1,581 wrong (the swapped Excel sheets)
On the six real sheets (Excel Week1 and Week2, the Week2 PDF export, the July
sheet as text and as a picture through OCR, the new July-EA sheet; 65 dates),
checked on 2026-09-24: R10u reads every date right, none left for the officer.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from combo_rules import COMBOS, run_combo  # noqa: E402
from generate import generate  # noqa: E402
from strategies import Parser, run_rule  # noqa: E402

from app.config_files import read_json_config  # noqa: E402

RULES = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R10s"] + list(COMBOS)
BY_DELAY = ["R10s", "U1", "U0", "U2", "R10u", "R11"]


def main() -> None:
    cfg = read_json_config(HERE / "trial_config.json", {"sheets": int, "month_names": dict})
    sheets = generate(cfg)
    parser = Parser(cfg)
    rows = sum(1 for s in sheets for r in s.rows if r.true)
    print(f"{len(sheets)} fabricated sheets, {rows} dated rows; styles: "
          + ", ".join(f"{k} {v}" for k, v in Counter(s.style for s in sheets).most_common()))
    print(f"sheets from a PDF picture (OCR noise possible): {sum(s.from_pdf for s in sheets)}; "
          f"writers who swap day and month on some rows: {sum(s.swapper for s in sheets)}\n")
    table = []
    by_style = defaultdict(dict)
    delay_t = defaultdict(lambda: defaultdict(Counter))
    for rule in RULES:
        t = Counter()
        style_t = defaultdict(Counter)
        for s in sheets:
            cells, receipts = [r.cell for r in s.rows], [r.receipt_dates for r in s.rows]
            if rule in COMBOS:
                got = run_combo(COMBOS[rule], parser, cells, receipts, s.processed)
            else:
                got = run_rule(rule, parser, cells, receipts)
            delay = (s.processed - max(r.true for r in s.rows if r.true)).days if any(r.true for r in s.rows) else 0
            bucket = next(f"{lo}-{hi} days" for lo, hi, _ in cfg["processing_delay_days"] if lo <= delay <= hi)
            for r, g in zip(s.rows, got):
                if r.true is None:
                    continue
                outcome = "correct" if g == r.true else ("officer" if g is None else "wrong")
                t[outcome] += 1
                style_t["swapper" if s.swapper else s.style][outcome] += 1
                delay_t[rule][bucket][outcome] += 1
                if outcome == "wrong" and g in r.receipt_dates:
                    t["wrong_confirmed"] += 1
        table.append((t["wrong_confirmed"], t["wrong"], t["officer"], rule, t))
        by_style[rule] = style_t
    table.sort()
    print(f"{'rule':6} {'correct':>16} {'WRONG':>14} {'wrong + a receipt agrees':>26} {'left for officer':>18}")
    for wc, w, o, rule, t in table:
        print(f"{rule:6} {t['correct']:7} ({100 * t['correct'] / rows:5.2f}%) {w:6} ({100 * w / rows:5.2f}%) "
              f"{wc:12} {'':12} {o:6} ({100 * o / rows:5.2f}%)")
    print("\nwrong readings by how long after the last receipt the claim is checked (wrong / officer):")
    buckets = [f"{lo}-{hi} days" for lo, hi, _ in cfg["processing_delay_days"]]
    print(f"  {'rule':6}" + "".join(f"{b:>20}" for b in buckets))
    for rule in BY_DELAY:
        print(f"  {rule:6}" + "".join(f"{delay_t[rule][b]['wrong']:>11} / {delay_t[rule][b]['officer']:<6}" for b in buckets))
    for rule in ("R10s", "U1", "R11"):
        print(f"\n{rule} — per writing style (correct / wrong / officer):")
        for style, c in sorted(by_style[rule].items()):
            n = sum(c.values())
            print(f"  {style:26} {c['correct']:6} / {c['wrong']:4} / {c['officer']:4}   of {n}")


if __name__ == "__main__":
    main()
