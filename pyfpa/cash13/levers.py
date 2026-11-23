# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Which debtors are late, and what collecting each one sooner does to the cash floor.

Both read the dated events `cash_floor_bands` takes (id, date, receipts,
payments), where each receipt sits on the date it is expected, and a
receivables table naming each receipt's debtor and due date. A receipt is late
by the days from its due date to its expected date, or 0 when it is expected
by then.

A lever collects every receipt of one debtor a stated number of days sooner,
but never before its due date or the window's first day, and leaves every
other flow where it is. Its gain is the change in the lowest end-of-day cash
in the window. A lever is arithmetic on the stated dates, not a prediction
that the debtor will pay sooner.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from pyfpa.cash13.bands import MAX_DELAY_DAYS, cash_floor_bands


def _floor(opening_cash: float, events: pd.DataFrame, window_start: date, window_end: date) -> float:
    """The lowest end-of-day cash with every flow on its stated date."""
    bands = cash_floor_bands(opening_cash, events, window_start, window_end, [], seed=0, runs=1)
    return float(bands.summary["floor"]["p50"])


def _receivables(events: pd.DataFrame, receivables: pd.DataFrame) -> pd.DataFrame:
    """One row per receivable with debtor, id, due, expected and amount, or a ValueError."""
    if not {"debtor", "id", "due_date"} <= set(receivables.columns):
        raise ValueError("receivables need columns debtor, id and due_date")
    if receivables["id"].duplicated().any():
        raise ValueError("each receivable id may appear once")
    if any(not isinstance(name, str) or not name.strip() for name in receivables["debtor"]):
        raise ValueError("every receivable needs a debtor name")
    if receivables["due_date"].isna().any():
        raise ValueError("every receivable needs a due_date")
    by_id = events.set_index("id")
    if unknown := sorted(set(receivables["id"]) - set(by_id.index)):
        raise ValueError(f"receivables name unknown event ids: {', '.join(map(str, unknown))}")
    rows = by_id.loc[receivables["id"]]
    if not ((rows["receipts"] > 0) & (rows["payments"] == 0)).all():
        raise ValueError("every receivable must be a receipt, and one is not a receipt")
    if rows["date"].isna().any():
        raise ValueError("every receivable needs an expected date")
    return pd.DataFrame({
        "debtor": receivables["debtor"].to_numpy(), "id": receivables["id"].to_numpy(),
        "due": pd.to_datetime(receivables["due_date"]).dt.normalize().to_numpy(),
        "expected": pd.to_datetime(rows["date"]).dt.normalize().to_numpy(),
        "amount": rows["receipts"].astype(float).to_numpy(),
    })


def debtor_lateness(events: pd.DataFrame, receivables: pd.DataFrame) -> pd.DataFrame:
    """One row per debtor, latest first: invoices, amount, late_amount (owed on
    receipts expected after their due date), max_days_late and weighted_days_late
    (days late weighted by amount, to 2 places). Ranked by amount times days late."""
    table = _receivables(events, receivables)
    table["days_late"] = (table["expected"] - table["due"]).dt.days.clip(lower=0)
    table["late_amount"] = table["amount"].where(table["days_late"] > 0, 0.0)
    table["amount_days"] = table["amount"] * table["days_late"]
    summary = table.groupby("debtor").agg(
        invoices=("id", "size"), amount=("amount", "sum"), late_amount=("late_amount", "sum"),
        max_days_late=("days_late", "max"), amount_days=("amount_days", "sum")).reset_index()
    summary["weighted_days_late"] = (summary["amount_days"] / summary["amount"]).round(2)
    summary = summary.sort_values(["amount_days", "debtor"], ascending=[False, True], kind="stable")
    return summary.drop(columns="amount_days").reset_index(drop=True)


def pull_forward_levers(
    opening_cash: float,
    events: pd.DataFrame,
    window_start: date,
    window_end: date,
    receivables: pd.DataFrame,
    days_sooner: list[int],
) -> pd.DataFrame:
    """For each of `days_sooner` and each debtor: floor_before, floor_after and gain.

    Rows follow `days_sooner` in order, then the largest gain first, ties in
    `debtor_lateness` order."""
    if not days_sooner or len(set(days_sooner)) != len(days_sooner) or any(
            isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_DELAY_DAYS for n in days_sooner):
        raise ValueError(f"days_sooner must be distinct whole numbers from 1 to {MAX_DELAY_DAYS}")
    table = _receivables(events, receivables)
    before = _floor(opening_cash, events, window_start, window_end)
    first = pd.Timestamp(window_start)
    rows = []
    for days in days_sooner:
        levers = []
        for debtor in debtor_lateness(events, receivables)["debtor"]:
            own = table[table["debtor"] == debtor]
            moved = (own["expected"] - pd.Timedelta(days=days)).clip(lower=own["due"]).clip(lower=first)
            dates = events["date"].copy()
            dates[events["id"].isin(own["id"])] = events["id"].map(dict(zip(own["id"], moved, strict=True)))
            after = _floor(opening_cash, events.assign(date=dates), window_start, window_end)
            levers.append({"debtor": debtor, "days_sooner": days, "floor_before": before,
                           "floor_after": after, "gain": round(after - before, 2)})
        rows += sorted(levers, key=lambda row: -row["gain"])
    return pd.DataFrame(rows, columns=["debtor", "days_sooner", "floor_before", "floor_after", "gain"])
