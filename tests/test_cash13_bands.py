# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Seeded cash-floor bands over dated flows. Every amount and date is invented."""

from __future__ import annotations

import math
import random
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from pyfpa.cash13.bands import DelayRange, cash_floor_bands

START, END = date(2026, 10, 1), date(2026, 10, 14)


def _events(*rows: tuple[str, str, float, float]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["id", "date", "receipts", "payments"]).assign(
        date=lambda frame: pd.to_datetime(frame["date"]))


EVENTS = _events(("INV-1", "2026-10-01", 100.0, 0.0), ("BILL-1", "2026-10-04", 0.0, 150.0))
LATE = [DelayRange(ids=["INV-1"], low_days=0, high_days=9, basis="Invented range for the test")]


def test_each_run_draws_its_delay_from_the_stated_seed_and_range():
    bands = cash_floor_bands(100.0, EVENTS, START, END, LATE, seed=7, runs=200)
    # The documented draw: low + floor(random() * (high - low + 1)), one per flow per run.
    rng = random.Random(7)
    shifts = [int(rng.random() * 10) for _ in range(200)]
    # Paid by day 3, cash dips to 50 on day 3; any later, it dips to -50 until the receipt.
    floors = sorted(50.0 if shift <= 3 else -50.0 for shift in shifts)
    summary = bands.summary
    assert summary["runs_below_zero"] == sum(shift > 3 for shift in shifts)
    assert summary["floor"] == {f"p{p}": floors[math.ceil(200 * p / 100) - 1] for p in (10, 50, 90)}
    assert summary["seed"] == 7 and summary["runs"] == 200
    assert summary["delays"] == [{"ids": ["INV-1"], "low_days": 0, "high_days": 9,
                                  "basis": "Invented range for the test"}]
    assert "not a forecast" in summary["label"]


def test_each_band_is_one_simulated_path_whose_floor_is_that_percentile():
    bands = cash_floor_bands(100.0, EVENTS, START, END, LATE, seed=11, runs=500)
    assert list(bands.paths.columns) == ["week_start", "week_end", "p10", "p50", "p90"]
    assert bands.paths.index.tolist() == [1, 2]
    assert bands.paths["week_start"].tolist() == ["2026-10-01", "2026-10-08"]
    assert bands.paths["week_end"].tolist() == ["2026-10-07", "2026-10-14"]
    for p in ("p10", "p50", "p90"):
        assert bands.paths[p].min() == bands.summary["floor"][p]
        assert 0 <= bands.summary["representative_runs"][p] < 500


def test_the_same_seed_gives_the_same_bytes_and_another_seed_can_differ():
    def csv(seed: int) -> str:
        return cash_floor_bands(100.0, EVENTS, START, END, LATE, seed=seed, runs=300).paths.to_csv(float_format="%.2f")

    assert csv(3) == csv(3)
    assert {csv(seed) for seed in range(10)} != {csv(3)}


def test_flows_with_no_range_stay_on_their_dates_and_late_ones_can_leave_the_window():
    events = _events(("INV-1", "2026-10-13", 500.0, 0.0), ("BILL-1", "2026-10-02", 0.0, 120.5),
                     ("BILL-2", "2026-10-15", 0.0, 9999.0))
    fixed = cash_floor_bands(100.0, events, START, END, [], seed=1, runs=5)
    assert fixed.summary["floor"] == {"p10": -20.5, "p50": -20.5, "p90": -20.5}
    assert fixed.summary["runs_below_buffer"] == 5
    # Moved 2 or more days, the receipt lands after the window and never arrives in it.
    moved = cash_floor_bands(100.0, events, START, END,
                             [DelayRange(ids=["INV-1"], low_days=2, high_days=2, basis="b")], seed=1, runs=5)
    assert moved.paths["p50"].tolist() == [-20.5, -20.5]


