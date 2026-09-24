"""What each claimed amount's receipt page shows wrong, its colour, and every page's badge (D34, D35).

For an amount linked to a page (links.py): Amount — the page does not print
it as its total (not at all, only with a faded decimal point, or not on a
total row); Date — the claimed date is not printed there (or the sheet has
none that could be used); PIN — the company PIN is missing while required,
or the page names another buyer; Repeated — the page repeats another page,
or one receipt carries two claims. An amount linked to no page: No receipt
found. Colour rule B (owner, D34): the problems listed in red_problems are
red, every other problem yellow, none green.

Each page's badge: its amount's problems with the mismatch ("Amount 320.00 ≠
330.00", "Date 13 Aug ≠ 14 Aug"), or ✓; a page no amount is linked to shows
Date · Amount (plus PIN when missing and required); a repeated copy and a
page that could not be read say so, in red.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.checking.assignment import Pairing
from app.checking.findings import CENTS_DROPPED, EXACT_AMOUNT, ItemFindings
from app.checking.links import DATE_LINK, Links
from app.checking.model import (GREEN, P_AMOUNT, P_DATE, P_NO_RECEIPT, P_OTHER_BUYER, P_PIN, P_REPEATED,
                                P_UNREADABLE, PROBLEMS, RED, YELLOW, PageResult)
from app.checking.receipts import ReceiptFacts


@dataclass
class Judged:
    problems: tuple[str, ...]
    colour: str
    lines: tuple[str, ...]
    hits: list


def judge(findings: list[ItemFindings], pairing: Pairing, links: Links, facts: ReceiptFacts,
          pin_required: bool) -> tuple[list[Judged], dict[int, PageResult]]:
    """Every amount's problems and badge lines, and every receipt page's badge."""
    rules = facts.rules
    items = []
    for i, f in enumerate(findings):
        page = links.page_of.get(i)
        if page is None:
            items.append(Judged((P_NO_RECEIPT,), _colour({P_NO_RECEIPT}, rules), (rules.badge_lines["no_receipt"],),
                                []))
            continue
        problems = _problems(i, f, page, links, pairing, facts, pin_required)
        when = pairing.date_of.get(i)
        found = next((p for p in f.pages if p.page == page), None)
        hits = found.hits(when) if found else links.date_hits.get(i, []) + facts.pin_hits.get(page, [])
        items.append(Judged(problems, _colour(set(problems), rules), _lines(problems, f, page, when, facts), hits))

    linked = links.item_of
    pages: dict[int, PageResult] = {}
    for n in range(1, facts.page_count + 1):
        if n not in facts.pages:
            pages[n] = _page(n, (P_UNREADABLE,), (rules.badge_lines["unreadable"],), None, rules)
        elif n in linked:
            j = items[linked[n]]
            pages[n] = PageResult(n, j.colour, j.problems, j.lines or (rules.badge_lines["ok"],), linked[n])
        elif n in facts.repeat_of:
            pages[n] = _page(n, (P_REPEATED,), (rules.badge_lines["repeated"].format(page=facts.repeat_of[n]),),
                             None, rules)
        else:
            pin = _pin_problem(n, facts, pin_required)
            lines = (rules.badge_lines["no_claim"],) + ((rules.badge_lines[pin],) if pin else ())
            pages[n] = _page(n, (P_AMOUNT, P_DATE) + ((pin,) if pin else ()), lines, None, rules)
    return items, pages


def _problems(i: int, f: ItemFindings, page: int, links: Links, pairing: Pairing, facts: ReceiptFacts,
              pin_required: bool) -> tuple[str, ...]:
    found = next((p for p in f.pages if p.page == page), None)
    when = pairing.date_of.get(i)
    problems = set()
    if (f.item.amount is None or found is None or found.amount not in (EXACT_AMOUNT, CENTS_DROPPED)
            or not found.anchored):
        problems.add(P_AMOUNT)
    if when is None or (found is not None and when not in found.dates) or (found is None and links.how[i] != DATE_LINK):
        problems.add(P_DATE)
    pin = _pin_problem(page, facts, pin_required)
    if pin:
        problems.add(pin)
    if page in facts.repeat_of or i in pairing.red:
        problems.add(P_REPEATED)
    return tuple(p for p in PROBLEMS if p in problems)


def _pin_problem(page: int, facts: ReceiptFacts, pin_required: bool) -> str | None:
    if page in facts.other_buyer:
        return P_OTHER_BUYER
    if pin_required and page not in facts.pin_pages:
        return P_PIN
    return None


def _lines(problems: tuple[str, ...], f: ItemFindings, page: int, when: date | None,
           facts: ReceiptFacts) -> tuple[str, ...]:
    rules = facts.rules
    words = rules.badge_lines
    unknown = words["unknown"]
    out = []
    for key in problems:
        if key == P_AMOUNT:
            out.append(words[key].format(receipt=_money(facts.printed_total.get(page)) or unknown,
                                         claimed=_money(f.item.amount) or unknown))
        elif key == P_DATE:
            reading = f.item.date
            target = when or reading.value or (reading.candidates[0] if reading.candidates else None)
            if target is None:
                out.append(words["date_not_on_sheet"])
                continue
            printed = facts.dates.get(page, ())
            near = min(printed, key=lambda d: abs((d - target).days)) if printed else None
            if when or reading.value:
                claimed = _day(when or reading.value, rules)
            else:
                claimed = "/".join(_day(d, rules) for d in reading.candidates)
            out.append(words[key].format(receipt=_day(near, rules) if near else unknown, claimed=claimed))
        elif key == P_REPEATED:
            other = facts.repeat_of.get(page) or next((later for earlier, later in facts.repeats if earlier == page),
                                                      page)
            out.append(words[key].format(page=other))
        else:
            out.append(words[key])
    return tuple(out)


def _page(n: int, problems: tuple[str, ...], lines: tuple[str, ...], item: int | None, rules) -> PageResult:
    return PageResult(n, _colour(set(problems), rules), problems, lines, item)


def _colour(problems: set[str], rules) -> str:
    if not problems:
        return GREEN
    return RED if problems & rules.red_problems else YELLOW


def _money(value: Decimal | None) -> str | None:
    return f"{value:,.2f}" if value is not None else None


def _day(d: date, rules) -> str:
    return d.strftime(rules.badge_date_format)
