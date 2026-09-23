"""PROTOTYPE (tools/) — detection-resolution trial, step 2 of 2: score the readings.

Compares every variant in outputs/ocr_resolution_trial/readings.json with the
hand-checked answer key (private/ground_truth.json) and with the current
setting's reading:

  found      answer-key values read exactly, searched the way the matcher
             will: text grouped into printed rows (app/layout), each amount
             tried in its printed forms (2406.94, 2,406.94, 2.406.94 ...),
             dates and IDs exactly as printed, with and without the spaces
             OCR puts between split segments.
  changed    amount/date/PIN tokens a variant reads that the current setting
             does not (new) or no longer reads (lost); new ones not in the
             answer key are counted as misreads.
  text       how much of each page's full text differs from the current
             reading (1 - similarity).
  speed      seconds per page, and detection's share.

    .venv/Scripts/python.exe tools/ocr_resolution_trial/score.py

Prints the comparison and writes summary.json beside readings.json.
Not part of the application.
"""

from __future__ import annotations

import difflib
import json
import re
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config_files import read_json_config  # noqa: E402
from app.layout import group_rows, load_row_rules  # noqa: E402

CONFIG = Path(__file__).resolve().with_name("trial_config.json")
THOUSANDS_MARKS = [",", ".", " ", ""]


def page_rows(words: list[dict], rules) -> list[str]:
    segs = [SimpleNamespace(text=w["text"], box=w["box"]) for w in words]
    rows = [r.text for r in group_rows(segs, rules)]
    return rows + [r.replace(" ", "") for r in rows]


def amount_forms(canonical: str) -> list[str]:
    whole, cents = canonical.split(".")
    groups = []
    rest = whole
    while len(rest) > 3:
        groups.insert(0, rest[-3:])
        rest = rest[:-3]
    groups.insert(0, rest)
    return sorted({mark.join(groups) + "." + cents for mark in THOUSANDS_MARKS})


def present(value: str, rows: list[str], digits_only: bool) -> bool:
    edge = r"\d" if digits_only else r"[A-Za-z0-9]"
    pattern = re.compile(rf"(?<!{edge}){re.escape(value)}(?!{edge})")
    return any(pattern.search(r) for r in rows)


def found(truth: dict, rows: list[str]) -> tuple[int, int, list[str]]:
    hits, total, missed = 0, 0, []
    for amount in truth.get("amounts", []):
        total += 1
        if any(present(f, rows, True) for f in amount_forms(amount)):
            hits += 1
        else:
            missed.append(amount)
    for value in truth.get("dates", []) + truth.get("ids", []):
        total += 1
        if present(value, rows, False):
            hits += 1
        else:
            missed.append(value)
    return hits, total, missed


def tokens(rows: list[str], patterns: dict[str, re.Pattern]) -> set[str]:
    out = set()
    for kind, pattern in patterns.items():
        for row in rows:
            out.update(f"{kind}:{m}" for m in pattern.findall(row))
    return out


def truth_tokens(truth: dict) -> set[str]:
    out = {f"date:{d}" for d in truth.get("dates", [])} | {f"pin:{i}" for i in truth.get("ids", [])}
    for amount in truth.get("amounts", []):
        out.update(f"amount:{f}" for f in amount_forms(amount))
    return out


def main() -> None:
    cfg = read_json_config(CONFIG, {"output_folder": str, "ground_truth": str, "key_value_patterns": dict})
    readings = json.loads((ROOT / cfg["output_folder"] / "readings.json").read_text(encoding="utf-8"))
    truth = json.loads((ROOT / cfg["ground_truth"]).read_text(encoding="utf-8"))["pages"]
    patterns = {k: re.compile(v) for k, v in cfg["key_value_patterns"].items()}
    rules = load_row_rules()
    names = list(readings)
    current = names[0]
    base = {r["page"]: r for r in readings[current]}
    base_rows = {p: page_rows(r["words"], rules) for p, r in base.items()}
    base_tokens = {p: tokens(rows, patterns) for p, rows in base_rows.items()}
    base_text = {p: "\n".join(w["text"] for w in r["words"]) for p, r in base.items()}
    base_secs = statistics.fmean(r["seconds"] for r in readings[current])

    summary = {}
    print(f"{'variant':26} {'s/page':>7} {'faster':>7} {'detect s':>9} {'found':>11} {'lost':>5} {'new':>5} "
          f"{'misread':>8} {'text changed':>13} {'pages same':>11}")
    for name in names:
        rows_all = readings[name]
        hits = total = lost = new = misread = same = 0
        text_change, per_page = [], {}
        for r in rows_all:
            page = r["page"]
            rows = page_rows(r["words"], rules)
            t = truth.get(page, {})
            h, n, missed = found(t, rows)
            hits, total = hits + h, total + n
            toks = tokens(rows, patterns)
            added, gone = toks - base_tokens[page], base_tokens[page] - toks
            lost, new = lost + len(gone), new + len(added)
            wrong = added - truth_tokens(t)
            misread += len(wrong)
            text = "\n".join(w["text"] for w in r["words"])
            ratio = difflib.SequenceMatcher(None, base_text[page], text, autojunk=False).ratio()
            text_change.append(1 - ratio)
            same += text == base_text[page]
            per_page[page] = {"found": h, "of": n, "missed": missed, "lost": sorted(gone), "new": sorted(added),
                              "misread": sorted(wrong), "text_changed": round(1 - ratio, 4),
                              "seconds": r["seconds"], "det_cls_rec": r["det_cls_rec"]}
        secs = statistics.fmean(r["seconds"] for r in rows_all)
        det = statistics.fmean(r["det_cls_rec"][0] for r in rows_all if r["det_cls_rec"])
        summary[name] = {"seconds_per_page": round(secs, 2), "faster_pct": round(100 * (1 - secs / base_secs), 1),
                         "detect_seconds": round(det, 2), "found": hits, "of": total,
                         "lost_vs_current": lost, "new_vs_current": new, "new_misreads": misread,
                         "mean_text_changed_pct": round(100 * statistics.fmean(text_change), 2),
                         "pages_identical": same, "pages": per_page}
        print(f"{name:26} {secs:7.2f} {summary[name]['faster_pct']:6.1f}% {det:9.2f} {hits:4d}/{total:<4d}"
              f"({100 * hits / total:4.1f}%) {lost:5d} {new:5d} {misread:8d} "
              f"{summary[name]['mean_text_changed_pct']:12.2f}% {same:5d}/{len(rows_all)}")

    print("\nAnswer-key values each variant missed that the current setting found, or found that current missed:")
    cur_missed = {p: set(v["missed"]) for p, v in summary[current]["pages"].items()}
    for name in names[1:]:
        for page, v in summary[name]["pages"].items():
            worse, better = set(v["missed"]) - cur_missed[page], cur_missed[page] - set(v["missed"])
            if worse or better or v["misread"]:
                print(f"  {name:22} {page:48} missed {sorted(worse)} | recovered {sorted(better)} | misread {v['misread']}")
    print("\nCurrent setting's own misses (answer-key values not read at all):")
    for page, v in summary[current]["pages"].items():
        if v["missed"]:
            print(f"  {page:48} {v['missed']}")
    out = ROOT / cfg["output_folder"] / "summary.json"
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nwritten: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
