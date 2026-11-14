# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""When each open invoice is likely to be paid, from how its customer has paid before.

A paid invoice's days to pay run from its issue date to the receipt that
cleared it. An open invoice already `age` days old can only be paid by a
customer who takes at least that long, so its forecast uses the customer's
paid invoices that took `age` days or more, and lands the invoice on the
nearest-rank median of them: the ceil(n / 2)-th smallest, the lower of the 2
middle values for an even count, and always a day count one of those invoices
took. With fewer than `MIN_SAMPLE` such invoices it uses every customer's paid
invoices that took `age` days or more instead, and with fewer than that again
it forecasts nothing: the invoice stays owed and its row says why. Nothing is
random, so the same records give the same forecast.

Only paid invoices count. Open invoices older than `age` will take longer
still, so a customer whose slowest invoices are still open may be forecast to
pay sooner than it will; check the oldest open invoices before relying on a date.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from pyfpa.cash13.schemas import WeeklyFlow
from pyfpa.models.working_capital import _dates, _paid_history

# 6 is the smallest sample of independent payments whose lowest and highest
# values bracket the true median with at least 95% confidence whatever the
# distribution: the chance they miss it is at most 2 x 0.5^n, 3.1% at 6 and
# 6.3% at 5. It sets how much history a median needs, not how close a forecast
# date will be.
MIN_SAMPLE = 6
PERCENTILE = 50


def _any_bool(values: pd.Series) -> bool:
    """True when a value is True or False, which pandas would otherwise read as the number 1 or 0."""
    return any(isinstance(value, (bool, np.bool_)) for value in values)


def _require_customers(frame: pd.DataFrame, name: str) -> None:
    if "customer" not in frame.columns:
        raise ValueError(f"{name} needs a customer column")
    if not all(isinstance(customer, str) and customer.strip() for customer in frame["customer"]):
        raise ValueError(f"every {name} row needs a customer name")


def _require_distinct_customers(names: set[str]) -> None:
    """Refuse 2 spellings of one customer, which would split its history in 2."""
    by_key: dict[str, list[str]] = {}
    for name in sorted(names):
        by_key.setdefault(" ".join(name.split()).casefold(), []).append(name)
    clashes = [spellings for spellings in by_key.values() if len(spellings) > 1]
    if clashes:
        raise ValueError(f"customer names differ only in case or spacing: {clashes}; use one spelling")


def _validated_open(open_invoices: pd.DataFrame, paid: set[str], window_start: date) -> tuple[pd.Series, pd.Series]:
    """The open invoices' amounts and issue dates, once each row can be placed without guessing."""
    missing = {"invoice", "customer", "issued_on", "amount"} - set(open_invoices.columns)
    if missing:
        raise ValueError(f"open_invoices needs columns invoice, customer, issued_on and amount; missing {sorted(missing)}")
    if not open_invoices.index.is_unique:
        # Joining the forecast on a repeated label would repeat rows and overstate the ledger.
        raise ValueError("open_invoices needs a unique index, so each invoice keeps exactly one row")
    _require_customers(open_invoices, "open_invoices")
    amounts = pd.to_numeric(open_invoices["amount"], errors="coerce")
    if _any_bool(open_invoices["amount"]) or not (np.isfinite(amounts) & (amounts > 0)).all():
        raise ValueError("each open_invoices amount must be a finite number above 0: the amount still owed")
    if open_invoices["invoice"].isna().any() or not all(str(invoice).strip() for invoice in open_invoices["invoice"]):
        raise ValueError("every open_invoices row needs its invoice")
    # As text, so invoice 1 and invoice '1' count as one invoice, as they read the same in each row's name.
    keys = open_invoices["invoice"].map(str)
    if keys.duplicated().any():
        raise ValueError("each invoice must appear once in open_invoices")
    both = sorted(set(keys) & {str(invoice) for invoice in paid})
    if both:
        raise ValueError(f"invoices are both paid in the history and open: {both}")
    if open_invoices["issued_on"].isna().any():
        raise ValueError("every open_invoices row needs an issued_on date")
    issued = _dates(open_invoices["issued_on"], "issued_on").dt.date
    late = sorted(open_invoices.loc[issued.to_numpy() > window_start, "invoice"], key=str)
    if late:
        raise ValueError(f"open invoices issued after window_start would be a negative number of days old: {late}")
    return amounts.astype(float), issued


