"""PROTOTYPE (tools/) — prove the application's matcher equals the trial winners.

    .venv/Scripts/python.exe tools/search_criteria_trial/verify_app_matcher.py

Runs app.matching (the code the window uses) over every trial case, real and
fabricated, and compares with the approved winners measured by run_trial.py:
amounts A9 (decimal-tail joining), dates D4, PINs P6. Only EXACT and
CORRECTED finds count as found (POSSIBLE is a CAUTION, never a find). Exits
with status 1 if any count differs, so it can be re-run after any change to
app/matching or its rules. Holds no values in its output beyond case labels.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cases_real import real_cases  # noqa: E402
from cases_synthetic import all_cases  # noqa: E402
from criteria import amount_found, date_found, pin_found  # noqa: E402
from text_model import ROOT, TextSettings, page_rows  # noqa: E402

sys.path.insert(0, str(ROOT))
from app.config_files import read_json_config  # noqa: E402
from app.layout import group_rows, load_row_rules  # noqa: E402
from app.matching import (CORRECTED, EXACT, Query, load_matching_rules, prepare_page,  # noqa: E402
                          search_page)

WINNERS = {"amount": ("A9", TextSettings("tail", 0.6)), "date": ("D4", TextSettings("none")),
           "pin": ("P6", TextSettings("none"))}
TRIAL_FINDERS = {"amount": amount_found, "date": date_found, "pin": pin_found}


def main() -> int:
    cfg = read_json_config(HERE / "trial_config.json", {"currency_words": list})
    rules, row_rules = load_matching_rules(), load_row_rules()
    cases = real_cases(ROOT, cfg) + all_cases()
    prepared, trial_rows = {}, {}
    app_tally, trial_tally = Counter(), Counter()
    disagreements = []
    for c in cases:
        key = id(c.segments)
        if key not in prepared:
            prepared[key] = prepare_page(group_rows(c.segments, row_rules), rules)
        query = Query(**{c.kind: c.claim})
        app_found = any(h.strength in (EXACT, CORRECTED) for h in search_page(prepared[key], query, rules))
        rule, settings = WINNERS[c.kind]
        tkey = (key, settings)
        if tkey not in trial_rows:
            trial_rows[tkey] = page_rows(c.segments, settings)
        trial_found = TRIAL_FINDERS[c.kind](rule, c.claim, trial_rows[tkey], cfg)
        for tally, f in ((app_tally, app_found), (trial_tally, trial_found)):
            tally[(c.kind, c.source, c.expected, f)] += 1
        if app_found != trial_found:
            disagreements.append((c.kind, c.category, c.label[-40:], app_found, trial_found))

    print(f"{len(cases)} cases\n")
    print(f"{'key':7} {'source':10} {'found (app / trial)':>24} {'false matches (app / trial)':>30}")
    for kind in ("amount", "date", "pin"):
        for src in ("real", "synthetic"):
            pos = sum(v for (k, s, e, f), v in app_tally.items() if k == kind and s == src and e)
            neg = sum(v for (k, s, e, f), v in app_tally.items() if k == kind and s == src and not e)
            af, tf = app_tally[(kind, src, True, True)], trial_tally[(kind, src, True, True)]
            afm, tfm = app_tally[(kind, src, False, True)], trial_tally[(kind, src, False, True)]
            print(f"{kind:7} {src:10} {af:>8}/{pos:<5} {tf:>5}/{pos:<5} {afm:>12}/{neg:<6} {tfm:>6}/{neg:<6}")
    print(f"\ncases where the application and the trial winner disagree: {len(disagreements)}")
    for d in disagreements[:40]:
        print("  ", ascii(d))
    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
