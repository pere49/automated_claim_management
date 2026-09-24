"""PROTOTYPE (tools/) — Stage C checking end to end, on saved OCR readings.

The design of blueprint §6 (decisions D23-D30) as one small program, to try it
on the owner's real claim pairs before app/checking is built:
  1 PIN scan        the company PIN on any page -> "PIN required" starts on
  2 repeated pages  text / moment (tools/duplicate_pages_trial/checks.py, indexed); the
                    references check was dropped once measured one document at a time
  3 amount index    amount text -> pages; whole part of an amount printed with cents -> pages
  4 pairing         two passes over the claim items in sheet order (exact amounts first, then
                    cents dropped): the first page carrying the item's amount and date (and
                    the PIN when required) that is not already paired, and is not the later
                    copy of a repeated page, is paired with the item and taken out of every
                    later search
  5 double claim    an unpaired item whose amount and date are on the later copy of a page
                    paired with another item of the same amount and date -> both red
  6 verdict         green / yellow with the nearest miss / red
Not used by the application.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.layout import group_rows
from app.matching import Query, prepare_page, search_document
from app.matching.amount_search import _faded, trim  # prototype: the app would export these
from app.matching.money import amount_forms

CENTS = re.compile(r"(.+)[.,](\d{2})")
GREEN, YELLOW, RED = "green", "yellow", "red"


@dataclass(frozen=True)
class Item:
    row: int
    column: str
    amount: Decimal
    date: date | None


@dataclass
class Outcome:
    item: Item
    colour: str
    page: int | None
    reason: str


@dataclass
class Document:
    pages: dict                          # page number -> PreparedPage
    segments: dict                       # page number -> OCR segment texts, reading order
    rows: dict                           # page number -> printed rows of segment texts
    floors: dict = field(default_factory=dict)


def prepare(words_by_page: dict[int, list[dict]], rules, row_rules) -> Document:
    doc = Document({}, {}, {})
    for n, words in sorted(words_by_page.items()):
        grouped = group_rows([SimpleNamespace(text=w["text"], box=w["box"]) for w in words], row_rules)
        doc.pages[n] = prepare_page(grouped, rules)
        doc.segments[n] = [w["text"] for w in words]
        doc.rows[n] = [[s.text for s in r.segments] for r in grouped]
        doc.floors[n] = {m.group(1) for row in doc.pages[n].amount_cores for core, _ in row
                         if (m := CENTS.fullmatch(core)) and m.group(2) != "00"}
    return doc


def pin_pages(doc: Document, pin: str, rules) -> list[int]:
    return search_document(doc.pages, Query(pin=pin), rules).pages_with("pin")


def repeated_pages(doc: Document, checks) -> list[tuple[int, int]]:
    numbers = sorted(doc.pages)
    fps = [checks.fingerprint(doc.segments[n], doc.rows[n]) for n in numbers]
    found = set()
    for check in ("text", "moment"):
        found |= checks.indexed(fps, check)
    return sorted((numbers[i], numbers[j]) for i, j in found)


def check(items: list[Item], doc: Document, rules, pin: str, pin_required: bool,
          repeats: list[tuple[int, int]]) -> list[Outcome]:
    printed, whole = _index(doc, rules)
    later_copy = {b: a for a, b in repeats}
    found = [_find(it, doc, rules, pin, printed, whole) for it in items]

    taken: dict[int, int] = {}          # page -> item paired with it
    paired: dict[int, int] = {}         # item -> its page
    for kind in ("exact", "dropped"):
        for i, (it, f) in enumerate(zip(items, found)):
            if i in paired or it.date is None:
                continue
            for n in f[kind]:
                if n not in taken and n not in later_copy and n in f["date"] and (n in f["pin"] or not pin_required):
                    taken[n], paired[i] = i, n
                    break

    red = set()
    for i, (it, f) in enumerate(zip(items, found)):
        if i in paired or it.date is None:
            continue
        for n in f["exact"] + f["dropped"]:
            j = taken.get(later_copy.get(n))
            if n in later_copy and n in f["date"] and j is not None \
                    and items[j].amount == it.amount and items[j].date == it.date:
                red |= {i, j}

    out = []
    for i, (it, f) in enumerate(zip(items, found)):
        if i in red:
            other = next(j for j in red if j != i and items[j].amount == it.amount and items[j].date == it.date)
            page = paired.get(i, paired.get(other))
            out.append(Outcome(it, RED, page, f"one receipt (p.{page}, repeated as p."
                                              f"{next(b for b, a in later_copy.items() if a == page)}) "
                                              f"for two claims: rows {items[min(i, other)].row} and {items[max(i, other)].row}"))
        elif i in paired:
            how = "exact" if paired[i] in f["exact"] else "cents dropped"
            out.append(Outcome(it, GREEN, paired[i], f"amount ({how}) + date{' + PIN' if pin_required else ''}"))
        else:
            out.append(Outcome(it, YELLOW, *_nearest_miss(it, f, taken, items, later_copy, pin_required)))
    return out


def _index(doc: Document, rules) -> tuple[dict, dict]:
    printed, whole = {}, {}
    for n, p in doc.pages.items():
        for tokens, cores in zip(p.amounts, p.amount_cores):
            for core, _ in cores:
                printed.setdefault(core, set()).add(n)
            for _, text in _faded(tokens, rules):
                printed.setdefault(trim(text, rules)[0], set()).add(n)
        for w in doc.floors[n]:
            whole.setdefault(w, set()).add(n)
    return printed, whole


def _find(it: Item, doc: Document, rules, pin: str, printed: dict, whole: dict) -> dict:
    forms = amount_forms(it.amount, rules)
    wanted = set().union(*(printed.get(f, ()) for f in forms.with_cents | forms.without_cents),
                         *(whole.get(w, ()) for w in forms.without_cents))
    empty = {"exact": [], "dropped": [], "possible": [], "date": set(), "pin": set()}
    if not wanted:
        return empty
    res = search_document({n: doc.pages[n] for n in sorted(wanted)}, Query(date=it.date, amount=it.amount, pin=pin), rules)
    exact = res.pages_with("amount")
    return {
        "exact": exact,
        "dropped": [n for n in sorted(wanted) if n not in exact and doc.floors[n] & forms.without_cents],
        "possible": res.pages_possible("amount"),
        "date": {n for n in res.pages if res.pages[n].found("date")},
        "pin": {n for n in res.pages if res.pages[n].found("pin")},
    }


def _nearest_miss(it: Item, f: dict, taken: dict, items: list[Item], later_copy: dict,
                  pin_required: bool) -> tuple[int | None, str]:
    if it.date is None:
        return None, "no date on the claim sheet"
    pages = f["exact"] + f["dropped"]
    if not pages:
        if f["possible"]:
            return f["possible"][0], f"only a possible match (faded decimal point) on p.{f['possible'][0]}"
        return None, "amount not found on any receipt page"
    with_date = [n for n in pages if n in f["date"]]
    for n in with_date:
        if n in taken:
            other = items[taken[n]]
            return n, f"amount and date on p.{n}, already paired with row {other.row} ({other.column})"
    for n in with_date:
        if n in later_copy:
            return n, f"its receipt p.{n} repeats p.{later_copy[n]}"
    if with_date and pin_required:
        return with_date[0], f"amount and date on p.{with_date[0]}, but no PIN"
    return pages[0], f"amount on p.{pages[0]}, but not the date {it.date:%d %b %Y}"
