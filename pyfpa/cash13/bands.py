# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Seeded cash-floor bands: how low daily cash could go if stated flows are late.

Each run moves every flow a `DelayRange` names later by a whole number of
days, drawn uniformly from its range as `low + floor(random() * (high - low + 1))`,
one draw per flow per run in the order the events are given, from one
`random.Random(seed)`. Other flows keep their dates. The run then walks
end-of-day cash through the window; its floor is the lowest end-of-day balance.
A flow moved past `window_end` never arrives in the window.

P10, P50 and P90 are nearest-rank percentiles of the run floors: the
ceil(runs x p / 100)-th lowest, always a floor some run reached. Each band is
one simulated path, the first run whose floor is that percentile, reported as
its lowest end-of-day cash in each week, so the lowest week of a band is its
floor. The bands are not separate per-week percentiles.

Reproducible byte for byte: amounts are whole cents, rounded half up from
the amount as written, and only
`random.Random.random()` is used, whose sequence for an integer seed Python
documents as stable across versions.

Limits: the result is a scenario range under the stated ranges, not a forecast
and not a probability that cash will fall that low. The ranges are
assumptions, not fitted to payment history; each draw is independent, so
customers who pay late together are not modelled; amounts never change; and
nothing moves earlier.
"""

from __future__ import annotations

import math
import numbers
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

PERCENTILES = (10, 50, 90)
MAX_DELAY_DAYS = 366
MAX_RUNS = 100_000
LABEL = ("Scenario range under the stated delay ranges, not a forecast and not a "
         "probability that cash will fall this low.")


class DelayRange(BaseModel):
    """Every flow in `ids` moves later by `low_days` to `high_days`, each day equally likely.

    `basis` says where the range comes from: it is a stated assumption."""

    model_config = ConfigDict(extra="forbid", strict=True)

    ids: list[str] = Field(min_length=1)
    low_days: int = Field(ge=0, le=MAX_DELAY_DAYS)
    high_days: int = Field(ge=0, le=MAX_DELAY_DAYS)
    basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> DelayRange:
        if self.high_days < self.low_days:
            raise ValueError("high_days must be >= low_days")
        return self


@dataclass(frozen=True)
class CashFloorBands:
    """`summary` for a results file; `paths` has one row per week (week 1 first)."""

    summary: dict[str, Any]
    paths: pd.DataFrame


def _cents(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value) or value < 0:
        raise ValueError("receipts and payments must be finite, non-negative numbers")
    return _to_cents(value)


def _to_cents(value: object) -> int:
    """Whole cents from the amount as written (1.005 is 101), half a cent rounding up."""
    return int((Decimal(str(value)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _whole(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be a whole number from {low} to {high}")
    return value


def _week_lows(opening: int, base: list[int], moving: list[tuple[int, int]], shifts: list[int]) -> list[int]:
    net = list(base)
    for (day, amount), shift in zip(moving, shifts, strict=True):
        if day + shift < len(net):
            net[day + shift] += amount
    lows, balance = [], opening
    for start in range(0, len(net), 7):
        week = []
        for amount in net[start:start + 7]:
            balance += amount
            week.append(balance)
        lows.append(min(week))
    return lows


def cash_floor_bands(
    opening_cash: float,
    events: pd.DataFrame,
    window_start: date,
    window_end: date,
    delays: list[DelayRange],
    *,
    seed: int,
    runs: int = 1000,
    buffer: float = 0.0,
) -> CashFloorBands:
    """Floors of `runs` seeded runs over `events` (id, date, receipts, payments).

    Week n runs 7 days from `window_start` plus 7(n - 1) days; the last week
    stops at `window_end`. `buffer` only counts the runs whose floor is below it.
    Refuses a repeated or non-text id, a missing or pre-window date, a negative
    or non-finite amount, a range naming an unknown id or an id another range
    already names, and a seed, run count, opening cash or buffer out of range."""
    seed = _whole(seed, "seed", 0, 2**63 - 1)
    runs = _whole(runs, "runs", 1, MAX_RUNS)
    if not math.isfinite(opening_cash):
        raise ValueError("opening_cash must be finite")
    if not math.isfinite(buffer) or buffer < 0:
        raise ValueError("buffer must be finite and non-negative")
    if window_end < window_start:
        raise ValueError("window_end must not be before window_start")
    if not {"id", "date", "receipts", "payments"} <= set(events.columns):
        raise ValueError("events need columns id, date, receipts and payments")
    ids = events["id"].tolist()
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("event ids must be unique, non-empty text")
    rule_of: dict[str, DelayRange] = {}
    for rule in delays:
        for i in rule.ids:
            if i in rule_of:
                raise ValueError(f"{i} is in more than one delay range")
            rule_of[i] = rule
    if unknown := sorted(set(rule_of) - set(ids)):
        raise ValueError(f"delay ranges name unknown ids: {', '.join(unknown)}")

    days = (window_end - window_start).days + 1
    base, moving, ranges = [0] * days, [], []
    for i, when, received, paid in zip(ids, events["date"], events["receipts"], events["payments"], strict=True):
        if pd.isna(when):
            raise ValueError(f"every event needs a date; {i} has none")
        day = (pd.Timestamp(when).date() - window_start).days
        if day < 0:
            raise ValueError(f"{i} falls before window_start")
        amount = _cents(received) - _cents(paid)
        if i in rule_of:
            moving.append((day, amount))
            ranges.append((rule_of[i].low_days, rule_of[i].high_days - rule_of[i].low_days + 1))
        elif day < days:
            base[day] += amount

    rng = random.Random(seed)
    opening = _to_cents(opening_cash)
    lows = [_week_lows(opening, base, moving, [low + int(rng.random() * width) for low, width in ranges])
            for _ in range(runs)]
    floors = [min(week) for week in lows]
    ranked = sorted(floors)
    chosen = {f"p{p}": floors.index(ranked[math.ceil(runs * p / 100) - 1]) for p in PERCENTILES}
    starts = [window_start + timedelta(days=offset) for offset in range(0, days, 7)]
    paths = pd.DataFrame(
        {"week_start": [day.isoformat() for day in starts],
         "week_end": [min(day + timedelta(days=6), window_end).isoformat() for day in starts],
         **{p: [cents / 100 for cents in lows[run]] for p, run in chosen.items()}},
        index=pd.RangeIndex(1, len(starts) + 1, name="week"))
    summary: dict[str, Any] = {
        "label": LABEL, "seed": seed, "runs": runs,
        "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
        "delays": [rule.model_dump() for rule in delays],
        "floor": {p: floors[run] / 100 for p, run in chosen.items()},
        "representative_runs": chosen,
        "buffer": buffer,
        "runs_below_zero": sum(floor < 0 for floor in floors),
        "runs_below_buffer": sum(floor < _to_cents(buffer) for floor in floors),
    }
    return CashFloorBands(summary=summary, paths=paths)
