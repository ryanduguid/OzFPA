# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Price, volume and mix bridge. Every service, unit and price is invented.

Two services, 200 units before and 180 after. Prior revenue is 3,000 and
current revenue 2,520, a change of -480. At prior mix and prior prices, 180
units earn 2,700: volume is -300. At prior prices, the actual 120 and 60 units
earn 2,400: mix is -300, because units moved to the cheaper service. Current
prices on current units add 120: price is +120. -300 - 300 + 120 = -480.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from pyfpa.analysis.pvm import price_volume_mix


def line(name: str, q0: object, q1: object, p0: object, p1: object) -> dict[str, object]:
    return {"line": name, "prior_units": q0, "current_units": q1, "prior_price": p0, "current_price": p1}


def test_two_services_split_into_volume_mix_and_price():
    bridge = price_volume_mix([line("Cheap", "100", "120", "10", "11"), line("Dear", "100", "60", "20", "20")])
    assert (bridge.total, bridge.volume, bridge.mix, bridge.price) == (
        Decimal("-480.00"), Decimal("-300.00"), Decimal("-300.00"), Decimal("120.00"))
    cheap, dear = bridge.lines
    assert (cheap["volume"], cheap["mix"], cheap["price"]) == (Decimal("-100.00"), Decimal("300.00"), Decimal("120.00"))
    assert (dear["volume"], dear["mix"], dear["price"]) == (Decimal("-200.00"), Decimal("-600.00"), Decimal("0.00"))
    assert "Volume" in bridge.method and "Mix" in bridge.method and "Price" in bridge.method


def test_one_line_has_no_mix_and_matches_the_two_way_bridge():
    bridge = price_volume_mix([line("Maintenance", "200", "220", "100", "110")])
    assert (bridge.volume, bridge.mix, bridge.price, bridge.total) == (
        Decimal("2000.00"), Decimal("0.00"), Decimal("2200.00"), Decimal("4200.00"))


def test_an_unchanged_mix_gives_zero_mix():
    bridge = price_volume_mix([line("A", "10", "30", "7", "7"), line("B", "20", "60", "3", "3")])
    assert bridge.mix == 0
    assert bridge.volume == bridge.total == Decimal("260.00")


def test_the_three_effects_sum_exactly_to_the_change_in_every_line():
    rng = random.Random(20261124)
    for _ in range(300):
        lines = [line(f"L{i}", str(rng.randint(0, 997)) + ".37", str(rng.randint(0, 997)) + ".1",
                      f"{rng.randint(0, 9999)}.{rng.randint(0, 999999):06d}", f"{rng.randint(0, 9999)}.{rng.randint(0, 99):02d}")
                 for i in range(rng.randint(1, 6))]
        bridge = price_volume_mix(lines)
        assert bridge.volume + bridge.mix + bridge.price == bridge.total
        for row in bridge.lines:
            assert row["volume"] + row["mix"] + row["price"] == row["total"] == row["current"] - row["prior"]
        assert sum((row["total"] for row in bridge.lines), Decimal(0)) == bridge.total
        assert all(value == value.quantize(Decimal("0.01")) for value in (bridge.volume, bridge.mix, bridge.price))


def test_a_new_line_counts_as_mix_at_its_stated_prior_price():
    bridge = price_volume_mix([line("Old", "10", "10", "5", "5"), line("New", "0", "4", "8", "9")])
    new = bridge.lines[1]
    assert (new["prior"], new["volume"], new["mix"], new["price"]) == (Decimal("0.00"), Decimal("0.00"), Decimal("32.00"), Decimal("4.00"))
    assert bridge.total == Decimal("36.00") == bridge.volume + bridge.mix + bridge.price


def test_revenue_is_rounded_half_up_from_the_amount_as_written():
    # 1.005 is 100.49999... as a binary float; as written it rounds up to 1.01.
    bridge = price_volume_mix([line("A", "1", "1", "1.005", "1.005")])
    assert bridge.lines[0]["prior"] == bridge.lines[0]["current"] == Decimal("1.01")


def test_a_third_of_the_units_rounds_once_and_still_sums():
    # 3 prior units, 1 current: each line's prior 50 at current total units is 50/3, so 16.67.
    bridge = price_volume_mix([line("A", "1", "1", "50", "50"), line("B", "2", "0", "25", "25")])
    assert bridge.volume == Decimal("-66.66")
    assert bridge.volume + bridge.mix + bridge.price == bridge.total == Decimal("-50.00")


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [line("A", 1.5, "1", "1", "1")],
        [line("A", "1", "1", "NaN", "1")],
        [line("A", "1", "1", "Infinity", "1")],
        [line("A", "1", "-1", "1", "1")],
        [line("A", "1", -1, "1", "1")],
        [line("A", "1", "1", Decimal("NaN"), "1")],
        [line("A", "1", "1", "1e3", "1")],
        [line("A", "1", "1", "1", "one")],
        [line("A", True, "1", "1", "1")],
        [line("A", "1", "1", "1", "1"), line("A", "1", "1", "1", "1")],
        [line("", "1", "1", "1", "1")],
        [{"line": "A", "prior_units": "1", "current_units": "1", "prior_price": "1"}],
        [line("A", "0", "5", "1", "1")],
    ],
)
def test_bad_lines_are_refused(rows):
    with pytest.raises(ValueError):
        price_volume_mix(rows)


def test_integer_and_decimal_inputs_are_accepted():
    bridge = price_volume_mix([line("A", 2, Decimal("3"), Decimal("1.50"), 2)])
    assert bridge.total == Decimal("3.00")
