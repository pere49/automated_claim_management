"""PROTOTYPE RUNNER (tools/) — Stage C acceptance on the owner's real claims, through the application's code.

    .venv/Scripts/python.exe tools/stage_c_acceptance/run_acceptance.py

For each pair in private/pairs.json (git-ignored): the claim sheet read by
app/claims (a text PDF, or a scanned sheet with its saved OCR), the receipts
from saved OCR readings prepared exactly as the window prepares them, then
app/checking. Prints each claimed amount's colour, linked page and badge,
every page's badge, the four statuses, and checks that no page is linked to
two amounts. The application no longer reads Excel (D39); an Excel tab in
the pairs (the owner's Week1, the only real claim with receipts missing the
PIN) is read here with openpyxl — this runner only — and built into a sheet
by the application's own sheet builder. Files moved into sub-folders of
images/ are found by name. The Week2 pair also runs stress cases built from
its own pages (a page repeated; repeated and claimed twice; claimed twice
with one receipt; the PIN switch flipped). The company PIN comes from .env and is
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
from app.claims.sheet_builder import build_sheet  # noqa: E402
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
        pair = {**pair, "sheet": find(pair["sheet"])}
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
    used = Counter(r.page for r in check.items if r.page is not None)
    assert all(v == 1 for v in used.values()), f"{label}: a page was linked to two amounts"
    assert all(check.pages[r.page].item == i for i, r in enumerate(check.items) if r.page is not None), label
    colours = Counter(r.colour for r in check.items)
    rows = {}
    for r in check.items:
        rows[r.item.row] = max(rows.get(r.item.row, GREEN), r.colour, key=["green", "yellow", "red"].index)
    t = check.totals
    print(f"\n=== {label}")
    print(f"    {len(pages)} receipt pages; PIN on {len(facts.pin_pages)} -> required: {required}")
    print(f"    Verification: {check.verification.colour} ({check.verification.text}) | Total: {check.total.colour} "
          f"({check.total.text}) | PIN: {check.pin.colour} ({check.pin.text}) | Repeated: "
          f"{check.repeated_pages.colour} ({check.repeated_pages.text})")
    for r in check.items:
        it = r.item
        when = f"{r.date_used:%d %b %Y}" if r.date_used else "-"
        badge = " / ".join(r.lines) or "ok"
        print(f"    row {it.row:>3} {it.column[:18]:<18} {str(it.amount):>9} {when:<12} {r.colour.upper():<6} "
              f"{r.status:<7} p.{r.page or '-':<3} {badge:<30} {r.detail}")
    print("    pages: " + "  ".join(f"{n}:{p.colour[0].upper()}[{' / '.join(p.lines)}]"
                                  for n, p in check.pages.items()))
    rc = Counter(rows.values())
    print(f"    amounts green {colours[GREEN]}, yellow {colours['yellow']}, red {colours[RED]} | row buttons green "
          f"{rc['green']}, yellow {rc['yellow']}, red {rc['red']} | no page linked twice | amounts {t.claimed}, "
          f"verified {t.approved}, sheet Total {t.grand_total}"
          f"{' rows ' + str(t.rows_disagreeing) if t.rows_disagreeing else ''}")


def _sheet(pair, ctx, today):
    if pair["sheet"].lower().endswith((".xlsx", ".xlsm")):
        grid = _excel_grid(ROOT / pair["sheet"], pair["tab"])
        return build_sheet(pair["tab"], grid, list(range(1, len(grid) + 1)), ctx.claim, today)
    scanned = None
    if "scanned_words" in pair:
        data = json.loads((ROOT / pair["scanned_words"]).read_text(encoding="utf-8"))
        scanned = {1: [(min(p[0] for p in w["page_box"]), min(p[1] for p in w["page_box"]),
                        max(p[0] for p in w["page_box"]), max(p[1] for p in w["page_box"]), w["text"]) for w in data]}
    claim = read_claim_file(ROOT / pair["sheet"], ctx.claim, today, scanned_words=scanned)
    return next(s for s in claim.sheets if s.name == pair["tab"])


def _excel_grid(path: Path, tab: str) -> list[list[object]]:
    """This runner only (the application does not read Excel, D39): one tab's saved values."""
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [list(row) for row in book[tab].iter_rows(min_row=1, values_only=True)]
    finally:
        book.close()


def find(relative: str) -> str:
    """Files moved into sub-folders of images/ after the pairs were written: found by name."""
    path = ROOT / relative
    if path.exists():
        return relative
    found = next((p for p in (ROOT / "images").rglob(path.name)), None)
    if found is None:
        raise SystemExit(f"not found under images/: {path.name}")
    return str(found.relative_to(ROOT))


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