def predicted_receipts(
    invoices: pd.DataFrame,
    receipts: pd.DataFrame,
    open_invoices: pd.DataFrame,
    window_start: date,
    weeks: int = 13,
) -> pd.DataFrame:
    """`open_invoices` with the date and week each is forecast to be paid, and why.

    `invoices` and `receipts` are the paid history `collection_profile_from_history`
    takes, checked the same way, with a customer column on `invoices`.
    `open_invoices` has invoice, customer, issued_on and amount (the amount still
    owed, taken as a number); other columns are kept. Adds age_days (days old
    at `window_start`), basis ("customer", "all customers" or "none"),
    sample_size (the paid invoices the median came from, or the most there were
    when basis is "none"), percentile, days_to_pay, expected_on and week (1 to
    `weeks`; missing when expected after the window or when basis is "none").
    Every open invoice keeps one row, so the amounts still add up to the
    receivables ledger. Pass the result to `predicted_receipt_flows` for the
    forecast's receipts.

    Refuses a receipt before its invoice, an open invoice issued after
    `window_start`, an invoice both paid and open, a repeated open invoice or
    index label, an open invoice with no invoice or customer, an amount of True
    or False, and customer names that differ only in case or spacing.
    """
    if isinstance(weeks, bool) or not isinstance(weeks, int) or weeks < 1:
        raise ValueError("weeks must be a whole number of at least 1")
    _require_customers(invoices, "invoices")
    paid = _paid_history(invoices, receipts)
    customer_of = dict(zip(invoices["invoice"], invoices["customer"], strict=True))
    cleared = paid.groupby("invoice").agg(issued=("issued", "first"), cleared=("received", "max"))
    history = pd.DataFrame({"customer": [customer_of[invoice] for invoice in cleared.index],
                            "days": (cleared["cleared"] - cleared["issued"]).dt.days.to_numpy()})
    amounts, issued = _validated_open(open_invoices, set(customer_of), window_start)
    _require_distinct_customers(set(history["customer"]) | set(open_invoices["customer"]))

    rows: list[dict[str, object]] = []
    for customer, issued_on in zip(open_invoices["customer"], issued, strict=True):
        age = (window_start - issued_on).days
        comparable = history[history["days"] >= age]
        own = sorted(comparable.loc[comparable["customer"] == customer, "days"])
        pooled = sorted(comparable["days"])
        basis, sample = ("customer", own) if len(own) >= MIN_SAMPLE else ("all customers", pooled)
        if len(sample) < MIN_SAMPLE:
            rows.append({"age_days": age, "basis": "none", "sample_size": len(sample), "percentile": pd.NA,
                         "days_to_pay": pd.NA, "expected_on": None, "week": pd.NA})
            continue
        days = int(sample[math.ceil(len(sample) * PERCENTILE / 100) - 1])
        expected = issued_on + timedelta(days=days)
        week = (expected - window_start).days // 7 + 1
        rows.append({"age_days": age, "basis": basis, "sample_size": len(sample), "percentile": PERCENTILE,
                     "days_to_pay": days, "expected_on": expected, "week": week if week <= weeks else pd.NA})
    columns = ["age_days", "basis", "sample_size", "percentile", "days_to_pay", "expected_on", "week"]
    forecast = pd.DataFrame(rows, index=open_invoices.index, columns=columns)
    integers = {"percentile": "Int64", "days_to_pay": "Int64", "week": "Int64"}
    return open_invoices.assign(amount=amounts).join(forecast.astype(integers))


def predicted_receipt_flows(predicted: pd.DataFrame) -> list[WeeklyFlow]:
    """One receipt per invoice `predicted_receipts` places in the window, named with its basis."""
    flows: list[WeeklyFlow] = []
    for row in predicted[predicted["week"].notna()].itertuples(index=False):
        source = row.customer if row.basis == "customer" else "all customers"
        flows.append(WeeklyFlow(
            name=(f"{row.invoice} {row.customer}: {row.days_to_pay} days, the median of "
                  f"{row.sample_size} paid invoices from {source} that took {row.age_days} days or more"),
            amount=float(row.amount), start_week=int(row.week)))
    return flows
