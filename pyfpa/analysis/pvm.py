# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Price, volume and mix bridge of revenue between two periods.

Each line has prior and current units and prices. With Q0 and Q1 the total
prior and current units, a line's revenue is taken at four stages, each
rounded half up to cents from the exact product:

1. prior: prior price times prior units;
2. at current volume: prior revenue times Q1 / Q0, so prior prices and prior
   mix on the current total units;
3. at current units: prior price times current units;
4. current: current price times current units.

Volume is stage 2 less stage 1, mix is stage 3 less stage 2 and price is
stage 4 less stage 3. The steps telescope, so for every line and in total the
three effects sum exactly to current less prior revenue. Mix assumes the
lines' units are comparable, such as jobs or hours. A line with no prior
units still needs a prior price: its current units at that price are mix, and
the difference from its current price is price.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import TypedDict

FIELDS = ("prior_units", "current_units", "prior_price", "current_price")
METHOD = (
    "Volume: change in total units at prior prices and prior mix. "
    "Mix: change in each line's share of units, at prior prices and current total units. "
    "Price: change in price at current units. Each line's revenue is rounded half up to cents "
    "at each stage, so the three effects sum exactly to the change in revenue."
)


class PvmLine(TypedDict):
    """One line's revenue at prior and current, and its three effects and total, in cents."""

    line: str
    prior: Decimal
    current: Decimal
    volume: Decimal
    mix: Decimal
    price: Decimal
    total: Decimal


@dataclass(frozen=True)
class PriceVolumeMix:
    """Effects in cents as Decimal; `lines` gives each line's prior, current and effects."""

    total: Decimal
    volume: Decimal
    mix: Decimal
    price: Decimal
    lines: list[PvmLine] = field(default_factory=list)
    method: str = METHOD


def _exact(value: object, name: str) -> Fraction:
    """A non-negative finite amount as written; a float or bool is refused, never rounded."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{name} must be a decimal string, integer or Decimal, not {type(value).__name__}")
    if isinstance(value, str) and not re.fullmatch(r"\d+(?:\.\d+)?", value):
        raise ValueError(f"{name} must be written as plain digits, such as 12.50: {value!r}")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise ValueError(f"{name} must be finite and non-negative: {value!r}")
    return Fraction(number)


def _cents(value: Fraction) -> Decimal:
    """Half a cent rounds up; the value is never negative here."""
    return Decimal(math.floor(value * 100 + Fraction(1, 2))).scaleb(-2)


def price_volume_mix(lines: Sequence[Mapping[str, object]]) -> PriceVolumeMix:
    """Split the change in revenue into volume, mix and price; see the module docstring."""
    parsed: list[tuple[str, Fraction, Fraction, Fraction, Fraction]] = []
    for row in lines:
        name = row.get("line")
        if not isinstance(name, str) or not name or any(name == seen[0] for seen in parsed):
            raise ValueError("Each line needs a unique non-empty name")
        if any(key not in row for key in FIELDS):
            raise ValueError(f"{name} needs {', '.join(FIELDS)}")
        q0, q1, p0, p1 = (_exact(row[key], f"{name} {key}") for key in FIELDS)
        parsed.append((name, q0, q1, p0, p1))
    if not parsed:
        raise ValueError("At least one line is required")
    prior_units = sum((line[1] for line in parsed), Fraction(0))
    current_units = sum((line[2] for line in parsed), Fraction(0))
    if prior_units == 0:
        raise ValueError("Prior units total zero, so volume and mix are undefined")
    out: list[PvmLine] = []
    for name, q0, q1, p0, p1 in parsed:
        prior = _cents(p0 * q0)
        at_volume = _cents(p0 * q0 * current_units / prior_units)
        at_units = _cents(p0 * q1)
        current = _cents(p1 * q1)
        out.append(PvmLine(line=name, prior=prior, current=current, volume=at_volume - prior,
                           mix=at_units - at_volume, price=current - at_units, total=current - prior))
    zero = Decimal("0.00")
    return PriceVolumeMix(sum((row["total"] for row in out), zero), sum((row["volume"] for row in out), zero),
                          sum((row["mix"] for row in out), zero), sum((row["price"] for row in out), zero), out)
