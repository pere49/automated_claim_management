"""PROTOTYPE TRIAL (tools/) — how many receipt pages and claim rows turn red under two colour rules.

    .venv/Scripts/python.exe tools/badge_colour_trial/run_trial.py

Runs the owner's real claims through the application's own code (app/claims
+ app/checking; the pairs in tools/stage_c_acceptance/private/pairs.json,
receipts from saved OCR readings) and colours every receipt page and every
claim row from the problems the application finds (D35) — two ways:

  A (the owner's first rule): PIN required -> PIN missing red; PIN present but
    date or amount wrong yellow. PIN not required -> date or amount wrong red.
    Repeated, unreadable, no receipt found, another buyer's PIN: red.
  B (the alternative, chosen by the owner 2026-09-24 and built, D34): red =
    no valid receipt (the problems in checking_rules.json's red_problems);
    yellow = a receipt is there but its date or amount does not match,
    whatever the PIN switch says. Rule B is the application's own colouring.

History: the first version (2026-09-24, before the rework) derived the links
itself from the application's findings; once the application linked pages
itself (links.py), re-running that version miscounted pages linked by date
as green. This version reads the problems straight from the application.

Prints counts only (never names, amounts or PINs). Not used by the application.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "stage_c_acceptance"))

import run_acceptance as acc  # noqa: E402  (its readers of the private pairs, saved readings and sheets)
from app.checking import (GREEN, P_AMOUNT, P_DATE, RED, YELLOW, analyse_receipts, decide, find_all,  # noqa: E402
                          load_checking_rules)
from app.claims import load_claim_rules  # noqa: E402
from app.config_files import read_json_config  # noqa: E402
from app.layout import group_rows, load_row_rules  # noqa: E402
from app.matching import load_matching_rules, prepare_page  # noqa: E402

ORDER = {GREEN: 0, YELLOW: 1, RED: 2}
MISMATCH = {P_AMOUNT, P_DATE}


def main() -> None:
    cfg = read_json_config(ROOT / "tools/stage_c_acceptance/private/pairs.json",
                           {"pairs": list, "today": str, "readings": list})
    today = date.fromisoformat(cfg["today"])
    ctx = SimpleNamespace(claim=load_claim_rules(), checking=load_checking_rules(), matching=load_matching_rules(),
                          rows=load_row_rules(), pin=acc._company_pin())
    readings = acc._readings(cfg["readings"])
    totals = {"A": Counter(), "B": Counter()}
    for pair in cfg["pairs"]:
        pair = {**pair, "sheet": acc.find(pair["sheet"])}
        run(pair["label"], acc._sheet(pair, ctx, today), readings[pair["receipts"]], ctx, totals)
    print("\n=== ALL CLAIMS")
    for rule in "AB":
        print(f"    rule {rule}: " + ", ".join(f"{k} {v}" for k, v in sorted(totals[rule].items())))


def run(label, sheet, words, ctx, totals) -> None:
    pages = {n: prepare_page(group_rows([SimpleNamespace(text=w["text"], box=w["box"]) for w in ws], ctx.rows),
                             ctx.matching) for n, ws in words.items()}
    facts = analyse_receipts(pages, max(words), [], ctx.pin, ctx.checking, ctx.matching)
    required = bool(facts.pin_pages)
    check = decide(sheet, find_all(sheet, facts, ctx.pin, ctx.matching), facts, required)

    def colour(rule: str, problems: tuple[str, ...], app_colour: str) -> str:
        if rule == "B" or not problems or not set(problems) <= MISMATCH:
            return app_colour                   # rule B is the application's; A differs only on date / amount
        return YELLOW if required else RED       # A: PIN present (else PIN would be a problem) -> yellow

    print(f"\n=== {label}  ({len(check.pages)} receipt pages, {len(sheet.rows)} rows, PIN required: {required})")
    for rule in "AB":
        page_colours = Counter(colour(rule, p.problems, p.colour) for p in check.pages.values())
        rows: dict[int, str] = {}
        for r in check.items:
            c = colour(rule, r.problems, r.colour)
            rows[r.item.row] = max(rows.get(r.item.row, GREEN), c, key=ORDER.get)
        row_colours = Counter(rows.values())
        totals[rule].update({f"pages {k}": v for k, v in page_colours.items()})
        totals[rule].update({f"rows {k}": v for k, v in row_colours.items()})
        print(f"    rule {rule}: pages  green {page_colours[GREEN]:>2}  yellow {page_colours[YELLOW]:>2}  red "
              f"{page_colours[RED]:>2}   |   row buttons  green {row_colours[GREEN]:>2}  yellow {row_colours[YELLOW]:>2}"
              f"  red {row_colours[RED]:>2}")


if __name__ == "__main__":
    main()
