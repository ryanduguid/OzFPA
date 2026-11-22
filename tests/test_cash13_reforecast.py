# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""The 13-week forecast rolled forward past 4 closed weeks.

All customers, invoices and amounts are invented. The forecast is made as at
Monday 2 November 2026; after 4 closed weeks the new window starts on Monday
30 November 2026.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from pyfpa import (
    Cash13Config,
    WeeklyFlow,
    cash13_forecast,
    predicted_receipt_flows,
    predicted_receipts,
)
from pyfpa.cash13.reforecast import reforecast_from_actuals

START, ROLLED = date(2026, 11, 2), date(2026, 11, 30)
# Days each paid invoice took: Quickpay's median is 14, Slowpay's 50, and Newco has paid once, in 30 days.
PAID_DAYS = {"Quickpay": [10, 12, 14, 14, 16, 20], "Slowpay": [40, 45, 50, 55, 60, 70], "Newco": [30]}
OPEN = [("Q-1", "Quickpay", "2026-10-26", 1000.0), ("S-1", "Slowpay", "2026-10-26", 5000.0),
        ("Q-2", "Quickpay", "2026-10-12", 2000.0)]
SCHEDULED = {
    "receipts": [WeeklyFlow(name="Grant", amount=1500.0, start_week=3),
                 WeeklyFlow(name="Interest", amount=200.0, start_week=9)],
    "disbursements": [
        WeeklyFlow(name="Wages", amount=4000.0, start_week=1, recurrence="biweekly"),
        WeeklyFlow(name="Super", amount=500.0, start_week=2, recurrence="biweekly"),
        # Anchored before the window: 31 October, then 30 November, 31 December, 31 January and 28 February.
        WeeklyFlow(name="Rent", amount=3000.0, start_week=1, recurrence="monthly", anchor_date=date(2026, 10, 31)),
        WeeklyFlow(name="Fitout", amount=800.0, start_week=1, recurrence="weekly", end_week=3),
        WeeklyFlow(name="Loan", amount=600.0, start_week=2, recurrence="weekly", end_week=6),
        WeeklyFlow(name="Costs", amount=1000.0, start_week=1, recurrence="weekly"),
    ],
}


def _history(extra_paid=()) -> tuple[pd.DataFrame, pd.DataFrame]:
    invoices, receipts = [], []
    for customer, all_days in PAID_DAYS.items():
        for number, days in enumerate(all_days):
            issued = date(2026, 3, 1) + timedelta(days=7 * number)
            invoices.append((f"{customer}-paid-{number}", customer, issued.isoformat(), 1000.0))
            receipts.append((f"{customer}-paid-{number}", (issued + timedelta(days=days)).isoformat(), 1000.0))
    for invoice, customer, issued_on, amount, received_on in extra_paid:
        invoices.append((invoice, customer, issued_on, amount))
        receipts.append((invoice, received_on, amount))
    return (pd.DataFrame(invoices, columns=["invoice", "customer", "issued_on", "amount"]),
            pd.DataFrame(receipts, columns=["invoice", "received_on", "amount"]))


def _open(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["invoice", "customer", "issued_on", "amount"])


def _actuals(flows) -> dict[str, dict[str, float]]:
    balance, weeks = 20000.0, {}
    for week, (receipts, disbursements) in enumerate(flows):
        balance += receipts - disbursements
        weeks[(START + timedelta(weeks=week)).isoformat()] = {
            "receipts": receipts, "disbursements": disbursements, "ending_cash": balance}
    return weeks


PREDICTED = predicted_receipts(*_history(), _open(OPEN), START)
CONFIG = Cash13Config(opening_cash=20000.0, window_start=START,
                      receipts=[*SCHEDULED["receipts"], *predicted_receipt_flows(PREDICTED)],
                      disbursements=SCHEDULED["disbursements"])
# Q-1 was paid in full on 9 November; Newco's N-2 was issued on 23 November.
PAID_SINCE = [("Q-1", "Quickpay", "2026-10-26", 1000.0, "2026-11-09")]
STILL_OPEN = [OPEN[1], OPEN[2], ("N-2", "Newco", "2026-11-23", 3000.0)]
# Week 1 has no receipts, which the weekly score would refuse as a zero actual; nothing is scored here.
CLOSED = _actuals([(0.0, 2800.0), (1000.0, 6100.0), (1500.0, 5400.0), (0.0, 1600.0)])


def _rolled():
    return reforecast_from_actuals(CONFIG, CLOSED, PREDICTED, *_history(PAID_SINCE), _open(STILL_OPEN))