def test_a_buffer_counts_runs_whose_floor_is_below_it():
    bands = cash_floor_bands(100.0, EVENTS, START, END, LATE, seed=7, runs=200, buffer=60.0)
    assert bands.summary["runs_below_buffer"] == 200
    assert bands.summary["buffer"] == 60.0


def test_numpy_amounts_are_accepted_as_cents():
    events = EVENTS.astype({"receipts": np.int64, "payments": np.int64})
    assert cash_floor_bands(0.0, events, START, END, [], seed=0, runs=1).summary["floor"]["p50"] == -50.0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda e: e.drop(columns="payments"), "events need columns"),
        (lambda e: e.assign(id=["A", "A"]), "unique"),
        (lambda e: e.assign(id=["A", 2]), "unique"),
        (lambda e: e.assign(receipts=[-1.0, 0.0]), "finite, non-negative"),
        (lambda e: e.assign(receipts=[float("nan"), 0.0]), "finite, non-negative"),
        (lambda e: e.assign(receipts=[True, 0.0]), "finite, non-negative"),
        (lambda e: e.assign(payments=["1", "2"]), "finite, non-negative"),
        (lambda e: e.assign(date=pd.to_datetime(["2026-09-30", "2026-10-04"])), "before window_start"),
        (lambda e: e.assign(date=[pd.NaT, pd.Timestamp("2026-10-04")]), "date"),
    ],
)
def test_bad_events_are_refused(change, message):
    with pytest.raises(ValueError, match=message):
        cash_floor_bands(0.0, change(EVENTS), START, END, [], seed=0, runs=1)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"runs": 0}, "runs"), ({"runs": True}, "runs"), ({"runs": 100_001}, "runs"),
        ({"seed": -1}, "seed"), ({"seed": 1.5}, "seed"), ({"seed": False}, "seed"),
        ({"opening_cash": float("inf")}, "opening_cash"), ({"buffer": -1.0}, "buffer"),
        ({"window_end": date(2026, 9, 30)}, "window_end"),
        ({"delays": [DelayRange(ids=["NOPE"], low_days=0, high_days=1, basis="b")]}, "unknown"),
        ({"delays": [DelayRange(ids=["INV-1"], low_days=0, high_days=1, basis="b")] * 2}, "more than one"),
    ],
)
def test_bad_settings_are_refused(kwargs, message):
    settings = {"opening_cash": 0.0, "window_end": END, "delays": [], "seed": 0, "runs": 1, "buffer": 0.0} | kwargs
    with pytest.raises(ValueError, match=message):
        cash_floor_bands(settings.pop("opening_cash"), EVENTS, START, settings.pop("window_end"),
                         settings.pop("delays"), **settings)


@pytest.mark.parametrize(
    "fields",
    [
        {"ids": [], "low_days": 0, "high_days": 1, "basis": "b"},
        {"ids": ["A"], "low_days": 2, "high_days": 1, "basis": "b"},
        {"ids": ["A"], "low_days": -1, "high_days": 1, "basis": "b"},
        {"ids": ["A"], "low_days": 0, "high_days": 367, "basis": "b"},
        {"ids": ["A"], "low_days": 0, "high_days": 1, "basis": ""},
        {"ids": ["A"], "low_days": 0.5, "high_days": 1, "basis": "b"},
        {"ids": ["A"], "low_days": 0, "high_days": 1, "basis": "b", "shape": "normal"},
    ],
)
def test_a_bad_delay_range_is_refused(fields):
    with pytest.raises(ValidationError):
        DelayRange(**fields)


def test_amounts_round_to_cents_as_written_not_as_binary_floats():
    # 1.005 is 1.00499999... as a binary float; as written it rounds half up to 101 cents.
    events = _events(("INV-1", "2026-10-01", 1.005, 0.0), ("BILL-1", "2026-10-02", 0.0, 2.015))
    bands = cash_floor_bands(1.005, events, START, END, [], seed=0, runs=1, buffer=0.015)
    assert bands.summary["floor"]["p50"] == 0.0
    assert bands.summary["runs_below_buffer"] == 1
