# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Up to 3 actions for each week the 13-week forecast flags, from rows it already holds.

An action counts for a risk week only when it moves its whole amount into that
week's ending cash without moving anything past its due date:

- chase: an overdue receivable (due before the window starts) that the
  forecast expects after the risk week; collecting it by then adds it.
- pay on due date: a payment the forecast makes in or before the risk week
  whose due date falls in a later week; paying it on that date instead keeps
  it out of the week.

Nothing moves past its `due_on`, so a tax payment is never deferred past its
due date. The actions are suggestions for a person to weigh: chasing does not
make a customer pay, and a supplier may want its money earlier than the due date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.receivables import _any_bool
from pyfpa.cash13.runway import runway_summary
from pyfpa.cash13.schemas import Cash13Config
from pyfpa.models.working_capital import _dates

MAX_ACTIONS = 3
COLUMNS = ["week", "shortfall", "rank", "action", "amount", "source", "detail"]


def _require_names(frame: pd.DataFrame, name: str, key: str, party: str) -> None:
    """Refuse a row whose action would name no invoice or bill, or nobody, or the same one as another row."""
    if frame[key].isna().any() or not all(str(value).strip() for value in frame[key]) or not all(
            isinstance(value, str) and value.strip() for value in frame[party]):
        raise ValueError(f"every {name} row needs its {key} and a {party} name")
    # As text, the form each action's source takes, so 1 and '1' are one key.
    if frame[key].map(str).duplicated().any():
        raise ValueError(f"each {key} must appear once in {name}")


def _require_in_forecast(weekly: pd.DataFrame, receivables: pd.DataFrame, payables: pd.DataFrame) -> None:
    """Refuse rows the forecast cannot hold: more in a week than its receipts or disbursements that week.

    A necessary check, not a full match: the forecast's flows carry no invoice or bill, so a row
    that fits inside a week's total is taken to be one of that week's flows.
    """
    for name, frame, column in (("receivables", receivables, "receipts"), ("payables", payables, "disbursements")):
        by_week = frame.groupby("week")["amount"].sum()
        over = [int(week) for week, total in by_week.items() if total > weekly.at[int(week), column] + 0.005]
        if over:
            raise ValueError(f"{name} in weeks {over} add up to more than the forecast's {column} there; "
                             "pass the rows the forecast's flows came from")


def _checked(frame: pd.DataFrame, name: str, key: str, party: str, weeks: int, *, week_optional: bool) -> pd.DataFrame:
    """The frame with numeric amounts, date due_on and integer-or-missing weeks, or a ValueError."""
    missing = {key, party, "amount", "due_on", "week"} - set(frame.columns)
    if missing:
        raise ValueError(f"{name} needs columns {key}, {party}, amount, due_on and week; missing {sorted(missing)}")
    amounts = pd.to_numeric(frame["amount"], errors="coerce")
    if _any_bool(frame["amount"]) or amounts.isna().any() or not (np.isfinite(amounts) & (amounts > 0)).all():
        raise ValueError(f"each {name} amount must be a finite number above 0")
    _require_names(frame, name, key, party)
    if frame["due_on"].isna().any():
        raise ValueError(f"every {name} row needs a due_on date")
    week = pd.to_numeric(frame["week"], errors="coerce")
    placed = week.dropna()
    not_a_number = _any_bool(frame["week"]) or (week.isna() & frame["week"].notna()).any()
    if not_a_number or (not week_optional and week.isna().any()) or not (
            (placed % 1 == 0) & placed.between(1, weeks)).all():
        raise ValueError(f"each {name} week must be a whole number from 1 to {weeks}"
                         + (" or missing" if week_optional else ""))
    return frame.assign(amount=amounts.astype(float), due_on=_dates(frame["due_on"], "due_on").dt.date,
                        week=week.astype("Int64"))


def risk_week_actions(cfg: Cash13Config, receivables: pd.DataFrame, payables: pd.DataFrame) -> pd.DataFrame:
    """For each risk week, up to 3 actions ranked by amount, each naming its source row.

    Risk weeks are `runway_summary`'s `headroom_breach_weeks` when the config
    states a facility, otherwise its `negative_weeks`; `shortfall` is how far the
    week falls below the buffer or below zero. The config needs `window_start`.

    `receivables` has invoice, customer, amount, due_on and week, the week the
    forecast expects the money (missing when it is not expected in the window),
    as `predicted_receipts` gives them with a due_on column. `payables` has bill,
    payee, amount, due_on and week, the week the forecast pays it. For a tax
    payment, due_on is the `bas_schedule` or `payg_instalment_schedule` due_date
    under the `LodgmentChannel` the business already lodges by, the one the
    forecast was built with; never a payment plan date, and never another
    channel's later date, because nothing here can check that the business
    qualifies for it.

    Returns one row per action, columns week, shortfall, rank, action, amount,
    source and detail; a risk week no action helps has no rows. An action that
    helps several risk weeks appears in each, so its amount is not extra cash
    for every week: add amounts within a week, never across weeks. Ties in
    amount rank by source, so the same rows always give the same answer.
    Refuses receivables or payables that add up to more in a week than the
    forecast's receipts or disbursements that week, which cannot be its flows.
    """
    if cfg.window_start is None:
        raise ValueError("risk_week_actions needs the config's window_start to place due dates in weeks")
    start = cfg.window_start
    receivables = _checked(receivables, "receivables", "invoice", "customer", cfg.weeks, week_optional=True)
    payables = _checked(payables, "payables", "bill", "payee", cfg.weeks, week_optional=False)

    # Each candidate adds its amount to the ending cash of weeks first to last.
    candidates: list[tuple[int, int, str, float, str, str]] = []
    for row in receivables.itertuples(index=False):
        if row.due_on < start and pd.notna(row.week):
            candidates.append((1, row.week - 1, "chase", row.amount, f"receivables invoice {row.invoice}",
                               f"Chase {row.customer} for invoice {row.invoice}, due {row.due_on.isoformat()} "
                               f"and forecast to arrive in week {row.week}"))
    for row in payables.itertuples(index=False):
        due_week = (row.due_on - start).days // 7 + 1
        candidates.append((row.week, due_week - 1, "pay on due date", row.amount, f"payables bill {row.bill}",
                           f"Pay {row.bill} to {row.payee} on its due date, {row.due_on.isoformat()} "
                           f"(week {due_week}), not in week {row.week}"))

    weekly = cash13_forecast(cfg)
    _require_in_forecast(weekly, receivables, payables)
    summary = runway_summary(weekly, cfg.headroom_buffer)
    if cfg.facility_limit is None:
        risk = {week: -weekly.at[week, "ending_cash"] for week in summary["negative_weeks"]}
    else:
        risk = {week: cfg.headroom_buffer - weekly.at[week, "headroom"] for week in summary["headroom_breach_weeks"]}
    rows: list[list[object]] = []
    for week, shortfall in risk.items():
        helping = sorted((c for c in candidates if c[0] <= week <= c[1]), key=lambda c: (-c[3], c[4]))
        for rank, (_, _, action, amount, source, detail) in enumerate(helping[:MAX_ACTIONS], start=1):
            rows.append([week, float(shortfall), rank, action, amount, source, detail])
    return pd.DataFrame(rows, columns=COLUMNS)
