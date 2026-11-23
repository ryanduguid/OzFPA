# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Tie every figure in generated prose to its source, and report any it cannot tie.

A tie names one statement: a regular expression with one group per figure and
each figure's source value in group order. The pattern must match exactly
once. A source given as text must match the figure exactly; any other source
is a number. A figure written with `$` is compared in cents, rounded half up
from the source as written, and is negative when bracketed or signed. Every
other figure must equal the source as a number.

After the ties, every number in the text that no tie's match covers is
reported as untied, so a new sentence with a figure fails until it has a tie.
A tie with no groups vouches for a fixed phrase that holds digits, such as a
label.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_NUMBER = re.compile(r"\d(?:[\d,.]*\d)?")


@dataclass(frozen=True)
class FigureTie:
    """A statement's pattern and the source of each figure it carries."""

    name: str
    pattern: str
    sources: tuple[object, ...]


def _cents(value: object) -> int:
    """Whole cents from the amount as written (1.005 is 101), half a cent rounding up."""
    return int((Decimal(str(value)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _same(found: str, source: object) -> bool:
    if isinstance(source, str):
        return found == source
    try:
        if "$" in found:
            cents = _cents(re.sub(r"[^\d.]", "", found))
            negative = found.startswith("(") or "-" in found
            return (-cents if negative else cents) == _cents(source)
        return Decimal(found.replace(",", "")) == Decimal(str(source))
    except InvalidOperation:
        return False


def figure_problems(text: str, ties: Sequence[FigureTie]) -> list[str]:
    """Each tie that is missing, repeated or different from its source, then each untied number."""
    problems: list[str] = []
    covered: list[tuple[int, int]] = []
    for tie in ties:
        matches = list(re.finditer(tie.pattern, text, re.MULTILINE))
        if len(matches) != 1:
            problems.append(f"{tie.name}: pattern matched {len(matches)} times")
            continue
        match = matches[0]
        covered.append(match.span())
        found = match.groups()
        if len(found) != len(tie.sources):
            problems.append(f"{tie.name}: {len(found)} figures, {len(tie.sources)} sources")
            continue
        problems += [f"{tie.name}: text {value}, source {source}"
                     for value, source in zip(found, tie.sources, strict=True)
                     if value is None or not _same(value, source)]
    for number in _NUMBER.finditer(text):
        if not any(start <= number.start() and number.end() <= end for start, end in covered):
            problems.append(f"untied figure {number.group()!r} on line {text.count(chr(10), 0, number.start()) + 1}")
    return problems
