"""Dates: every printed form of a claimed date.

Day-first, as on every receipt seen so far: 03/08/2026, 3/8/26, 03-08-2026,
03.08.2026, 2026-08-03, 03 Aug 2026, 3 August 2026, Aug 3, 2026, 03-Aug-26.
Month names come from matching_rules.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.matching.rules import MatchingRules


@dataclass(frozen=True)
class DateForms:
    single: frozenset[str]                                  # one-token forms, lower case ("03/08/2026")
    multi: tuple[tuple[str, ...], ...]                      # several-token forms (("03", "aug", "2026"), ...)
    multi_by_first: dict[str, tuple[tuple[str, ...], ...]]  # the same, indexed by their first token


def date_forms(d: date, rules: MatchingRules) -> DateForms:
    days = {str(d.day), f"{d.day:02d}"}
    months = {str(d.month), f"{d.month:02d}"}
    years = {str(d.year), f"{d.year % 100:02d}"}
    single = {f"{dd}{s}{mm}{s}{yy}" for dd in days for mm in months for yy in years for s in rules.date_separators}
    single |= {f"{d.year}-{d.month:02d}-{d.day:02d}", f"{d.year}/{d.month:02d}/{d.day:02d}"}
    multi: list[tuple[str, ...]] = []
    for name in rules.month_names[d.month]:
        for dd in days:
            for yy in years:
                multi.append((dd, name, yy))
                multi.append((name, f"{dd},", yy))
                multi.append((name, dd, yy))
                single.add(f"{dd}-{name}-{yy}")
    forms = tuple(sorted({tuple(w.lower().strip(",") for w in form) for form in multi}))
    index: dict[str, list[tuple[str, ...]]] = {}
    for form in forms:
        index.setdefault(form[0], []).append(form)
    return DateForms(frozenset(f.lower() for f in single), forms, {k: tuple(v) for k, v in index.items()})
