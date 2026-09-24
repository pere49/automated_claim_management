"""PROTOTYPE RUNNER (tools/) — Stage C acceptance on the owner's real claims, through the application's code.

    .venv/Scripts/python.exe tools/stage_c_acceptance/run_acceptance.py

For each pair in private/pairs.json (git-ignored): the claim sheet read by
app/claims (Excel tab, text PDF, or a scanned sheet with its saved OCR), the
receipts from saved OCR readings prepared exactly as the window prepares
them, then app/checking. Prints each claimed amount's colour, page and
reason, the three statuses and both grand totals, and checks that no page is
paired twice. The Week2 pair also runs stress cases built from its own pages
(a page repeated; repeated and claimed twice; claimed twice with one
receipt; the PIN switch flipped). The company PIN comes from .env and is
never printed. Not used by the application.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from app.checking import GREEN, RED, analyse_receipts, decide, find_all, load_checking_rules  # noqa: E402
from app.claims import load_claim_rules, read_claim_file  # noqa: E402
from app.config_files import read_json_config  # noqa: E402
from app.layout import group_rows, load_row_rules  # noqa: E402
from app.matching import load_matching_rules, prepare_page  # noqa: E402


def main() -> None:
    cfg = read_json_config(HERE / "private/pairs.json", {"pairs": list, "today": str, "readings": list})
    today = date.fromisoformat(cfg["today"])
    ctx = SimpleNamespace(claim=load_claim_rules(), checking=load_checking_rules(), matching=load_matching_rules(),
                          rows=load_row_rules(), pin=_company_pin())
    readings = _readings(cfg["readings"])
    for pair in cfg["pairs"]:
        sheet = _sheet(pair, ctx, today)
        words = readings[pair["receipts"]]
        _run(pair["label"], sheet, words, ctx)
        if pair.get("stress"):
            third = sheet.items[2]
            twice = replace(sheet, rows=sheet.rows + [replace(sheet.rows[2], row=third.row * 100 + 1, items=[
                replace(third, index=len(sheet.items), row=third.row * 100 + 1)])],
                grand_total=(sheet.grand_total or 0) + third.amount)
            copy = {**words, max(words) + 1: words[3]}
            _run(f"STRESS {pair['label']}: page 3 repeated at the end", sheet, copy, ctx)
            _run(f"STRESS {pair['label']}: page 3 repeated AND row {third.row}'s amount claimed twice", twice, copy, ctx)
            _run(f"STRESS {pair['label']}: row {third.row}'s amount claimed twice, one receipt", twice, words, ctx)
            _run(f"STRESS {pair['label']}: PIN switch turned off by hand", sheet, words, ctx, pin_required=False)


def _run(label, sheet, words, ctx, pin_required=None) -> None:
    pages = {n: prepare_page(group_rows([SimpleNamespace(text=w["text"], box=w["box"]) for w in ws], ctx.rows),
                             ctx.matching) for n, ws in words.items()}
    facts = analyse_receipts(pages, max(words), [], ctx.pin, ctx.checking, ctx.matching)
    required = bool(facts.pin_pages) if pin_required is None else pin_required
    check = decide(sheet, find_all(sheet, facts, ctx.pin, ctx.matching), facts, required)
    used = Counter(r.page for r in check.items if r.colour == GREEN)
    assert all(v == 1 for v in used.values()), f"{label}: a page was paired twice"
    colours = Counter(r.colour for r in check.items)
    t = check.totals
    print(f"\n=== {label}")
    print(f"    {len(pages)} receipt pages; PIN on {len(facts.pin_pages)} -> required: {required}; "
          f"Verification: {check.verification.colour} ({check.verification.text}); PIN: {check.pin.colour} "
          f"({check.pin.text}); Repeated pages: {check.repeated_pages.colour} ({check.repeated_pages.text})")
    for r in check.items:
        it = r.item
        when = f"{r.date_used:%d %b %Y}" if r.date_used else "-"
        print(f"    row {it.row:>3} {it.column[:18]:<18} {str(it.amount):>9} {when:<12} {r.colour.upper():<6} "
              f"{r.status:<7} p.{r.page or '-':<3} {r.detail}")
    print(f"    green {colours[GREEN]}, yellow {colours['yellow']}, red {colours[RED]}; no page paired twice | "
          f"Grand total 1: {t.claimed} vs {t.grand_total} {'OK' if t.grand_total_1 else 'DIFFERS'}"
          f"{' rows ' + str(t.rows_disagreeing) if t.rows_disagreeing else ''} | Grand total 2: {t.approved} "
          f"{'OK' if t.grand_total_2 else 'short'}")


def _sheet(pair, ctx, today):
    scanned = None
    if "scanned_words" in pair:
        data = json.loads((ROOT / pair["scanned_words"]).read_text(encoding="utf-8"))
        scanned = {1: [(min(p[0] for p in w["page_box"]), min(p[1] for p in w["page_box"]),
                        max(p[0] for p in w["page_box"]), max(p[1] for p in w["page_box"]), w["text"]) for w in data]}
    claim = read_claim_file(ROOT / pair["sheet"], ctx.claim, today, scanned_words=scanned)
    return next(s for s in claim.sheets if s.name == pair["tab"])


def _readings(files):
    out = {}
    for f in files:
        for variant in json.loads((ROOT / f).read_text(encoding="utf-8")).values():
            for p in variant:
                doc, number = p["page"].rsplit("#", 1)
                out.setdefault(doc, {}).setdefault(int(number), p["words"])
    return out


def _company_pin() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("COMPANY_PINS="):
            return line.split("=", 1)[1].split(",")[0].strip()
    raise SystemExit("COMPANY_PINS missing from .env")


if __name__ == "__main__":
    main()
