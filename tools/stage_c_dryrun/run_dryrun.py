"""PROTOTYPE (tools/) — Stage C dry run on the owner's real claim pairs.

    .venv/Scripts/python.exe tools/stage_c_dryrun/run_dryrun.py

For each pair in private/pairs.json (git-ignored): claim items from the sheet,
dates by the date trial's recommended rule (R10u) with the configured "today",
receipts from saved OCR readings, then claim_check.py: PIN scan, repeated
pages, amount index, pairing (each page paired at most once, taken out of
every later search), double-claim rule, verdicts. Prints one line per claimed
amount, the status, both grand totals, and asserts that no page was paired
twice. The Week2 pair also runs stress cases built from its own pages:
a receipt page repeated; the same page repeated AND its amount claimed twice
on the same date; the amount claimed twice with only one receipt; the PIN
switch flipped. The company PIN is read from .env and never printed.
Not used by the application.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for folder in (ROOT, HERE, ROOT / "tools/duplicate_pages_trial", ROOT / "tools/date_parsing_trial"):
    sys.path.insert(0, str(folder))

from checks import Checks  # noqa: E402
from claim_check import GREEN, RED, YELLOW, check, pin_pages, prepare, repeated_pages  # noqa: E402
from combo_rules import COMBOS, run_combo  # noqa: E402
from sheets import claim_items, excel_sheet, items_file  # noqa: E402
from strategies import Parser  # noqa: E402

from app.config_files import read_json_config  # noqa: E402
from app.layout import load_row_rules  # noqa: E402
from app.matching import load_matching_rules  # noqa: E402

DATE_RULE = "R10u"


def company_pin() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("COMPANY_PINS="):
            return line.split("=", 1)[1].split(",")[0].strip()
    raise SystemExit("COMPANY_PINS missing from .env")


def receipts(spec: dict) -> dict[int, list[dict]]:
    data = json.loads((ROOT / spec["readings"]).read_text(encoding="utf-8"))["current"]
    prefix = spec["document"] + "#"
    return {int(p["page"].split("#")[1]): p["words"] for p in data if p["page"].startswith(prefix)}


def run(label, items, words, grand, ctx, pin_required=None) -> None:
    doc = prepare(words, ctx["rules"], ctx["row_rules"])
    with_pin = pin_pages(doc, ctx["pin"], ctx["rules"])
    required = bool(with_pin) if pin_required is None else pin_required
    repeats = repeated_pages(doc, ctx["checks"])
    outcomes = check(items, doc, ctx["rules"], ctx["pin"], required, repeats)
    used = Counter(o.page for o in outcomes if o.colour == GREEN)
    assert all(v == 1 for v in used.values()), f"{label}: a page was paired twice"

    colours = Counter(o.colour for o in outcomes)
    repeat_state = "none (green)" if not repeats else (
        "RED - one receipt, two claims" if colours[RED] else "yellow - repeated, claimed once")
    print(f"\n=== {label}")
    print(f"    {len(doc.pages)} receipt pages; PIN on {len(with_pin)} of them -> PIN required: "
          f"{'yes' if required else 'no'}{' (switch flipped by hand)' if pin_required is not None else ''}; "
          f"repeated pages: {repeats or 'none'} -> {repeat_state}")
    for o in outcomes:
        it = o.item
        when = f"{it.date:%d %b %Y}" if it.date else "no date"
        print(f"    row {it.row:>3} {it.column[:22]:<22} {it.amount:>10} {when:<12} {o.colour.upper():<7}"
              f" p.{o.page if o.page else '-':<3} {o.reason}")
    total1 = sum(o.item.amount for o in outcomes)
    total2 = sum(o.item.amount for o in outcomes if o.colour == GREEN)
    print(f"    green {colours[GREEN]}, yellow {colours[YELLOW]}, red {colours[RED]}; pages paired: {len(used)}, "
          f"none twice | Grand total 1: {total1} vs {grand} {'OK' if total1 == grand else 'DIFFERS'} | "
          f"Grand total 2: {total2} of {grand}")


def main() -> None:
    cfg = read_json_config(HERE / "private/pairs.json", {"pairs": list, "today": str})
    today = date.fromisoformat(cfg["today"])
    parser = Parser(read_json_config(ROOT / "tools/date_parsing_trial/trial_config.json", {"month_names": dict}))
    ctx = {"rules": load_matching_rules(), "row_rules": load_row_rules(), "pin": company_pin(),
           "checks": Checks(read_json_config(ROOT / "tools/duplicate_pages_trial/trial_config.json", {}))}

    def read_dates(cells):
        return run_combo(COMBOS[DATE_RULE], parser, cells, [set()] * len(cells), today)

    for pair in cfg["pairs"]:
        sheet = pair["sheet"]
        rows, grand = (excel_sheet(ROOT / sheet["xlsx"], sheet["tab"], cfg["excel_layout"]) if "xlsx" in sheet
                       else items_file(ROOT / sheet["items"]))
        items = claim_items(rows, read_dates)
        words = receipts(pair["receipts"])
        run(pair["label"], items, words, grand, ctx)
        if not pair.get("stress"):
            continue
        target = next(it for it in items if it.date and it.row == items[2].row)   # the third claimed amount
        page = 3
        twice = items + [replace(target, row=target.row * 100 + 1, column=target.column + " (again)")]
        copy = {**words, max(words) + 1: words[page]}
        run(f"STRESS {pair['label']}: receipt p.{page} repeated at the end", items, copy, grand, ctx)
        run(f"STRESS {pair['label']}: p.{page} repeated AND row {target.row}'s amount claimed twice that day",
            twice, copy, grand + target.amount, ctx)
        run(f"STRESS {pair['label']}: row {target.row}'s amount claimed twice, one receipt only",
            twice, words, grand + target.amount, ctx)
        run(f"STRESS {pair['label']}: PIN switch flipped", items, words, grand, ctx,
            pin_required=not bool(pin_pages(prepare(words, ctx["rules"], ctx["row_rules"]), ctx["pin"], ctx["rules"])))


if __name__ == "__main__":
    main()
