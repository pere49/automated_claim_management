"""PROTOTYPE (tools/) — what makes a matched amount the receipt's total (O1), and a different buyer's PIN.

    .venv/Scripts/python.exe tools/total_anchor_trial/run_trial.py

Part 1, the total anchor. On the owner's real claims (private/pairs.json:
the claim sheets read by app/claims, receipts from saved OCR readings):
  positives   every claimed amount found with its date on a receipt page
              (the claimant claimed it; it must stay acceptable)
  decoys      every OTHER amount printed on those same pages — cash
              tendered, change, line items, VAT, subtotals — as if claimed
              with that page's date (accepting one is a wrong green)
Rules compared (labels in trial_config.json, whole words on the amount's
printed row):
  A0  no anchor (today)
  A1  not only on cash / change / card rows
  A2  on a total-labelled row that is not a cash row, or the largest amount
      on the page outside cash rows
  A3  the largest amount on the page outside cash rows
  A4  on a total-labelled row that is not a cash row
  A4f A4, label words allowed one OCR letter slip ("TOTEL") — labels only
      help find where to look; values are still matched exactly
  A4m A4f, plus mobile-money wording ("Ksh200.00 sent to ...")
Ranked by wrong greens, then positives lost.

Part 2, a different buyer's PIN (D13's CAUTION). On every saved page: a
PIN-shaped value after a buyer / customer label on the same printed row;
compared with the company PIN from .env (never printed) with the matcher's
own tolerance. Pages naming another buyer are listed (digits masked) to be
judged by eye; pages carrying the company PIN must never be flagged.

CORRECTED, same day — Part 1 now runs through the application's own finder
(app/checking find_item and its label test), so the trial and the
application cannot differ. The first version (kept below for the record)
located only amounts printed with cents and ACCEPTED any amount it could not
locate — so telebirr's amounts ("460 Birr", no cents) were never tested;
through the app, the same-row rule turned 11 real telebirr claims yellow.
Telebirr prints "Settled Amount" as a column header with the value under it
(its "Total Paid Amount" adds the fee), hence A4m+:
  A0    no anchor                          keeps 31/31; accepts 22/22 larger amounts, 85/85 smaller
  A4m   same row                           keeps 20/31; accepts 10/22 larger
  A4m+  same row, or the column header     keeps 30/31; accepts 10/22 larger, 21/85 smaller
        right above
  A4m+ and rows with a "%" (tax lines)     keeps 30/31; accepts 9/22 larger
        not totals
  ... and a header segment refused only    keeps 31/31; accepts 9/22 larger, 21/85 smaller  <- chosen
      when one of its words is a number
      (OCR turns an Amharic letter in "Settled Amount" into a "9")
  The 9 larger amounts still accepted are all telebirr's "Total Paid Amount"
  (the transfer plus its fee — money the claimant did pay); cash tendered,
  change, tax lines and "total before discount" are all refused. Through the
  application (tools/stage_c_acceptance) the real claims then give exactly
  the dry run's greens: Week1 6, Week2 5, July 18, the wrong pair 0.

First version, measured 2026-09-24 (Week1, Week2, July; 33 claimed amounts found with their
dates, 95 other amounts on those pages: 11 larger than the claim, 84 smaller):
  A0   keeps 33/33; accepts 11/11 larger (over-claims), 84/84 smaller
  A1   keeps 32/33; accepts 8/11 larger
  A2   keeps 30/33; accepts 5/11 larger
  A4   keeps 29/33; accepts 0/11 larger, 17/84 smaller
  A4m  keeps 32/33; accepts 0/11 larger, 17/84 smaller   <- chosen (the one lost
       real claim shows its total only on a cash line: yellow, checked by hand)
  First run: "total before discount" was accepted as a total (an over-claim) ->
  discount wording added to the rows that are not the paid total.
  Smaller amounts (a line item, VAT) are under-claims; one receipt still pays
  at most one claim (page pairing), so they cannot add up to more.
Part 2: 71 pages; buyer label with the company PIN on 22, with no PIN after
it on 4, naming another buyer on 0 -> 0 wrong flags (no page in the samples
names another buyer, so the check's benefit is not measurable here).
Not used by the application.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from app.claims import load_claim_rules, read_claim_file  # noqa: E402
from app.config_files import read_json_config  # noqa: E402
from app.layout import group_rows, load_row_rules  # noqa: E402
from app.matching import load_matching_rules, prepare_page  # noqa: E402
from app.checking import analyse_receipts, load_checking_rules  # noqa: E402
from app.checking.findings import CENTS_DROPPED, EXACT_AMOUNT, find_item  # noqa: E402
from app.matching.pin_search import _compare, _format_of, normalise_pin  # noqa: E402  (prototype)

MONEY = re.compile(r"^\d{1,3}(?:[,.' ]\d{3})*[.,]\d{2}$|^\d+[.,]\d{2}$")


def main() -> None:
    cfg = read_json_config(HERE / "trial_config.json", {"pairs": str, "buyer_pin_labels": list})
    pairs = read_json_config(ROOT / cfg["pairs"], {"pairs": list, "today": str, "readings": list})
    rules, row_rules, claim_rules, checking = (load_matching_rules(), load_row_rules(), load_claim_rules(),
                                               load_checking_rules())
    today = date.fromisoformat(pairs["today"])
    readings = _readings(pairs["readings"])
    variants = {"A0 no anchor": None, "A4m same row": False, "A4m+ same row or column header above": True}
    tally = {v: Counter() for v in variants}
    shown = {v: [] for v in variants}
    for pair in pairs["pairs"]:
        claim = read_claim_file(ROOT / pair["sheet"], claim_rules, today)
        sheet = next(s for s in claim.sheets if s.name == pair["tab"])
        pages = {n: prepare_page(group_rows([SimpleNamespace(text=w["text"], box=w["box"]) for w in words], row_rules),
                                 rules) for n, words in readings[pair["receipts"]].items()}
        facts = analyse_receipts(pages, max(pages), [], None, checking, rules)
        for item in sheet.items:
            if item.amount is None or item.date.value is None:
                continue
            when = item.date.value
            for variant, above in variants.items():
                found = find_item(item, facts, None, rules, look_above=bool(above))
                for p in found.pages:
                    if p.amount not in (EXACT_AMOUNT, CENTS_DROPPED) or when not in p.dates:
                        continue
                    tally[variant][("positive", above is None or p.anchored)] += 1
                    for value in _page_values(pages[p.page]) - {item.amount}:
                        decoy = replace(item, amount=value)
                        hit = next((d for d in find_item(decoy, facts, None, rules, look_above=bool(above)).pages
                                    if d.page == p.page and d.amount in (EXACT_AMOUNT, CENTS_DROPPED)
                                    and when in d.dates), None)
                        if hit is None:
                            continue          # the matcher would not find this amount at all
                        kind = "larger" if value > item.amount else "smaller"
                        ok = above is None or hit.anchored
                        tally[variant][(kind, ok)] += 1
                        if ok and kind == "larger" and above is not None:
                            rows = {h.row for h in hit.amount_hits}
                            shown[variant].append(" / ".join(re.sub(r"[0-9]", "9", pages[p.page].rows[r].text)
                                                             for r in sorted(rows)))
    print("Part 1 — the total anchor, through the application's own finder (positives: claimed amounts found with")
    print("their date; decoys: every other amount the finder can find on those pages, claimed with that date):")
    for variant in variants:
        t = tally[variant]
        n = {k: t[(k, True)] + t[(k, False)] for k in ("positive", "larger", "smaller")}
        print(f"  {variant:40} positives kept {t[('positive', True)]}/{n['positive']}; larger decoys accepted "
              f"{t[('larger', True)]}/{n['larger']}; smaller accepted {t[('smaller', True)]}/{n['smaller']}")
        for row in shown[variant]:
            print(f"      accepted larger amount on the row: {ascii(row)[:120]}")

    print("\nPart 2 — a different buyer's PIN:")
    _buyer_pins(readings, cfg, rules, row_rules)


def _readings(files: list[str]) -> dict[str, dict[int, list[dict]]]:
    out: dict[str, dict[int, list[dict]]] = {}
    for f in files:
        for variant in json.loads((ROOT / f).read_text(encoding="utf-8")).values():
            for p in variant:
                doc, number = p["page"].rsplit("#", 1)
                out.setdefault(doc, {}).setdefault(int(number), p["words"])
    return out


def _labels(labels: list[str]) -> re.Pattern:
    return re.compile("|".join(r"\b" + r"\s+".join(map(re.escape, label.split())) + r"\b" for label in labels))


def _page_values(page) -> set[Decimal]:
    """Every amount-like text on the page, as a value (with cents, or a whole number)."""
    out = set()
    for row in page.amount_cores:
        for core, _ in row:
            if MONEY.fullmatch(core):
                digits = re.sub(r"[,.' ]", "", core[:-3]) + "." + core[-2:]
            elif re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+", core):
                digits = core.replace(",", "")
            else:
                continue
            try:
                value = Decimal(digits)
            except InvalidOperation:
                continue
            if value >= 1:
                out.add(value.quantize(Decimal("0.01")))
    return out


def _buyer_pins(readings: dict, cfg: dict, rules, row_rules) -> None:
    pin = normalise_pin(next(line.split("=", 1)[1].split(",")[0] for line in (ROOT / ".env").read_text().splitlines()
                             if line.startswith("COMPANY_PINS=")))
    fmt = _format_of(pin, rules)
    labels = _labels(cfg["buyer_pin_labels"])
    stats = Counter()
    for doc, pages in readings.items():
        for n, words in pages.items():
            rows = group_rows([SimpleNamespace(text=w["text"], box=w["box"]) for w in words], row_rules)
            ours_anywhere = any(_compare(tok.strip(".,:;").upper(), pin, fmt, rules)
                                for w in words for tok in w["text"].split())
            stats["pages"] += 1
            for row in rows:
                text = row.text
                m = labels.search(text.lower())
                if not m:
                    continue
                after = text[m.end():].split()
                shaped = [t.strip(".,:;|") for t in after if _format_of(t.strip(".,:;|").upper(), rules)]
                if not shaped:
                    stats["buyer label, no PIN after it"] += 1
                    continue
                value = shaped[0].upper()
                if _compare(value, pin, fmt, rules):
                    stats["buyer PIN = company PIN"] += 1
                else:
                    stats["buyer PIN = ANOTHER"] += 1
                    if ours_anywhere:
                        stats["  ...on a page that also carries the company PIN (would be a wrong flag)"] += 1
                    print(f"   another buyer named: page {doc[:12]}..#{n}: {ascii(re.sub(r'[0-9]', '9', text))[:90]}")
    for k, v in stats.items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
