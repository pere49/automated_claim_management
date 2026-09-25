"""PROTOTYPE (tools/) — search-criteria trial: test cases from the real pages.

Uses the current OCR reading of every page (outputs/ocr_resolution_trial/
readings.json) and the hand-checked answer key. Values the answer key says
are printed on a page must be found there; decoys must not be:

  amounts   one cent more, one unit more, ten times; another page's amount;
            a counter or receipt number (a whole number standing alone on a
            row with no currency word); digits taken from inside a longer
            number (PINs, phone numbers, codes)
  dates     next day, day and month swapped, previous year
  PINs      one digit changed (not a look-alike); one look-alike digit
            changed (cannot be told from a misread; reported separately);
            another page's PIN

A decoy is dropped when there is any sign it is really printed on the page:
it is in the page's answer key, or it appears on the page as a whole token.
Holds real values: results go to outputs/ (ignored by git).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from cases_synthetic import Case
from criteria import _trim, amount_forms

MAX_EMBEDDED_PER_PAGE = 15


def load_pages(root: Path, readings_file: str, variant: str) -> dict[str, list]:
    readings = json.loads((root / readings_file).read_text(encoding="utf-8"))[variant]
    return {p["page"]: [SimpleNamespace(text=w["text"], box=w["box"]) for w in p["words"]] for p in readings}


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                         "nov", "dec"], start=1)}


def parse_printed_date(text: str) -> date | None:
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})", text)
    named = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{2}|\d{4})", text)
    if named:
        d, mth, y = int(named.group(1)), MONTHS.get(named.group(2).lower()), int(named.group(3))
        if mth is None:
            return None
    elif m:
        d, mth, y = (int(g) for g in m.groups())
    else:
        return None
    try:
        return date(y + 2000 if y < 100 else y, mth, d)  # day-first, as confirmed for these receipts
    except ValueError:
        return None


def real_cases(root: Path, cfg: dict) -> list[Case]:
    cases: list[Case] = []
    for src in cfg["real_sources"]:
        truth = json.loads((root / src["ground_truth"]).read_text(encoding="utf-8"))["pages"]
        pages = load_pages(root, src["readings"], src["variant"])
        pages = {k: v for k, v in pages.items() if k in truth}
        cases += _cases_for(pages, truth, cfg)
    return cases


def _cases_for(pages: dict, truth: dict, cfg: dict) -> list[Case]:
    pin_re = re.compile("|".join(
        "".join("[A-Z]" if k == "L" else r"\d" for k in fmt) for fmt in cfg["pin_formats"]))
    pairs = {frozenset(p) for p in cfg["lookalike_pairs"]}
    cases: list[Case] = []

    all_amounts = {p: {Decimal(a) for a in t.get("amounts", [])} for p, t in truth.items()}
    all_pins = {p: {i for i in t.get("ids", []) if pin_re.fullmatch(i)} for p, t in truth.items()}

    for page, segs in pages.items():
        t = truth.get(page, {})
        tokens = {tok for s in segs for tok in s.text.split()}
        stripped = {tok.strip(".,:;") for tok in tokens}
        amounts = all_amounts.get(page, set())

        cores = {_trim(tok, cfg, marks=True)[0] for tok in tokens} | stripped

        def printed(v: Decimal) -> bool:
            """Any sign the value is really on the page (answer key, or any printed form of it as a token):
            such a value is not used as a decoy, since the answer key only lists the values the rules rely on."""
            if v in amounts:
                return True
            cents_forms, bare_forms = amount_forms(v, cfg, one_decimal=True)
            return bool(cores & (cents_forms | bare_forms))

        def add(kind, claim, expected, category):
            cases.append(Case(kind, claim, segs, expected, category, source="real", label=page))

        # ---- amounts
        for a in amounts:
            add("amount", a, True, "real: amount printed on the page")
        for a in amounts:
            for decoy in (a + Decimal("0.01"), a + 1, a * 10):
                if decoy > 0 and not printed(decoy):
                    add("amount", decoy, False, "real trap: near miss of a printed amount")
        for other, others in all_amounts.items():
            if other == page:
                continue
            for a in others:
                if not printed(a):
                    add("amount", a, False, "real trap: another page's amount")
        rows_text = [s.text for s in segs]
        currency = re.compile("|".join(re.escape(c) for c in cfg["currency_words"]), re.I)
        for text in rows_text:
            if currency.search(text):
                continue
            for tok in text.split():
                if re.fullmatch(r"\d{2,6}", tok) and not printed(Decimal(tok)):
                    add("amount", Decimal(tok), False, "real trap: counter or receipt number")
        embedded = 0
        for tok in tokens:
            for run in re.findall(r"\d{6,}", tok):
                for start in range(0, len(run) - 3, 2):
                    piece = run[start:start + 3].lstrip("0")
                    if len(piece) == 3 and piece not in stripped and not printed(Decimal(piece)) \
                            and embedded < MAX_EMBEDDED_PER_PAGE:
                        add("amount", Decimal(piece), False, "real trap: digits inside a longer number")
                        embedded += 1

        # ---- dates
        page_dates = {d for d in (parse_printed_date(x) for x in t.get("dates", [])) if d}
        for d in page_dates:
            add("date", d, True, "real: date printed on the page")
            decoys = [d + timedelta(days=1), d.replace(year=d.year - 1)]
            if d.day <= 12 and d.day != d.month:
                decoys.append(date(d.year, d.day, d.month))
            for decoy in decoys:
                if decoy not in page_dates:
                    add("date", decoy, False, "real trap: near miss of a printed date")

        # ---- PINs
        pins = all_pins.get(page, set())
        for pin in pins:
            add("pin", pin, True, "real: PIN printed on the page")
            digits = [i for i, ch in enumerate(pin) if ch.isdigit()]
            for i in digits[2:5]:
                other = next(str(n) for n in range(10)
                             if str(n) != pin[i] and frozenset((str(n), pin[i])) not in pairs
                             and abs(n - int(pin[i])) >= 2)
                decoy = pin[:i] + other + pin[i + 1:]
                if decoy not in pins:
                    add("pin", decoy, False, "real trap: different PIN, one digit (not a look-alike)")
            look = next((i for i in digits if frozenset((pin[i], "8")) in pairs and pin[i] != "8"), None)
            if look is not None:
                decoy = pin[:look] + "8" + pin[look + 1:]
                if decoy not in pins:
                    add("pin", decoy, False,
                        "real trap: different PIN, one look-alike digit (cannot be told from a misread)")
        for other, others in all_pins.items():
            for pin in others - pins:
                add("pin", pin, False, "real trap: another page's PIN")
    return cases
