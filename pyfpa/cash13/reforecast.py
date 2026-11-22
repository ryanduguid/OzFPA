# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""The 13-week forecast rolled forward past the weeks that have closed.

An opt-in step a person runs after `weekly_actuals_score`; nothing runs it for
them. The new window starts the week after the last closed week, from that
week's actual closing balance, and keeps its length. Each scheduled flow keeps
its dates, so a flow in a closed week leaves (the actuals hold it) and one with
no end_week runs on into the weeks the window gains. Open invoices are placed
again by `predicted_receipts` from the paid history as it now stands: an
invoice paid in the closed weeks leaves the forecast, and the others are placed
from the latest payments.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from pyfpa.backtest.weekly import _closed_weeks
from pyfpa.cash13.receivables import predicted_receipt_flows, predicted_receipts
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow

CHANGE_COLUMNS = ["invoice", "customer", "amount_before", "amount_after", "expected_before", "expected_after",
                  "change"]


@dataclass(frozen=True)
class Reforecast:
    config: Cash13Config       # the rolled forecast, for cash13_forecast
    receivables: pd.DataFrame  # predicted_receipts as at the new window_start
    changes: pd.DataFrame      # each invoice either forecast holds: paid, new, changed or unchanged


def _rolled(flows: Sequence[WeeklyFlow], closed: int) -> list[WeeklyFlow]:
    """The flows counted from `closed` weeks later, less those with no week left."""
    kept = []
    for flow in flows:
        start = flow.start_week - closed
        end = None if flow.end_week is None else flow.end_week - closed
        if start < 1:
            if flow.recurrence == "once":
                continue
            # A fortnightly flow keeps its fortnight: its first date after the closed weeks.
            start = 1 + (1 - start) % 2 if flow.recurrence == "biweekly" else 1
        if end is None or end >= start:
            kept.append(flow.model_copy(update={"start_week": start, "end_week": end}))
    return kept


def _changes(before: pd.DataFrame, after: pd.DataFrame, paid: set[str]) -> pd.DataFrame:
    """One row per invoice in either placement, saying how it moved."""
    old = {str(row.invoice): row for row in before.itertuples(index=False)}
    new = {str(row.invoice): row for row in after.itertuples(index=False)}
    gone = sorted(set(old) - set(new) - paid)
    if gone:
        raise ValueError(f"invoices {gone} were forecast but are neither open nor paid in full in the history; "
                         "pass each in open_invoices or in invoices and receipts")
    rows = []
    for key in [*old, *(key for key in new if key not in old)]:
        was, now = old.get(key), new.get(key)
        if now is None:
            change = "paid"
        elif was is None:
            change = "new"
        else:
            same = was.amount == now.amount and was.expected_on == now.expected_on
            change = "unchanged" if same else "changed"
        either = now if now is not None else old[key]
        rows.append([either.invoice, either.customer,
                     None if was is None else was.amount, None if now is None else now.amount,
                     None if was is None else was.expected_on, None if now is None else now.expected_on, change])
    return pd.DataFrame(rows, columns=CHANGE_COLUMNS)


def reforecast_from_actuals(
    cfg: Cash13Config,
    actuals_by_week: Mapping[str, Mapping[str, float]],
    predicted: pd.DataFrame,
    invoices: pd.DataFrame,
    receipts: pd.DataFrame,
    open_invoices: pd.DataFrame,
) -> Reforecast:
    """The forecast rolled past its closed weeks, its open invoices placed again, and what changed.

    `actuals_by_week` is the closed weeks as `weekly_actuals_score` takes them
    and is refused on the same terms. `predicted` is the `predicted_receipts`
    result the forecast's invoice receipts came from; those receipts must be in
    `cfg.receipts` as `predicted_receipt_flows` made them, and are replaced.
    `invoices`, `receipts` and `open_invoices` are `predicted_receipts`' inputs
    as at the new window_start: the paid history now, with the invoices paid in
    full in the closed weeks, and the amounts still owed.

    Refuses an invoice receipt of `predicted` that is not in `cfg.receipts`,
    and an invoice `predicted` held that is now neither open nor in the paid
    history, which would leave the forecast without a word.
    """
    window_start, actuals = _closed_weeks(cfg, actuals_by_week)
    closed = len(actuals)
    scheduled = list(cfg.receipts)
    for flow in predicted_receipt_flows(predicted):
        if flow not in scheduled:
            raise ValueError(f"the forecast has no receipt {flow.name!r} of {flow.amount} in week "
                             f"{flow.start_week}; pass the predicted_receipts result its receipts came from")
        scheduled.remove(flow)
    start = window_start + timedelta(weeks=closed)
    placed = predicted_receipts(invoices, receipts, open_invoices, start, cfg.weeks)
    rolled = Cash13Config.model_validate(cfg.model_dump() | {
        "opening_cash": actuals[-1]["ending_cash"], "window_start": start,
        "receipts": [*_rolled(scheduled, closed), *predicted_receipt_flows(placed)],
        "disbursements": _rolled(cfg.disbursements, closed)})
    return Reforecast(rolled, placed, _changes(predicted, placed, set(invoices["invoice"].map(str))))
