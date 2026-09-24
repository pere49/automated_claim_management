"""PROTOTYPE (tools/) — search-criteria trial: the candidate matching rules.

Each rule answers one closed question: "does this claimed value appear on
this page (given as rows of tokens)?" Values are compared exactly after
normalisation; the rules differ only in what normalisation and context they
allow. All word lists come from trial_config.json.

Amounts
  A1 naive     any printed form as a substring of the row text (baseline, unsafe)
  A2 strict    a whitespace token equal to a with-cents form
  A3 trimmed   A2 after trimming an attached currency word, "/=", a trailing
               tax-code letter and sentence punctuation from the token
  A4 +bare     A3, and no-cents forms ("1,200") anywhere as a token
  A5 +bare-ctx A3, and no-cents forms only with a currency word or "/=" on
               the same token or the next/previous token, or a total label
               right before
  A6 +bare-row A3, and no-cents forms when the row has a currency word anywhere
  A7 +bare-ctx2 A5, but a no-cents number found only through a total label must
               end the row or be followed by a currency word ("Total 575 CREDIT"
               is not money)
  A9 +marks    A7 plus the fused-word split, a leading printer mark ("*1.130.45")
               trimmed, and a one-decimal form for whole tens of cents
               ("6175.0" for 6175.00, "0.0" for 0.00)
  A8 +faded    A7, and two OCR artefacts undone first: a decimal point too faint
               to read ("430 00 KSh": number, space, exactly two digits, then a
               currency word) and an amount fused to the next word by a full
               stop ("Ksh5.00.Amount")
Dates
  D1 exact     a token equal to a numeric form (d/m/y in every zero, separator
               and 2/4-digit-year variant, and y-m-d)
  D2 +names    D1, and month-name forms over one or more tokens
               ("03 Aug 2026", "3 August 2026", "03-Aug-2026")
  D3 +label    D2 after trimming a "Label:" prefix and punctuation from tokens
  D4 +fused    D3, and a form followed directly by a time ("...2026193:33:31")
PINs
  P1 exact     a token equal to the PIN
  P2 tidy      P1 after trimming a "Label:" prefix and punctuation, any case
  P3 format    P2, and letters in digit positions / digits in letter positions
               (per pin_formats) mapped back before comparing
  P4 +any1     P3, or exactly one character different (any character)
  P5 +look1    P3, or exactly one character different where the pair is a
               known OCR look-alike (lookalike_pairs)
  P6 +glued    P5, and a PIN with a configured label word fused in front of
               it ("PinA012345678Z") -- the label is removed, nothing else
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

# ---------------------------------------------------------------- amounts


def amount_forms(value: Decimal, cfg: dict, one_decimal: bool = False) -> tuple[set[str], set[str]]:
    """(with-cents forms, no-cents forms). No-cents forms exist only for whole amounts."""
    whole, cents = f"{value:.2f}".split(".")
    grouped = f"{int(whole):,}"
    with_cents, no_cents = set(), set()
    for sep in cfg["thousands_separators"]:
        g = grouped.replace(",", sep)
        with_cents.add(f"{g}.{cents}")
        if one_decimal and cents[1] == "0":
            with_cents.add(f"{g}.{cents[0]}")
        if cents == "00":
            no_cents.add(g)
    return with_cents, no_cents


def _trim(token: str, cfg: dict, marks: bool = False) -> tuple[str, bool]:
    """Token core and whether a currency word or no-cents ending was attached."""
    t, attached = token, False
    if marks:
        while t and t[0] in cfg.get("amount_prefix_marks", []):
            t = t[1:]
    while t and t[-1] in ".,;:" and not re.search(r"\d[.,]\d{2}$", t):
        t = t[:-1]
    for end in cfg["no_cents_endings"]:
        if t.endswith(end):
            t, attached = t[: -len(end)], True
    for cur in sorted(cfg["currency_words"], key=len, reverse=True):
        if t.lower().startswith(cur.lower()) and t[len(cur):len(cur) + 1].isdigit():
            t, attached = t[len(cur):], True
            break
    for cur in sorted(cfg["currency_words"], key=len, reverse=True):
        if t.lower().endswith(cur.lower()) and t[: -len(cur)][-1:].isdigit():
            t, attached = t[: -len(cur)], True
            break
    if len(t) > 1 and t[-1] in cfg["tax_code_letters"] and t[-2].isdigit():
        t = t[:-1]
    return t, attached


def _is_currency(token: str, cfg: dict) -> bool:
    words = {c.lower() for c in cfg["currency_words"]} | set(cfg["no_cents_endings"])
    return token.strip(".,:;").lower() in words


def _label_before(tokens: list[str], i: int, cfg: dict) -> bool:
    labels = {lab.lower() for lab in cfg["total_labels"]}
    for n in (1, 2, 3):
        if i - n >= 0 and " ".join(tokens[i - n:i]).lower().rstrip(":") in labels:
            return True
    return False


def _undo_ocr_artefacts(tokens: list[str], cfg: dict) -> list[str]:
    out: list[str] = []
    for tok in tokens:
        out.extend(re.split(r"(?<=\d[.,]\d{2})\.(?=[A-Za-z])", tok))
    merged: list[str] = []
    i = 0
    while i < len(out):
        if i + 2 < len(out) and re.fullmatch(r"\d[\d,]*", out[i]) and re.fullmatch(r"\d{2}", out[i + 1]) \
                and _is_currency(out[i + 2], cfg):
            merged.append(f"{out[i]}.{out[i + 1]}")
            i += 2
            continue
        merged.append(out[i])
        i += 1
    return merged


def _split_fused(tokens: list[str]) -> list[str]:
    return [p for tok in tokens for p in re.split(r"(?<=\d[.,]\d{2})\.(?=[A-Za-z])", tok)]


def amount_found(rule: str, value: Decimal, rows: list[list[str]], cfg: dict) -> bool:
    cents_forms, bare_forms = amount_forms(value, cfg, one_decimal=(rule == "A9"))
    if rule == "A8":
        rows = [_undo_ocr_artefacts(t, cfg) for t in rows]
    if rule == "A9":
        rows = [_split_fused(t) for t in rows]
    for tokens in rows:
        if rule == "A1":
            text = " ".join(tokens)
            if any(f and f in text for f in cents_forms | bare_forms):
                return True
            continue
        for i, tok in enumerate(tokens):
            if rule == "A2":
                if tok in cents_forms:
                    return True
                continue
            core, attached = _trim(tok, cfg, marks=(rule == "A9"))
            if core in cents_forms:
                return True
            if core not in bare_forms:
                continue
            if rule == "A4":
                return True
            if rule in ("A5", "A7", "A8", "A9"):
                after = tokens[i + 1] if i + 1 < len(tokens) else None
                beside = (i > 0 and _is_currency(tokens[i - 1], cfg)) or \
                         (after is not None and _is_currency(after, cfg))
                if attached or beside:
                    return True
                if _label_before(tokens, i, cfg) and (rule == "A5" or after is None):
                    return True
            if rule == "A6" and (attached or any(_is_currency(t, cfg) or _trim(t, cfg)[1] for t in tokens)):
                return True
    return False


# ---------------------------------------------------------------- dates


def date_forms(d: date, cfg: dict) -> tuple[set[str], list[list[str]]]:
    """(single-token numeric forms, multi-token month-name forms as token lists)."""
    days, months = {str(d.day), f"{d.day:02d}"}, {str(d.month), f"{d.month:02d}"}
    years = {str(d.year), f"{d.year % 100:02d}"}
    numeric = {f"{dd}{s}{mm}{s}{yy}" for dd in days for mm in months for yy in years for s in cfg["date_separators"]}
    numeric |= {f"{d.year}-{d.month:02d}-{d.day:02d}", f"{d.year}/{d.month:02d}/{d.day:02d}"}
    named: list[list[str]] = []
    for name in cfg["month_names"][str(d.month)]:
        for dd in days:
            for yy in years:
                named.append([dd, name, yy])
                named.append([name, f"{dd},", yy])
                named.append([name, dd, yy])
                numeric.add(f"{dd}-{name}-{yy}")
    return numeric, named


def _label_trim(token: str) -> str:
    token = re.sub(r"^[A-Za-z .#]*:", "", token)
    return token.strip(".,;")


def date_found(rule: str, d: date, rows: list[list[str]], cfg: dict) -> bool:
    numeric, named = date_forms(d, cfg)
    lower_numeric = {f.lower() for f in numeric}
    for tokens in rows:
        cores = [(_label_trim(t) if rule in ("D3", "D4") else t) for t in tokens]
        for core in cores:
            if core.lower() in lower_numeric:
                return True
            if rule == "D4":
                for f in numeric:
                    if core.lower().startswith(f.lower()) and re.match(r"\d{1,3}:\d{2}", core[len(f):]):
                        return True
        if rule in ("D2", "D3", "D4"):
            low = [c.lower().strip(",") for c in cores]
            for form in named:
                want = [w.lower().strip(",") for w in form]
                n = len(want)
                if any(low[i:i + n] == want for i in range(len(low) - n + 1)):
                    return True
    return False


# ---------------------------------------------------------------- PINs


def _format_of(pin: str, cfg: dict) -> str | None:
    shape = "".join("D" if c.isdigit() else "L" for c in pin)
    return shape if shape in cfg["pin_formats"] else None


def _positional(token: str, fmt: str, cfg: dict) -> str:
    out = []
    for c, kind in zip(token, fmt):
        if kind == "D" and not c.isdigit():
            c = cfg["letter_to_digit"].get(c, c)
        elif kind == "L" and c.isdigit():
            c = cfg["digit_to_letter"].get(c, c)
        out.append(c)
    return "".join(out)


def _unglue_label(core: str, length: int, cfg: dict) -> str:
    head, tail = core[:-length], core[-length:]
    return tail if head and head.lower() in set(cfg.get("pin_labels", [])) else core


def pin_found(rule: str, pin: str, rows: list[list[str]], cfg: dict) -> bool:
    pin_u = pin.upper()
    fmt = _format_of(pin_u, cfg)
    pairs = {frozenset(p) for p in cfg["lookalike_pairs"]}
    for tokens in rows:
        for tok in tokens:
            if rule == "P1":
                if tok == pin:
                    return True
                continue
            core = _label_trim(tok).upper()
            if rule == "P6" and len(core) > len(pin_u):
                core = _unglue_label(core, len(pin_u), cfg)
            if core == pin_u:
                return True
            if rule == "P2" or len(core) != len(pin_u):
                continue
            norm = _positional(core, fmt, cfg) if fmt else core
            if norm == pin_u:
                return True
            diffs = [(raw, n, p) for raw, n, p in zip(core, norm, pin_u) if n != p]
            if len(diffs) != 1:
                continue
            if rule == "P4":
                return True
            raw, n, p = diffs[0]
            if rule in ("P5", "P6") and (frozenset((raw, p)) in pairs or frozenset((n, p)) in pairs):
                return True
    return False
