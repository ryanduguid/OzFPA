# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Debtor lateness and pull-forward levers. Every debtor, amount and date is invented.

Opening cash 50; a 120 bill on 3 October; Acme's 100 due 1 October arrives
10 October (9 days late); Bolt's 50 due 5 October arrives on time. Cash is
-70 on 3 October, so the floor is -70. Collected 7 or 14 days sooner, Acme
lands on 3 October and 1 October (never before its due date): both give a
floor of 30, a gain of 100. Bolt is on time, so neither lever moves it.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pyfpa.cash13.levers import debtor_lateness, pull_forward_levers

START, END = date(2026, 10, 1), date(2026, 10, 14)
EVENTS = pd.DataFrame({
    "id": ["INV-A", "INV-B", "BILL-1"],
    "date": pd.to_datetime(["2026-10-10", "2026-10-05", "2026-10-03"]),
    "receipts": [100.0, 50.0, 0.0], "payments": [0.0, 0.0, 120.0],
})
RECEIVABLES = pd.DataFrame({
    "debtor": ["Acme", "Bolt"], "id": ["INV-A", "INV-B"],
    "due_date": pd.to_datetime(["2026-10-01", "2026-10-05"]),
})


def test_lateness_ranks_debtors_by_amount_days_late():
    table = debtor_lateness(EVENTS, RECEIVABLES)
    assert table.to_dict("records") == [
        {"debtor": "Acme", "invoices": 1, "amount": 100.0, "late_amount": 100.0,
         "max_days_late": 9, "weighted_days_late": 9.0},
        {"debtor": "Bolt", "invoices": 1, "amount": 50.0, "late_amount": 0.0,
         "max_days_late": 0, "weighted_days_late": 0.0},
    ]


def test_lateness_weights_days_by_amount_within_a_debtor():
    events = pd.concat([EVENTS, pd.DataFrame({"id": ["INV-C"], "date": pd.to_datetime(["2026-10-03"]),
                                              "receipts": [300.0], "payments": [0.0]})], ignore_index=True)
    receivables = pd.concat([RECEIVABLES, pd.DataFrame({"debtor": ["Acme"], "id": ["INV-C"],
                                                        "due_date": pd.to_datetime(["2026-10-01"])})])
    acme = debtor_lateness(events, receivables).iloc[0]
    # (100 x 9 + 300 x 2) / 400 = 3.75, shown to 2 places.
    assert (acme["invoices"], acme["amount"], acme["max_days_late"], acme["weighted_days_late"]) == (2, 400.0, 9, 3.75)
    # Both Acme receipts move: INV-C to its 1 October due date, INV-A to 3 October.
    # Cash is 350 from 1 October and 330 after the bill, against 50 before.
    lever = pull_forward_levers(50.0, events, START, END, receivables, [7]).iloc[0]
    assert (lever["debtor"], lever["floor_before"], lever["floor_after"], lever["gain"]) == ("Acme", 50.0, 330.0, 280.0)


def test_each_lever_moves_one_debtor_sooner_but_never_before_its_due_date():
    table = pull_forward_levers(50.0, EVENTS, START, END, RECEIVABLES, [7, 14])
    assert table.to_dict("records") == [
        {"debtor": "Acme", "days_sooner": 7, "floor_before": -70.0, "floor_after": 30.0, "gain": 100.0},
        {"debtor": "Bolt", "days_sooner": 7, "floor_before": -70.0, "floor_after": -70.0, "gain": 0.0},
        {"debtor": "Acme", "days_sooner": 14, "floor_before": -70.0, "floor_after": 30.0, "gain": 100.0},
        {"debtor": "Bolt", "days_sooner": 14, "floor_before": -70.0, "floor_after": -70.0, "gain": 0.0},
    ]


def test_a_receipt_after_the_window_can_be_pulled_into_it():
    events = EVENTS.assign(date=pd.to_datetime(["2026-10-20", "2026-10-05", "2026-10-03"]))
    table = pull_forward_levers(50.0, events, START, END, RECEIVABLES, [19])
    # Outside the window it never arrives; 19 days sooner is its 1 October due date.
    assert table.iloc[0][["debtor", "floor_before", "floor_after", "gain"]].tolist() == ["Acme", -70.0, 30.0, 100.0]
    assert debtor_lateness(events, RECEIVABLES).iloc[0]["max_days_late"] == 19


@pytest.mark.parametrize(
    ("receivables", "message"),
    [
        (RECEIVABLES.drop(columns="due_date"), "receivables need columns"),
        (RECEIVABLES.assign(id=["INV-A", "INV-A"]), "once"),
        (RECEIVABLES.assign(id=["INV-A", "BILL-1"]), "not a receipt"),
        (RECEIVABLES.assign(id=["INV-A", "NOPE"]), "unknown"),
        (RECEIVABLES.assign(due_date=[pd.NaT, pd.Timestamp("2026-10-05")]), "due_date"),
        (RECEIVABLES.assign(debtor=["Acme", ""]), "debtor"),
        (RECEIVABLES.assign(debtor=["Acme", None]), "debtor"),
    ],
)
def test_bad_receivables_are_refused(receivables, message):
    with pytest.raises(ValueError, match=message):
        debtor_lateness(EVENTS, receivables)
    with pytest.raises(ValueError, match=message):
        pull_forward_levers(50.0, EVENTS, START, END, receivables, [7])


@pytest.mark.parametrize("days", [[], [0], [-1], [True], [1.5], [7, 7], [367]])
def test_bad_lever_days_are_refused(days):
    with pytest.raises(ValueError, match="days_sooner"):
        pull_forward_levers(50.0, EVENTS, START, END, RECEIVABLES, days)


def test_a_receivable_with_no_expected_date_is_refused():
    events = EVENTS.assign(date=[pd.NaT, pd.Timestamp("2026-10-05"), pd.Timestamp("2026-10-03")])
    with pytest.raises(ValueError, match="expected date"):
        debtor_lateness(events, RECEIVABLES)
