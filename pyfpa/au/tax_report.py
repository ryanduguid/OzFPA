# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""One table of tax payments by due date, joined from the pack's existing schedules.

Each source keeps its own rules: `bas_schedule` (net GST), `payg_instalment_schedule`,
`settlement_events` (PAYG withholding, super guarantee and payroll tax, through the
due-date rules the caller passed) and `fbt_schedule`. This module only lists their
rows together; it computes no amount or date. Payroll events that share a component
and due date are one row, whose period runs from the first payday's month to the last.
A schedule that keeps no nominal date leaves `nominal_due_date` empty.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd

from pyfpa.au.payroll_settlement import SettlementEvent

COLUMNS = ["due_date", "obligation", "period", "amount", "nominal_due_date"]
# Payroll components that are taxes or super; net wages and workers compensation are not reported.
PAYROLL_OBLIGATIONS = {"payg_withholding": "PAYG withholding", "super_guarantee": "Super guarantee",
                       "payroll_tax": "Payroll tax"}


def _schedule_rows(schedule: pd.DataFrame | None, obligation: str, period_column: str) -> list[dict[str, object]]:
    if schedule is None:
        return []
    nominal = schedule["nominal_due_date"] if "nominal_due_date" in schedule else [None] * len(schedule)
    return [
        {"due_date": due, "obligation": obligation, "period": str(period), "amount": float(amount),
         "nominal_due_date": nominal_due}
        for due, period, amount, nominal_due in zip(
            schedule["due_date"], schedule[period_column], schedule["amount"], nominal, strict=True)
    ]


def _payroll_rows(events: Sequence[SettlementEvent]) -> list[dict[str, object]]:
    groups: dict[tuple[str, date], list[SettlementEvent]] = {}
    for event in events:
        if event.component in PAYROLL_OBLIGATIONS:
            groups.setdefault((event.component, event.due_date), []).append(event)
    rows: list[dict[str, object]] = []
    for (component, due), group in groups.items():
        first = min(event.source_period for event in group)
        last = max(event.source_period for event in group)
        rows.append({"due_date": due, "obligation": PAYROLL_OBLIGATIONS[component],
                     "period": str(first) if first == last else f"{first} to {last}",
                     "amount": sum(event.amount for event in group), "nominal_due_date": None})
    return rows


def tax_report(
    *,
    bas: pd.DataFrame | None = None,
    payg_instalments: pd.DataFrame | None = None,
    payroll: Sequence[SettlementEvent] = (),
    fbt: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Every payment the given schedules hold, by due date, then obligation and period.

    Columns: due_date, obligation, period, amount (negative is a refund) and
    nominal_due_date. Each obligation's amounts add up to its schedule's.
    """
    rows = (_schedule_rows(bas, "GST (BAS)", "period_label")
            + _schedule_rows(payg_instalments, "PAYG instalment", "quarter")
            + _payroll_rows(payroll)
            + _schedule_rows(fbt, "FBT", "period_label"))
    report = pd.DataFrame(rows, columns=COLUMNS)
    return report.sort_values(["due_date", "obligation", "period"], kind="stable", ignore_index=True)
