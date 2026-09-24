"""ReceiptFacts: everything about a receipts document that does not depend on the claim.

Worked out once when the receipts have been read, then shared by every
claimed amount (and re-used when the officer flips the PIN switch):
the PIN scan (D23), the repeated pages (D29), and per page where it prints
its total and the amount printed there, whether it names another buyer, the
whole parts of amounts printed with cents, the dates it prints, and an index
of which pages print which amount text — so each claimed amount is searched
in full only on the pages that can hold it (D28; measured identical to
searching every page). It also keeps the rules and the company PIN it was
worked out with, so a later step can search a page for a date (D35's date
link) the same way — never logged, never shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.checking.page_facts import (TotalMarks, fingerprint, names_other_buyer, total_marks, total_value,
                                     whole_parts)
from app.checking.repeats import repeated_pages
from app.checking.rules import CheckingRules
from app.matching import (DATE, PIN, Hit, MatchingRules, PreparedPage, Query, amount_forms, amount_texts,
                          search_document, search_page)


@dataclass
class ReceiptFacts:
    pages: dict[int, PreparedPage]           # every page read (and searchable)
    page_count: int
    unread: list[int]                        # pages with no usable reading
    pin_pages: list[int]                     # pages printing the company PIN
    repeats: list[tuple[int, int]]           # (earlier page, the page repeating it)
    look_above: bool = True                  # a total label may stand above the amount as its column header
    totals: dict[int, TotalMarks] = field(default_factory=dict)
    printed_total: dict[int, Decimal | None] = field(default_factory=dict)   # what each page prints as its total
    other_buyer: set[int] = field(default_factory=set)
    whole: dict[int, set[str]] = field(default_factory=dict)
    dates: dict[int, frozenset[date]] = field(default_factory=dict)
    pin_hits: dict[int, list[Hit]] = field(default_factory=dict)
    rules: CheckingRules | None = None
    matching: MatchingRules | None = None
    _printed: dict[str, set[int]] = field(default_factory=dict)
    _by_whole: dict[str, set[int]] = field(default_factory=dict)
    _date_hits: dict[tuple[int, date], list[Hit]] = field(default_factory=dict)

    @property
    def repeat_of(self) -> dict[int, int]:
        """Later page -> the earlier page it repeats."""
        return {later: earlier for earlier, later in self.repeats}

    def pages_for(self, amount: Decimal, matching: MatchingRules) -> list[int]:
        """Pages that can print this amount: exactly, faded, or with its cents dropped."""
        forms = amount_forms(amount, matching)
        found = set().union(*(self._printed.get(f, ()) for f in forms.with_cents | forms.without_cents),
                            *(self._by_whole.get(w, ()) for w in forms.without_cents))
        return sorted(found)

    def date_hits(self, page: int, day: date) -> list[Hit]:
        """Where page `page` prints `day` (searched once, then remembered)."""
        key = (page, day)
        if key not in self._date_hits:
            found = search_page(self.pages[page], Query(date=day), self.matching) if page in self.pages else []
            self._date_hits[key] = [h for h in found if h.key == DATE]
        return self._date_hits[key]


def analyse_receipts(pages: dict[int, PreparedPage], page_count: int, unread: list[int], pin: str | None,
                     rules: CheckingRules, matching: MatchingRules) -> ReceiptFacts:
    scan = search_document(pages, Query(pin=pin), matching) if pin else None
    pin_pages = scan.pages_with(PIN) if scan else []
    prints = {n: fingerprint(p, rules) for n, p in pages.items()}
    facts = ReceiptFacts(pages, page_count, sorted(unread), pin_pages, repeated_pages(prints, rules),
                         rules.total_label_above, rules=rules, matching=matching)
    for n in pin_pages:
        facts.pin_hits[n] = [h for h in scan.pages[n].hits if h.key == PIN]
    for n, page in pages.items():
        facts.totals[n] = total_marks(page, rules)
        facts.printed_total[n] = total_value(page, facts.totals[n], rules.total_label_above)
        if names_other_buyer(page, pin, rules, matching):
            facts.other_buyer.add(n)
        facts.whole[n] = whole_parts(page)
        facts.dates[n] = prints[n].dates
        for text in amount_texts(page, matching):
            facts._printed.setdefault(text, set()).add(n)
        for w in facts.whole[n]:
            facts._by_whole.setdefault(w, set()).add(n)
    return facts
