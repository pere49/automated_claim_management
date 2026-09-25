"""PROTOTYPE (tools/) — search-criteria trial: fabricated test cases.

Every case is one claimed value, a small fabricated page (OCR-like segments
with positions) and the right answer: should the value be found or not. All
values and PINs here are invented. Categories name the trap or the printing
style being tested, so results can be read per category.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from text_model import segment

AMOUNTS = [Decimal(v) for v in ("500", "1200", "1060", "13000", "75", "2406.94", "45.50", "250000", "5000")]
DATES = [date(2026, 8, 3), date(2026, 7, 12), date(2026, 12, 25), date(2026, 5, 9)]
PINS = ["A012345678Z", "C051234567D", "B987650432K"]
TINS = ["1234509876"]


@dataclass
class Case:
    kind: str          # "amount" | "date" | "pin"
    claim: object      # Decimal | date | str
    segments: list
    expected: bool     # should the claim be found on this page?
    category: str
    source: str = "synthetic"
    label: str = ""    # short description, safe to print (fabricated)


def row(*parts, y=0.0):
    """Segments on one printed row: parts are (text, x) pairs."""
    return [segment(text, x, y) for text, x in parts]


def _comma(v: Decimal) -> str:
    return f"{v:,.2f}"


def _plain(v: Decimal) -> str:
    return f"{v:.2f}"


def _bare(v: Decimal) -> str:
    return f"{int(v):,}"


def _dot(v: Decimal) -> str:
    """Dot as thousands separator and decimal point, as on some thermal printers: 2.406.94."""
    whole, cents = f"{v:.2f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + "." + cents


def _space(v: Decimal) -> str:
    return _comma(v).replace(",", " ")


def amount_cases() -> list[Case]:
    cases: list[Case] = []

    def add(v, segs, expected, category):
        cases.append(Case("amount", v, segs, expected, category, label=" | ".join(s.text for s in segs)))

    for v in AMOUNTS:
        whole = v == v.to_integral_value()
        c, p = _comma(v), _plain(v)
        # ---- printed with cents: must be found
        add(v, row(("TOTAL", 0), (c, 300)), True, "cents: label and value in separate segments")
        add(v, row((f"{c} KSh", 0)), True, "cents: currency word after, spaced")
        add(v, row((f"KES {c}", 0)), True, "cents: currency word before, spaced")
        add(v, row((f"Ksh{c}", 0)), True, "cents: currency attached before")
        add(v, row((f"{c}KSh", 0)), True, "cents: currency attached after")
        add(v, row(("FOOD / DRINKS", 0), (f"{c}B", 400)), True, "cents: tax-code letter attached")
        add(v, row(("FOOD / DRINKS", 0), (f"{c} B", 400)), True, "cents: tax-code letter spaced")
        add(v, row((f"balance is Ksh{c}.", 0)), True, "cents: sentence, currency attached, full stop")
        add(v, row(("TOTAL", 0), (p, 300)), True, "cents: no thousands separator")
        add(v, row((f"1.00 x {c} KSh / PC(S)", 0)), True, "cents: inside a quantity line")
        add(v, row(("Grand Total", 0), (f"{c} KES", 400)), True, "cents: two-word label, currency after")
        if v >= 1000:
            add(v, row(("TOTAL", 0), (_dot(v), 300)), True, "cents: dot as thousands separator")
            add(v, row(("TOTAL", 0), (_space(v), 300)), True, "cents: space as thousands separator")
            head, tail = c[:-3], c[-3:]
            add(v, row(("TOTAL", 0), (head, 300), (tail, 300 + len(head) * 10 + 3)), True,
                "cents: value split into two close segments")
        # ---- printed without cents (whole amounts only): must be found
        if whole:
            b, bp = _bare(v), str(int(v))
            add(v, row((f"{b} Birr", 0)), True, "no cents: currency word after")
            add(v, row((f"ETB{bp}", 0)), True, "no cents: currency attached before")
            add(v, row((f"{bp}br", 0)), True, "no cents: currency attached after")
            add(v, row((f"{b}/=", 0)), True, "no cents: /= ending")
            add(v, row(("TOTAL", 0), (b, 300)), True, "no cents: right after a TOTAL label")
            add(v, row((f"Amount: {b}", 0)), True, "no cents: right after an Amount label")
            add(v, row(("CASH", 0), (f"{b} KSh", 300)), True, "no cents: currency after, CASH row")
            add(v, row((f"KES {bp}", 0)), True, "no cents: currency before, no separator")
        # ---- traps: must NOT be found
        bp = str(int(v))
        add(v, row((f"PIN P0{bp}7Q", 0)), False, "trap: digits inside a PIN or code")
        add(v, row((f"Tel 07{bp}19", 0)), False, "trap: digits inside a phone number")
        add(v, row((f"CU No 0090974{bp}201105", 0)), False, "trap: digits inside a long number")
        add(v, row(("RECEIPT NUMBER:", 0), (bp, 400)), False, "trap: receipt number")
        add(v, row((bp, 0)), False, "trap: lone whole number (counter)")
        add(v, row((f"Qty {bp}", 0)), False, "trap: quantity")
        add(v, row((f"COKE {bp}ML", 0)), False, "trap: product size")
        add(v, row(("TOTAL", 0), (_comma(v + Decimal("0.01")), 300)), False, "trap: one cent more")
        add(v, row(("TOTAL", 0), (_comma(v - Decimal("0.01")), 300)), False, "trap: one cent less")
        add(v, row(("TOTAL", 0), (_comma(Decimal("1" + str(int(v))) + (v - int(v))), 300)), False,
            "trap: extra leading digit")
        add(v, row(("TOTAL", 0), (_comma(v * 10), 300)), False, "trap: ten times the value")
        if whole:
            add(v, row(("TOTAL", 0), (_comma(v + Decimal("0.50")), 300)), False, "trap: same whole, different cents")
            add(v, row(("TOTAL", 0), (f"{int(v)},00", 300)), False, "trap: decimal comma (ambiguous)")
    # ---- joining traps and year
    add(Decimal("1100"), row(("Qty 1", 0), ("100.00", 400)), False, "trap: unrelated numbers far apart")
    add(Decimal("1100"), row(("1", 0), ("100.00", 14)), False, "trap: unrelated numbers very close")
    add(Decimal("2500"), row(("2", 0), ("500.00", 300)), False, "trap: unrelated numbers far apart")
    add(Decimal("12542"), row(("TOTAL", 0), ("12,542", 300), (".00", 363)), True, "cents: value split into two close segments")
    add(Decimal("2026"), row(("DATE:12/08/2026", 0)), False, "trap: year inside a date")
    add(Decimal("2026"), row(("12/08/2026", 0), ("TOTAL", 300)), False, "trap: year inside a date")
    add(Decimal("604"), row(("604", 0)), False, "trap: lone whole number (counter)")
    add(Decimal("575"), row(("Total", 0), ("575 CREDIT", 200)), False, "trap: total label, not money (points)")
    add(Decimal("7"), row(("TOTAL LINES:", 0), ("7", 300)), False, "trap: total label, not money (count)")
    add(Decimal("14"), row(("Total", 0), ("14 items", 200)), False, "trap: total label, not money (count)")
    add(Decimal("3"), row(("Total Qty", 0), ("3", 300)), False, "trap: total label, not money (count)")
    add(Decimal("1100"), row(("Qty 1 100.00", 0)), False, "trap: quantity and amount in one segment")
    add(Decimal("2500"), row(("2 500.00 KSh", 0)), False, "trap: quantity and amount in one segment")
    add(Decimal("1100"), row(("1 100.00", 0)), False, "trap: quantity and amount in one segment")
    add(Decimal("1200"), row(("TOTAL", 0), ("1,200.", 300), ("00", 363)), True,
        "cents: value split into two close segments")
    add(Decimal("430"), row(("CASH T2 -UC", 0), ("430 00 KSh", 300)), True, "faded: decimal point not read")
    add(Decimal("40.69"), row(("VAT 16% on 254.31 KSh", 0), ("40 69 KSh", 400)), True, "faded: decimal point not read")
    add(Decimal("75"), row(("1.00 x 75 00 KSh / PC(S)", 0)), True, "faded: decimal point not read")
    add(Decimal("5"), row(("Transaction cost, Ksh5.00.Amount you can", 0)), True, "fused: amount joined to next word")
    add(Decimal("2.50"), row(("2 50 KSh", 0)), False, "trap: quantity then price, looks like a faded decimal")
    add(Decimal("3.20"), row(("Qty 3 20 KSh", 0)), False, "trap: quantity then price, looks like a faded decimal")
    add(Decimal("12.30"), row(("Room 12 30 KSh", 0)), False, "trap: number then price, looks like a faded decimal")
    return cases


def _dmy(d: date, sep="/", zero=True, yy=False) -> str:
    day = f"{d.day:02d}" if zero else str(d.day)
    mon = f"{d.month:02d}" if zero else str(d.month)
    year = f"{d.year % 100:02d}" if yy else str(d.year)
    return f"{day}{sep}{mon}{sep}{year}"


def date_cases() -> list[Case]:
    cases: list[Case] = []
    months = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep",
              10: "Oct", 11: "Nov", 12: "Dec"}
    full = {5: "May", 7: "July", 8: "August", 12: "December"}

    def add(d, segs, expected, category):
        cases.append(Case("date", d, segs, expected, category, label=" | ".join(s.text for s in segs)))

    for d in DATES:
        mon, month = months[d.month], full[d.month]
        add(d, row((f"DATE:{_dmy(d)}", 0)), True, "date: label attached with colon")
        add(d, row(("Date:", 0), (_dmy(d), 200)), True, "date: label in its own segment")
        add(d, row((f"Date : {_dmy(d)} 22:08:34", 0)), True, "date: with time after")
        add(d, row((f"{_dmy(d, '-')} 23:55:12", 0)), True, "date: dashes")
        add(d, row((_dmy(d, '.'), 0)), True, "date: dots")
        add(d, row((f"on {_dmy(d, zero=False, yy=True)} at", 0)), True, "date: no zeros, two-digit year")
        add(d, row((f"{d.day:02d} {mon} {d.year}", 0)), True, "date: month abbreviation")
        add(d, row((f"Mon {d.day:02d} {month} {d.year}", 0)), True, "date: weekday and full month name")
        add(d, row((f"DATETIME : {d.day:02d} {mon} {d.year} 19:03:30", 0)), True, "date: label, month name, time")
        add(d, row((f"{d.year}-{d.month:02d}-{d.day:02d}", 0)), True, "date: year first")
        add(d, row((f"{d.day:02d}-{mon}-{d.year}", 0)), True, "date: day-Mon-year in one token")
        add(d, row((f"Date:{_dmy(d)}19:33:31", 0)), True, "date: time fused onto the year by OCR")
        add(d, row((f"Date:{_dmy(d, zero=False)}", 0)), True, "date: no leading zeros")
        # ---- traps
        if d.day <= 12 and d.day != d.month:
            swapped = date(d.year, d.day, d.month)
            add(d, row((f"DATE:{_dmy(swapped)}", 0)), False, "trap: month-first printing")
        add(d, row((f"DATE:{_dmy(d + timedelta(days=1))}", 0)), False, "trap: next day")
        add(d, row((f"DATE:{_dmy(d.replace(year=d.year - 1))}", 0)), False, "trap: previous year")
        other_month = d.replace(month=d.month % 12 + 1) if d.day <= 28 else d
        add(d, row((f"DATE:{_dmy(other_month)}", 0)), False, "trap: next month")
        add(d, row((f"DATE:{_dmy(d)}1", 0)), False, "trap: extra digit after the year")
        add(d, row((f"No:1{_dmy(d)}", 0)), False, "trap: digit before the day")
        add(d, row((f"CU {d.day:02d}{d.month:02d}{d.year}0012", 0)), False, "trap: digits inside a long number")
    return cases


def _swap(pin: str, i: int, c: str) -> str:
    return pin[:i] + c + pin[i + 1:]


def pin_cases() -> list[Case]:
    cases: list[Case] = []

    def add(pin, segs, expected, category):
        cases.append(Case("pin", pin, segs, expected, category, label=" | ".join(s.text for s in segs)))

    for pin in PINS:
        digits = [i for i, ch in enumerate(pin) if ch.isdigit()]
        zero = next(i for i in digits if pin[i] == "0")
        add(pin, row((f"PIN: {pin}", 0)), True, "pin: exact with label")
        add(pin, row(("Pin of buyer:", 0), (pin, 300)), True, "pin: label in its own segment")
        add(pin, row((f"BUYER PIN:{pin}", 0)), True, "pin: label attached with colon")
        add(pin, row((f"pin {pin.lower()}", 0)), True, "pin: lower case")
        add(pin, row((f"Pin{pin}", 0)), True, "pin: label fused on with no space")
        add(pin, row((f"TIN{pin}", 0)), True, "pin: label fused on with no space")
        add(pin, row((f"REF{pin}", 0)), False, "different: other code containing the PIN")
        add(pin, row((f"X{pin}", 0)), False, "different: other code containing the PIN")
        add(pin, row((f"PIN: {_swap(pin, zero, 'O')}", 0)), True, "misread: letter O for digit 0")
        add(pin, row((f"PIN: {_swap(pin, zero, '8')}", 0)), True, "misread: 8 for 0 (look-alike digits)")
        if pin[-1] == "Z":
            add(pin, row((f"PIN: {_swap(pin, len(pin) - 1, '2')}", 0)), True, "misread: digit 2 for final letter Z")
        if pin[-1] == "D":
            add(pin, row((f"PIN: {_swap(pin, len(pin) - 1, '0')}", 0)), True, "misread: 0 for final letter D")
        one = next((i for i in digits if pin[i] == "1"), None)
        if one is not None:
            add(pin, row((f"PIN: {_swap(pin, one, '7')}", 0)), True, "misread: 7 for 1 (look-alike digits)")
        five = next((i for i in digits if pin[i] == "5"), None)
        if five is not None:
            add(pin, row((f"PIN: {_swap(pin, five, 'S')}", 0)), True, "misread: letter S for digit 5")
        # ---- a different person's PIN: must NOT be found
        i = digits[3]
        other = str((int(pin[i]) + 3) % 10)
        add(pin, row((f"PIN: {_swap(pin, i, other)}", 0)), False, "different PIN: one digit, not a look-alike")
        add(pin, row((f"PIN: {_swap(_swap(pin, digits[2], '9'), digits[5], '4')}", 0)), False,
            "different PIN: two digits")
        add(pin, row((f"PIN: {pin}9", 0)), False, "different: longer code containing the PIN")
        add(pin, row((f"PIN: Q{pin}", 0)), False, "different: prefix letter")
        add(pin, row((f"PIN: {_swap(pin, zero, '8')}", 0)), False,
            "different PIN: one look-alike digit (cannot be told from a misread)")
    for tin in TINS:
        add(tin, row(("TIN No.", 0), (tin, 300)), True, "pin: 10-digit TIN")
        add(tin, row(("TIN No.", 0), (_swap(tin, 4, "S"), 300)), True, "misread: letter S for digit 5 (TIN)")
        add(tin, row(("TIN No.", 0), (_swap(tin, 2, "7"), 300)), False, "different PIN: one digit, not a look-alike")
    return cases


def all_cases() -> list[Case]:
    return amount_cases() + date_cases() + pin_cases()
