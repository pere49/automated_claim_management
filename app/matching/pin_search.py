"""Finding a PIN on one page (trial winner P6).

A token matches after trimming a "Label:" prefix, in any letter case, and
after removing a configured label word OCR fused onto it ("PinA012345678Z").
Where the PIN fits a configured format, a letter read in a digit-only
position (or the reverse) is mapped back (CORRECTED). One differing
character is accepted only when the pair is a configured OCR look-alike
(CORRECTED). Two or more differences never match.
"""

from __future__ import annotations

from app.matching.found import CORRECTED, EXACT, Found
from app.matching.rules import MatchingRules
from app.matching.tokens import Token


def normalise_pin(text: str) -> str:
    """The PIN as searched: spaces removed, letters capitalised."""
    return "".join(text.split()).upper()


def find_pin(pin: str, rows: list[list[Token]], cores: list[list[str]], rules: MatchingRules) -> list[Found]:
    """Every place the PIN is printed. `rows` are plain tokens (no joining);
    `cores` their label-trimmed, lower-case text (date_search.text_cores)."""
    pin_u = normalise_pin(pin)
    fmt = _format_of(pin_u, rules)
    found: list[Found] = []
    for r, (tokens, row) in enumerate(zip(rows, cores)):
        for tok, core in zip(tokens, row):
            if len(core) < len(pin_u):
                continue
            strength = _compare(core.upper(), pin_u, fmt, rules)
            if strength:
                found.append(Found(r, tok.segments, strength))
    return found


def _compare(core: str, pin_u: str, fmt: str | None, rules: MatchingRules) -> str | None:
    if len(core) > len(pin_u):
        head, tail = core[: -len(pin_u)], core[-len(pin_u):]
        if head.lower() in rules.pin_labels:
            core = tail
    if core == pin_u:
        return EXACT
    if len(core) != len(pin_u):
        return None
    norm = _positional(core, fmt, rules) if fmt else core
    if norm == pin_u:
        return CORRECTED
    diffs = [(raw, n, p) for raw, n, p in zip(core, norm, pin_u) if n != p]
    if len(diffs) != 1:
        return None
    raw, n, p = diffs[0]
    if frozenset((raw, p)) in rules.lookalike_pairs or frozenset((n, p)) in rules.lookalike_pairs:
        return CORRECTED
    return None


def _format_of(pin: str, rules: MatchingRules) -> str | None:
    shape = "".join("D" if c.isdigit() else "L" for c in pin)
    return shape if shape in rules.pin_formats else None


def _positional(token: str, fmt: str, rules: MatchingRules) -> str:
    out = []
    for c, kind in zip(token, fmt):
        if kind == "D" and not c.isdigit():
            c = rules.letter_to_digit.get(c, c)
        elif kind == "L" and c.isdigit():
            c = rules.digit_to_letter.get(c, c)
        out.append(c)
    return "".join(out)
