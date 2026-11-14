# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Open invoices placed by how each customer has paid before.

All customers, invoices and amounts are invented. Expected weeks are worked
out by hand beside each case: week n runs 7 days from 2 November 2026 plus
7(n - 1) days.
"""

import math
import random
from datetime import date, timedelta

import pandas as pd
import pytest

from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.receivables import (
    MIN_SAMPLE,
    predicted_receipt_flows,
    predicted_receipts,
)
from pyfpa.cash13.schemas import Cash13Config

START = date(2026, 11, 2)

# Days each paid invoice took: Quickpay's median is 14 (the 3rd smallest of 6),
# Slowpay's 50, and Newco has paid once, in 30 days.
PAID_DAYS = {"Quickpay": [10, 12, 14, 14, 16, 20], "Slowpay": [40, 45, 50, 55, 60, 70], "Newco": [30]}


def _history(paid_days=PAID_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    invoices, receipts = [], []
    for customer, all_days in paid_days.items():
        for number, days in enumerate(all_days):
            invoice = f"{customer}-paid-{number}"
            issued = date(2026, 3, 1) + timedelta(days=7 * number)
            invoices.append({"invoice": invoice, "customer": customer, "issued_on": issued.isoformat(),
                             "amount": 1000.0})
            # Paid in 2 parts: the invoice is paid when the second arrives.
            receipts.append({"invoice": invoice, "received_on": issued.isoformat(), "amount": 400.0})
            receipts.append({"invoice": invoice, "received_on": (issued + timedelta(days=days)).isoformat(),
                             "amount": 600.0})
    return pd.DataFrame(invoices), pd.DataFrame(receipts)


def _open(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["invoice", "customer", "issued_on", "amount"])


def test_each_customer_is_forecast_from_its_own_history():
    predicted = predicted_receipts(*_history(), _open(
        # 7 days old; all 6 of Quickpay's took 7 or more: 14 days, 9 November, week 2.
        ("Q-1", "Quickpay", "2026-10-26", 1000.0),
        # 7 days old; Slowpay's median is 50 days: 15 December, week 7.
        ("S-1", "Slowpay", "2026-10-26", 5000.0),
        # Newco has 1 paid invoice, under 6, so all customers' that took 14 days or more:
        # 14, 14, 16, 20, 30, 40, 45, 50, 55, 60, 70; the 6th of 11 is 40 days, 28 November, week 4.
        ("N-1", "Newco", "2026-10-19", 3000.0),
        # 46 days old: only 4 paid invoices took that long, from anyone. Not forecast.
        ("S-2", "Slowpay", "2026-09-17", 2000.0),
    ), START)
    assert predicted["basis"].tolist() == ["customer", "customer", "all customers", "none"]
    assert predicted["sample_size"].tolist() == [6, 6, 11, 4]
    assert predicted["days_to_pay"].tolist() == [14, 50, 40, pd.NA]
    assert predicted["expected_on"].tolist() == [date(2026, 11, 9), date(2026, 12, 15), date(2026, 11, 28), None]
    assert predicted["week"].tolist() == [2, 7, 4, pd.NA]
    assert predicted["percentile"].tolist() == [50, 50, 50, pd.NA]
    assert predicted["age_days"].tolist() == [7, 7, 14, 46]

    flows = predicted_receipt_flows(predicted)
    assert [(flow.start_week, flow.amount) for flow in flows] == [(2, 1000.0), (7, 5000.0), (4, 3000.0)]
    assert flows[0].name == "Q-1 Quickpay: 14 days, the median of 6 paid invoices from Quickpay that took 7 days or more"
    assert flows[2].name == ("N-1 Newco: 40 days, the median of 11 paid invoices from all customers "
                             "that took 14 days or more")


def test_the_portfolio_measure_alone_would_put_a_fast_payer_later():
    # Pooling every customer, Quickpay's invoice would take the 7th of 13 paid
    # invoices, 30 days: 25 November, week 4, not week 2.
    pooled = {"Everyone": [days for all_days in PAID_DAYS.values() for days in all_days]}
    open_invoice = _open(("Q-1", "Everyone", "2026-10-26", 1000.0))
    assert predicted_receipts(*_history(pooled), open_invoice, START)["week"].tolist() == [4]


def test_a_customer_with_fewer_than_six_comparable_payments_falls_back():
    five = {"Fiveco": [10, 10, 10, 10, 10], "Other": [60] * 6}
    predicted = predicted_receipts(*_history(five), _open(("F-1", "Fiveco", "2026-11-02", 10.0)), START)
    # Fiveco's 5 say 10 days; all 11 say the 6th smallest, 60 days.
    assert (predicted["basis"].item(), predicted["days_to_pay"].item()) == ("all customers", 60)
    six = {"Fiveco": [10] * 6, "Other": [60] * 6}
    predicted = predicted_receipts(*_history(six), _open(("F-1", "Fiveco", "2026-11-02", 10.0)), START)
    assert (predicted["basis"].item(), predicted["days_to_pay"].item()) == ("customer", 10)
    assert MIN_SAMPLE == 6


def test_an_invoice_expected_after_the_window_stays_owed_with_its_date():
    predicted = predicted_receipts(*_history(), _open(("S-1", "Slowpay", "2026-10-26", 5000.0)), START, weeks=4)
    assert predicted["expected_on"].tolist() == [date(2026, 12, 15)]
    assert predicted["week"].tolist() == [pd.NA]
    assert predicted_receipt_flows(predicted) == []


def test_extra_columns_are_kept_and_text_amounts_become_numbers():
    open_invoices = _open(("Q-1", "Quickpay", date(2026, 10, 26), "1000.50")).assign(due_on="2026-11-25")
    predicted = predicted_receipts(*_history(), open_invoices, START)
    assert predicted["due_on"].tolist() == ["2026-11-25"]
    assert predicted["amount"].tolist() == [1000.5]


def test_no_open_invoices_gives_no_rows():
    assert predicted_receipts(*_history(), _open(), START).empty


@pytest.mark.parametrize(
    ("history", "open_rows", "match"),
    [
        # Negative days: a receipt dated before its invoice.
        (lambda inv, rec: (inv, rec.assign(received_on=["2026-02-01", *rec["received_on"][1:]])), [],
         "before its invoice"),
        # Negative days: an open invoice issued after the window starts.
        (None, [("X-1", "Quickpay", "2026-11-03", 10.0)], "negative number of days old"),
        # Ambiguous matching.
        (None, [("Quickpay-paid-0", "Quickpay", "2026-10-26", 10.0)],
         r"both paid in the history and open: \['Quickpay-paid-0'\]"),
        (None, [("X-1", "Quickpay", "2026-10-26", 10.0), ("X-1", "Quickpay", "2026-10-27", 5.0)], "appear once"),
        (None, [("X-1", "quickpay ", "2026-10-26", 10.0)], r"differ only in case or spacing: \[\['Quickpay', 'quickpay '\]\]"),
        (lambda inv, rec: (inv, rec.assign(invoice=["nope", *rec["invoice"][1:]])), [], "not in invoices"),
        (lambda inv, rec: (inv.drop(columns="customer"), rec), [], "invoices needs a customer column"),
        (lambda inv, rec: (inv.assign(customer=[" ", *inv["customer"][1:]]), rec), [], "every invoices row needs a customer"),
        (None, [("X-1", None, "2026-10-26", 10.0)], "every open_invoices row needs a customer"),
        # Amounts and dates that cannot be placed.
        (None, [("X-1", "Quickpay", "2026-10-26", 0.0)], "finite number above 0"),
        (None, [("X-1", "Quickpay", "2026-10-26", float("inf"))], "finite number above 0"),
        (None, [("X-1", "Quickpay", None, 10.0)], "needs an issued_on date"),
        (None, [("X-1", "Quickpay", "26/10/2026", 10.0)], "ISO date"),
    ],
)
def test_records_that_cannot_be_placed_without_guessing_are_refused(history, open_rows, match):
    invoices, receipts = _history()
    if history is not None:
        invoices, receipts = history(invoices, receipts)
    with pytest.raises(ValueError, match=match):
        predicted_receipts(invoices, receipts, _open(*open_rows), START)


def test_open_invoices_without_the_columns_or_a_window_are_refused():
    with pytest.raises(ValueError, match=r"missing \['issued_on'\]"):
        predicted_receipts(*_history(), _open().drop(columns="issued_on"), START)
    with pytest.raises(ValueError, match="weeks must be at least 1"):
        predicted_receipts(*_history(), _open(), START, weeks=0)


def _random_case(rng: random.Random) -> tuple[dict[str, list[int]], pd.DataFrame]:
    customers = [f"Customer {n}" for n in range(rng.randint(1, 4))]
    paid = {customer: [rng.randint(0, 120) for _ in range(rng.randint(1, 9))] for customer in customers}
    rows = [(f"open-{n}", rng.choice(customers), (START - timedelta(days=rng.randint(0, 150))).isoformat(),
             round(rng.uniform(0.01, 50_000), 2)) for n in range(rng.randint(0, 12))]
    return paid, _open(*rows)


@pytest.mark.parametrize("seed", range(200))
def test_cash_in_never_exceeds_what_is_owed_and_the_ledger_reconciles(seed):
    rng = random.Random(seed)
    paid, open_invoices = _random_case(rng)
    weeks = rng.randint(1, 13)
    predicted = predicted_receipts(*_history(paid), open_invoices, START, weeks=weeks)
    # Every ledger row once, in order, with its amount.
    assert predicted["invoice"].tolist() == open_invoices["invoice"].tolist()
    assert math.fsum(predicted["amount"]) == pytest.approx(math.fsum(open_invoices["amount"]))
    flows = predicted_receipt_flows(predicted)
    forecast = cash13_forecast(Cash13Config(opening_cash=0.0, weeks=weeks, receipts=flows))
    placed = predicted[predicted["week"].notna()]
    still_owed = predicted[predicted["week"].isna()]
    assert forecast["receipts"].sum() == pytest.approx(math.fsum(placed["amount"]))
    assert forecast["receipts"].sum() <= math.fsum(open_invoices["amount"]) + 1e-6
    assert math.fsum(placed["amount"]) + math.fsum(still_owed["amount"]) == pytest.approx(
        math.fsum(open_invoices["amount"]))
    for customer, rows in predicted.groupby("customer"):
        cash_in = sum(flow.amount for flow in flows if flow.name.split(": ")[0].endswith(f" {customer}"))
        assert cash_in <= math.fsum(rows["amount"]) + 1e-6
    # A forecast date is never before the window, and comes from at least 6 paid invoices.
    for row in placed.itertuples():
        assert row.expected_on >= START
        assert row.sample_size >= MIN_SAMPLE
        assert row.days_to_pay >= row.age_days
