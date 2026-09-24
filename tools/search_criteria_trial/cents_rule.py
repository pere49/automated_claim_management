"""PROTOTYPE (tools/) — the "cents dropped" rule for amounts, measured.

Rule (user, 2026-09-24): a claimed amount matches a receipt when it equals the
receipt's amount exactly, or equals it with the cents dropped (claim 500 for a
receipt of 500.34 — the claimant rounded DOWN to the whole number). Never the
other way: a claim of 500.34 does not match a receipt of 500, and 500 does not
match 499.99 or 501.00.

    .venv/Scripts/python.exe tools/search_criteria_trial/cents_rule.py

Compares the approved amount rule (A9, EXACT) with A9 + cents-dropped on:
  real positives   every real answer-key amount with cents, claimed with its
                   cents dropped (these must now be found, on their own page)
  real decoys      the trial's real amount traps that are whole numbers
  fabricated       positives and traps written for this rule
and lists every false match so its kind can be judged. Not used by the app.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cases_real import real_cases  # noqa: E402
from cases_synthetic import Case, row  # noqa: E402
from text_model import ROOT, TextSettings, page_rows  # noqa: E402

sys.path.insert(0, str(ROOT))
from app.config_files import read_json_config  # noqa: E402
from app.matching import load_matching_rules  # noqa: E402
from app.matching.amount_search import trim  # noqa: E402
from app.matching.money import amount_forms  # noqa: E402

CENTS = re.compile(r"(.+)[.,](\d{2})")
TS = TextSettings("tail", 0.6)


def floor_found(claim: Decimal, rows: list[list[str]], rules) -> list[str]:
    """Tokens that match the whole-number claim only by dropping their cents."""
    if claim != claim.to_integral_value():
        return []
    forms = amount_forms(claim, rules)
    hits = []
    for tokens in rows:
        for tok in tokens:
            core, _ = trim(tok, rules)
            m = CENTS.fullmatch(core)
            if m and m.group(2) != "00" and m.group(1) in forms.without_cents and core not in forms.with_cents:
                hits.append(core)
    return hits


def synthetic() -> list[Case]:
    cases = []
    def add(v, segs, expected, cat):
        cases.append(Case("amount", Decimal(v), segs, expected, cat, label=" | ".join(s.text for s in segs)))
    for v, printed in (("500", "500.34"), ("500", "500.99"), ("500", "500.01"), ("1200", "1,200.50"), ("2406", "2,406.94"),
                       ("2406", "2.406.94"), ("45", "45.50"), ("13000", "13,000.25")):
        add(v, row(("TOTAL", 0), (printed, 300)), True, "cents dropped: must be found")
        add(v, row((f"Ksh{printed}", 0)), True, "cents dropped: must be found")
        add(v, row(("CASH", 0), (f"{printed} KES", 300)), True, "cents dropped: must be found")
    for v, printed, why in (("500", "501.00", "one more"), ("500", "499.99", "rounded up, not down"), ("500", "1,500.34", "longer number"),
                            ("500", "5000.34", "ten times"), ("500", "50.34", "shorter"), ("500.34", "500", "claim has cents, receipt none"),
                            ("500.34", "500.00", "claim above the receipt"), ("500", "500.34.12", "not an amount"),
                            ("12", "12.08/2026", "part of a date"), ("19", "19.06", "a time"), ("16", "16.00%", "a tax rate"),
                            ("1100", "Qty 1 100.34", "quantity then price")):
        add(v, row(("LINE", 0), (printed, 300)), False, f"trap: {why}")
    return cases


def main() -> None:
    cfg = read_json_config(HERE / "trial_config.json", {"currency_words": list})
    rules = load_matching_rules()
    real = real_cases(ROOT, cfg)
    cache = {}
    def rows_of(c):
        if id(c.segments) not in cache:
            cache[id(c.segments)] = page_rows(c.segments, TS)
        return cache[id(c.segments)]
    tally, false_kinds = Counter(), Counter()
    # real positives: every real amount with cents, claimed as its whole number, on its own page
    seen = set()
    for c in real:
        if c.kind == "amount" and c.expected and c.claim != c.claim.to_integral_value() and (id(c.segments), c.claim) not in seen:
            seen.add((id(c.segments), c.claim))
            floor = c.claim.to_integral_value(rounding="ROUND_FLOOR")
            tally[("real positive (receipt amount, cents dropped)", "found" if floor_found(floor, rows_of(c), rules) else "missed")] += 1
    for c in real:
        if c.kind == "amount" and not c.expected and c.claim == c.claim.to_integral_value():
            hits = floor_found(c.claim, rows_of(c), rules)
            tally[("real decoy, whole number", "FALSE MATCH" if hits else "rejected")] += 1
            if hits:
                false_kinds[(c.category, f"claim {c.claim} vs printed {hits[0]}")] += 1
    for c in synthetic():
        hits = floor_found(c.claim, [[t for s in c.segments for t in s.text.split()]], rules)
        outcome = ("found" if hits else "missed") if c.expected else ("FALSE MATCH" if hits else "rejected")
        tally[(c.category if c.expected else "fabricated traps", outcome)] += 1
        if not c.expected and hits:
            false_kinds[(c.category, c.label)] += 1
    for k, v in sorted(tally.items()):
        print(f"{k[0]:48} {k[1]:12} {v}")
    print("\nfalse matches, by kind:")
    for (cat, what), n in false_kinds.most_common():
        print(f"  {n:3}  {cat:40} {what}")


if __name__ == "__main__":
    main()
