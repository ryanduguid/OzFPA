# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""One tax report by due date: the existing schedules' rows and dates, joined and sorted."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from pyfpa.au import tax_report
from pyfpa.au.fbt import fbt_schedule
from pyfpa.au.gst import GstAssumptions, bas_schedule, monthly_gst
from pyfpa.au.payg_instalments import payg_instalment_schedule
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.payroll_settlement import SettlementEvent, settlement_events
from pyfpa.au.super_guarantee import super_due_rule

MONTHS = pd.period_range("2026-07", "2026-12", freq="M")


class _Weekdays:
    def add_business_days(self, d: date, n: int) -> date:
        while n:
            d += timedelta(days=1)
            n -= d.weekday() < 5
        return d

    def check_horizon(self, d: date) -> None:
        return None


def _seventh_of_next_month(day: date) -> date:
    following = pd.Period(day, freq="M") + 1
    return date(following.year, following.month, 7)


def _payroll(withholder: str = "medium"):
    payroll = pd.DataFrame({
        "gross_wages": [10000.0] * 6, "bonuses": [0.0] * 6, "super_guarantee": [1200.0] * 6,
        "payroll_tax": [500.0] * 6, "workers_comp": [90.0] * 6, "leave_provisions": [0.0] * 6,
    }, index=MONTHS)
    # Fortnightly Fridays from 3 July 2026.
    paydays = [date(2026, 7, 3) + timedelta(days=14 * n) for n in range(13)]
    rules = {
        "payg_withholding": paygw_due_rule(withholder, deferred_bas_payer=False),
        "super_guarantee": super_due_rule(_Weekdays()),
        "payroll_tax": _seventh_of_next_month,
        "workers_comp": _seventh_of_next_month,
    }
    return settlement_events(payroll, paydays, payg_withholding_rate_assumption=0.2, due_rules=rules)


def _schedules():
    revenue = pd.Series([50000.0] * 6, index=MONTHS)
    purchases = pd.Series([20000.0] * 6, index=MONTHS)
    bas = bas_schedule(monthly_gst(revenue, purchases, GstAssumptions(gst_rate=0.1))["net_gst"])
    instalments = payg_instalment_schedule(revenue, deferred_bas_payer=True, rate=0.02)
    return bas, instalments, fbt_schedule(2027, 4000.0)


def test_each_schedule_keeps_its_dates_and_totals():
    bas, instalments, fbt = _schedules()
    events = _payroll()
    report = tax_report(bas=bas, payg_instalments=instalments, payroll=events, fbt=fbt)
    by_obligation = report.groupby("obligation")["amount"].sum()
    assert by_obligation["GST (BAS)"] == bas["amount"].sum()
    assert by_obligation["PAYG instalment"] == instalments["amount"].sum()
    assert by_obligation["FBT"] == fbt["amount"].sum()
    for component, name in [("payg_withholding", "PAYG withholding"), ("super_guarantee", "Super guarantee"),
                            ("payroll_tax", "Payroll tax")]:
        assert by_obligation[name] == sum(e.amount for e in events if e.component == component)
    gst = report[report["obligation"] == "GST (BAS)"]
    assert gst["due_date"].tolist() == bas["due_date"].tolist()
    assert gst["nominal_due_date"].tolist() == bas["nominal_due_date"].tolist()
    assert report[report["obligation"] == "PAYG instalment"]["due_date"].tolist() == instalments["due_date"].tolist()
    assert report["due_date"].is_monotonic_increasing
    assert "Workers compensation" not in set(report["obligation"])


def test_a_quarterly_bas_statement_lists_gst_and_the_instalment_on_one_date():
    bas, instalments, _ = _schedules()
    report = tax_report(bas=bas, payg_instalments=instalments)
    # Both sit on the September quarter statement, due 28 October 2026.
    october = report[report["due_date"] == date(2026, 10, 28)]
    assert october[["obligation", "period", "amount"]].values.tolist() == [
        ["GST (BAS)", "2027Q1", 9000.0], ["PAYG instalment", "2027Q1", 3000.0]]
    assert pd.isna(october["nominal_due_date"].iloc[1])


def test_paydays_sharing_a_due_date_are_one_row():
    report = tax_report(payroll=_payroll())
    withholding = report[report["obligation"] == "PAYG withholding"]
    # A medium withholder pays each month's withholding on the 21st of the next;
    # Saturday 21 November 2026 moves to Monday 23 November.
    assert withholding["due_date"].tolist() == [
        date(2026, 8, 21), date(2026, 9, 21), date(2026, 10, 21), date(2026, 11, 23), date(2026, 12, 21),
        date(2027, 1, 21)]
    assert withholding["period"].tolist() == [str(month) for month in MONTHS]
    assert withholding["amount"].tolist() == [2000.0] * 6
    # Payday Super falls due a week or so after each payday, so each payday is its own row.
    assert len(report[report["obligation"] == "Super guarantee"]) == 13


def test_a_quarterly_withholder_names_the_months_its_row_covers():
    report = tax_report(payroll=_payroll("small"))
    withholding = report[report["obligation"] == "PAYG withholding"]
    assert withholding["period"].tolist() == ["2026-07 to 2026-09", "2026-10 to 2026-12"]
    assert withholding["amount"].tolist() == [6000.0, 6000.0]


def test_no_schedules_give_an_empty_report():
    report = tax_report()
    assert report.empty
    assert list(report.columns) == ["due_date", "obligation", "period", "amount", "nominal_due_date"]


def test_grouped_payroll_amounts_lose_no_cents_to_rounding():
    # Amounts read from a frame can be NumPy scalars, which leave sum()'s compensated float path.
    due = date(2026, 10, 7)
    events = [SettlementEvent("payroll_tax", pd.Period(month, freq="M"), date(2026, 9, 30), due, due, amount)
              for month, amount in [("2026-07", 1e16), ("2026-08", np.float64(1.0)), ("2026-09", 1.0)]]
    report = tax_report(payroll=events)
    assert report[["period", "amount"]].values.tolist() == [["2026-07 to 2026-09", 10000000000000002.0]]


def test_a_refund_keeps_its_sign_and_due_date():
    fbt = fbt_schedule(2027, -500.0)
    report = tax_report(fbt=fbt)
    assert report[["due_date", "amount"]].values.tolist() == [[fbt["due_date"].iloc[0], -500.0]]
