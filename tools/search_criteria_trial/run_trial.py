"""PROTOTYPE (tools/) — search-criteria trial: score every candidate rule.

    .venv/Scripts/python.exe tools/search_criteria_trial/run_trial.py

Runs every rule combination in criteria.py (with every way of joining split
segments from text_model.py) over the real and fabricated cases, and ranks
them: fewest false matches first (the governing rule: a wrong PASS is worse
than a REVIEW), then most values found. Cases in the category "cannot be
told from a misread" are reported separately and not used for ranking: any
rule that recovers a look-alike misread necessarily accepts the identical-
looking different PIN too, and that trade-off is the owner's decision.

Prints the comparison; writes outputs/search_criteria_trial/summary.json
(holds real values; ignored by git). Not part of the application.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cases_real import real_cases  # noqa: E402
from cases_synthetic import all_cases  # noqa: E402
from criteria import amount_found, date_found, pin_found  # noqa: E402
from text_model import ROOT, TextSettings, page_rows  # noqa: E402

sys.path.insert(0, str(ROOT))
from app.config_files import read_json_config  # noqa: E402

INHERENT = "cannot be told from a misread"


QUICK = "--quick" in sys.argv  # only the leading candidates (for large case sets)


def configurations(cfg: dict) -> dict[str, list[tuple[str, str, TextSettings]]]:
    if QUICK:
        tail = TextSettings("tail", cfg["join_gap_per_height"][1])
        amount = [(r, f"{r} join={jn}", ts) for r in ("A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9")
                  for jn, ts in (("none", TextSettings("none")), ("tail", tail))]
        return {"amount": amount,
                "date": [(r, f"{r} join=none", TextSettings("none")) for r in ("D1", "D2", "D3", "D4")],
                "pin": [(r, f"{r} join=none", TextSettings("none")) for r in ("P1", "P2", "P3", "P4", "P5", "P6")]}
    joins = [("none", TextSettings("none"))] + \
            [(f"near{g}", TextSettings("near", g)) for g in cfg["join_gap_per_height"]] + \
            [(f"tail{g}", TextSettings("tail", g)) for g in cfg["join_gap_per_height"]] + \
            [("all", TextSettings("all"))]
    amount = [(rule, f"{rule} join={jn} space1000={'on' if sp else 'off'}",
               TextSettings(ts.join, ts.gap_per_height, sp))
              for rule in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8") for jn, ts in joins for sp in (False, True)]
    dates = [(rule, f"{rule} join={jn}", ts) for rule in ("D1", "D2", "D3", "D4")
             for jn, ts in joins if jn in ("none", f"near{cfg['join_gap_per_height'][1]}")]
    pins = [(rule, f"{rule} join=none", TextSettings("none")) for rule in ("P1", "P2", "P3", "P4", "P5", "P6")]
    return {"amount": amount, "date": dates, "pin": pins}


def evaluate(kind: str, rule: str, settings: TextSettings, cases: list, cfg: dict, cache: dict) -> dict:
    finder = {"amount": amount_found, "date": date_found, "pin": pin_found}[kind]
    tally = Counter()
    per_cat = defaultdict(Counter)
    wrong: list[tuple[str, str, str]] = []
    start = time.perf_counter()
    for case in cases:
        key = (id(case.segments), settings)
        if key not in cache:
            cache[key] = page_rows(case.segments, settings)
        found = finder(rule, case.claim, cache[key], cfg)
        outcome = ("found" if found else "missed") if case.expected else ("FALSE MATCH" if found else "rejected")
        tally[(case.source, outcome, INHERENT in case.category)] += 1
        per_cat[case.category][outcome] += 1
        if outcome in ("missed", "FALSE MATCH"):
            wrong.append((outcome, case.category, case.label if case.source == "synthetic" else case.label))
    elapsed = (time.perf_counter() - start) / max(1, len(cases))
    return {"tally": tally, "per_category": per_cat, "wrong": wrong, "ms_per_search": elapsed * 1000}


def summarise(res: dict) -> dict:
    t = res["tally"]
    g = lambda src, out, inh=False: t[(src, out, inh)]  # noqa: E731
    return {
        "real_found": g("real", "found"), "real_positives": g("real", "found") + g("real", "missed"),
        "syn_found": g("synthetic", "found"), "syn_positives": g("synthetic", "found") + g("synthetic", "missed"),
        "real_false": g("real", "FALSE MATCH"), "real_traps": g("real", "FALSE MATCH") + g("real", "rejected"),
        "syn_false": g("synthetic", "FALSE MATCH"),
        "syn_traps": g("synthetic", "FALSE MATCH") + g("synthetic", "rejected"),
        "inherent_accepted": g("real", "FALSE MATCH", True) + g("synthetic", "FALSE MATCH", True),
        "inherent_total": sum(v for (s, o, inh), v in t.items() if inh),
    }


def main() -> None:
    cfg = read_json_config(HERE / "trial_config.json", {"currency_words": list, "output_folder": str})
    cases = real_cases(ROOT, cfg) + all_cases()
    by_kind = defaultdict(list)
    for c in cases:
        by_kind[c.kind].append(c)
    counts = Counter((c.kind, c.source, c.expected) for c in cases)
    print("cases:", ", ".join(f"{k}/{s}/{'find' if e else 'trap'}={n}" for (k, s, e), n in sorted(counts.items())))
    print(f"total cases: {len(cases)}\n")

    cache: dict = {}
    report = {}
    for kind, configs in configurations(cfg).items():
        rows = []
        for rule, name, settings in configs:
            res = evaluate(kind, rule, settings, by_kind[kind], cfg, cache)
            s = summarise(res)
            rows.append((s["real_false"] + s["syn_false"], -(s["real_found"] + s["syn_found"]), name, s, res))
        rows.sort(key=lambda r: (r[0], r[1]))
        print(f"=== {kind.upper()}  (ranked: fewest false matches, then most found)")
        print(f"{'rule':34} {'found real':>12} {'found fabricated':>17} {'false real':>11} {'false fabr.':>12}"
              f" {'look-alike accepted':>20} {'ms':>6}")
        shown = rows if kind != "amount" else rows[:14] + [r for r in rows[14:] if "A1" in r[2] or "A2" in r[2]][:3]
        for _, _, name, s, res in shown:
            print(f"{name:34} {s['real_found']:5d}/{s['real_positives']:<6d} {s['syn_found']:8d}/{s['syn_positives']:<8d}"
                  f" {s['real_false']:5d}/{s['real_traps']:<5d} {s['syn_false']:5d}/{s['syn_traps']:<6d}"
                  f" {s['inherent_accepted']:10d}/{s['inherent_total']:<9d} {res['ms_per_search']:6.3f}")
        best = rows[0]
        print(f"\n  best: {best[2]}")
        misses = Counter(c for o, c, _ in best[4]["wrong"] if o == "missed")
        falses = Counter(c for o, c, _ in best[4]["wrong"] if o == "FALSE MATCH" and INHERENT not in c)
        print("  still missed:", dict(misses) or "none")
        print("  false matches:", dict(falses) or "none")
        for o, c, label in best[4]["wrong"]:
            if "real" not in c and INHERENT not in c:
                print(f"    {o:11} {c:55} {label[:60]}")
        print()
        report[kind] = [{"rule": name, **s, "ms": res["ms_per_search"],
                         "per_category": {k: dict(v) for k, v in res["per_category"].items()},
                         "wrong": res["wrong"]} for _, _, name, s, res in rows]
    out = ROOT / cfg["output_folder"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"written: {(out / 'summary.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