def test_the_rolled_forecast_opens_at_the_last_actual_balance():
    # Q-1 in week 2, Q-2 in week 5 and S-1 in week 7, as the receivables tests work them out.
    assert PREDICTED["week"].tolist() == [2, 7, 5]
    config = _rolled().config
    assert config.window_start == ROLLED
    assert config.opening_cash == 20000.0 + 2500.0 - 15900.0
    assert config.weeks == 13


def test_an_invoice_paid_in_the_closed_weeks_leaves_the_forecast_and_the_rest_are_placed_again():
    result = _rolled()
    assert not [flow for flow in result.config.receipts if flow.name.startswith("Q-1 ")]
    # S-1 is 35 days old: Slowpay's 6 paid invoices all took that long, so 50 days, 15 December, week 3.
    # Q-2 is 49 days old: only 4 paid invoices took that long, so it is no longer forecast.
    # N-2 is 7 days old and Newco has paid once: every customer's 14 that took 7 days or more, Q-1's 14 days
    # among them, give 20 days, 13 December, week 2.
    assert result.receivables["week"].tolist() == [3, pd.NA, 2]
    assert result.receivables["basis"].tolist() == ["customer", "none", "all customers"]
    assert predicted_receipt_flows(result.receivables) == result.config.receipts[-2:]
    changes = result.changes.set_index("invoice")
    assert changes["change"].to_dict() == {"Q-1": "paid", "S-1": "unchanged", "Q-2": "changed", "N-2": "new"}
    assert changes.loc["Q-2", ["expected_before", "expected_after"]].tolist() == [date(2026, 12, 1), None]
    assert changes.loc["Q-1", "amount_before"] == 1000.0
    assert pd.isna(changes.loc["Q-1", "amount_after"])
    assert pd.isna(changes.loc["N-2", "amount_before"])
    assert changes.loc["N-2", "expected_after"] == date(2026, 12, 13)


@pytest.mark.parametrize("side", ["receipts", "disbursements"])
def test_scheduled_flows_keep_their_dates(side):
    rolled = _rolled().config
    flows = [flow for flow in getattr(rolled, side) if flow.name[:3] not in {"S-1", "N-2"}]
    # The original flows over 17 weeks, from week 5, are the rolled flows over 13.
    original = cash13_forecast(Cash13Config.model_validate(
        {"opening_cash": 0.0, "window_start": START, "weeks": 17, side: SCHEDULED[side]}))
    again = cash13_forecast(Cash13Config.model_validate({"opening_cash": 0.0, "window_start": ROLLED, side: flows}))
    assert again[side].tolist() == original[side].iloc[4:].tolist()
    # Flows wholly in the closed weeks leave, rather than stay with no week.
    assert {flow.name for flow in flows} == {flow.name for flow in SCHEDULED[side]} - {"Grant", "Fitout"}


def test_flows_that_do_not_come_from_the_predicted_invoices_are_refused():
    moved = PREDICTED.assign(week=PREDICTED["week"].replace({7: 8}))
    with pytest.raises(ValueError, match="the forecast has no receipt 'S-1 Slowpay.*in week 8"):
        reforecast_from_actuals(CONFIG, CLOSED, moved, *_history(PAID_SINCE), _open(STILL_OPEN))


def test_a_scheduled_receipt_equal_to_an_invoice_receipt_stays():
    # A second receipt equal to S-1's: only the one predicted_receipts made is replaced.
    s1 = predicted_receipt_flows(PREDICTED)[1]
    config = CONFIG.model_copy(update={"receipts": [*CONFIG.receipts, s1]})
    rolled = reforecast_from_actuals(config, CLOSED, PREDICTED, *_history(PAID_SINCE), _open(STILL_OPEN)).config
    assert [(flow.name[:3], flow.start_week) for flow in rolled.receipts if flow.name.startswith("S-1 ")] == [
        ("S-1", 3), ("S-1", 3)]


def test_an_invoice_that_is_neither_open_nor_paid_is_refused():
    with pytest.raises(ValueError, match=r"invoices \['Q-1'\] were forecast but are neither open nor paid"):
        reforecast_from_actuals(CONFIG, CLOSED, PREDICTED, *_history(), _open(STILL_OPEN))


def test_actuals_are_refused_as_the_weekly_score_refuses_them():
    gap = {label: week for label, week in CLOSED.items() if label != "2026-11-09"}
    with pytest.raises(ValueError, match=r"actuals are missing for weeks \[2\], before week 4"):
        reforecast_from_actuals(CONFIG, gap, PREDICTED, *_history(PAID_SINCE), _open(STILL_OPEN))
