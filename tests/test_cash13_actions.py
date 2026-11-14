# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Up to 3 actions for each risk week, from the forecast's own rows.

Customers, suppliers and amounts are invented. Week n runs 7 days from
5 October 2026 plus 7(n - 1) days, so 28 October is in week 4 and 11 November
in week 6. Expected figures are worked out by hand beside each case.
"""

import random
from datetime import date, timedelta

import pandas as pd
import pytest

from pyfpa.au.gst import LodgmentChannel, quarterly_bas_due_date
from pyfpa.cash13.actions import risk_week_actions
from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow

START = date(2026, 10, 5)
SEP_QUARTER = pd.Period("2026-09", freq="M")


def _receivables(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["invoice", "customer", "amount", "due_on", "week"])


def _payables(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["bill", "payee", "amount", "due_on", "week"])


def _config(receivables: pd.DataFrame, payables: pd.DataFrame, opening: float, **extra) -> Cash13Config:
    placed = receivables[receivables["week"].notna()]
    return Cash13Config(
        opening_cash=opening, window_start=START,
        receipts=[WeeklyFlow(name=r.invoice, amount=r.amount, start_week=int(r.week)) for r in placed.itertuples()],
        disbursements=[WeeklyFlow(name=p.bill, amount=p.amount, start_week=int(p.week)) for p in payables.itertuples()],
        **extra)


RECEIVABLES = _receivables(
    ("INV-A", "Harbour Co", 8000.0, "2026-09-20", 6),   # overdue, expected week 6
    ("INV-B", "Ridge Co", 3000.0, "2026-09-30", 9),     # overdue, expected week 9
    ("INV-C", "Bay Co", 20000.0, "2026-10-20", 5),      # not yet due: never chased
    ("INV-D", "Cape Co", 1000.0, "2026-08-31", pd.NA),  # overdue, not expected in 13 weeks
    ("INV-E", "Dune Co", 1500.0, "2026-09-25", 7),      # overdue, expected week 7
)


def _payables_with_bas(due_on: date, bill: str = "BAS 2026Q1") -> pd.DataFrame:
    return _payables(
        ("RENT-10", "Landlord", 4000.0, "2026-10-20", 2),     # paid week 2, due week 3
        ("STOCK-7", "Supplier", 12000.0, "2026-11-02", 3),    # paid week 3, due week 5
        (bill, "ATO", 9000.0, due_on, 4),                     # paid week 4
    )


def test_each_risk_week_gets_its_three_largest_actions():
    payables = _payables_with_bas(quarterly_bas_due_date(SEP_QUARTER))
    # Ending cash: 10,000 opening; week 2 6,000 after rent; week 3 -6,000 after stock;
    # week 4 -15,000 after BAS; week 5 5,000 after INV-C.
    actions = risk_week_actions(_config(RECEIVABLES, payables, 10000.0), RECEIVABLES, payables)
    assert actions[["week", "shortfall", "rank", "action", "amount", "source"]].values.tolist() == [
        [3, 6000.0, 1, "pay on due date", 12000.0, "payables bill STOCK-7"],
        [3, 6000.0, 2, "chase", 8000.0, "receivables invoice INV-A"],
        [3, 6000.0, 3, "chase", 3000.0, "receivables invoice INV-B"],
        [4, 15000.0, 1, "pay on due date", 12000.0, "payables bill STOCK-7"],
        [4, 15000.0, 2, "chase", 8000.0, "receivables invoice INV-A"],
        [4, 15000.0, 3, "chase", 3000.0, "receivables invoice INV-B"],
    ]
    assert actions["detail"].tolist()[:2] == [
        "Pay STOCK-7 to Supplier on its due date, 2026-11-02 (week 5), not in week 3",
        "Chase Harbour Co for invoice INV-A, due 2026-09-20 and forecast to arrive in week 6",
    ]


def test_a_tax_payment_is_never_moved_past_its_due_date():
    # The BAS is the largest payment in week 4 but falls due that week, 28 October.
    due = quarterly_bas_due_date(SEP_QUARTER)
    assert due == date(2026, 10, 28)
    payables = _payables_with_bas(due)
    actions = risk_week_actions(_config(RECEIVABLES, payables, 10000.0), RECEIVABLES, payables)
    assert not actions["source"].str.contains("BAS").any()


def test_a_bas_the_forecast_pays_before_its_due_date_can_rank():
    # The business lodges online, so the September quarter's BAS is due 11 November,
    # week 6. The forecast pays it in week 4, so paying on the due date takes it out
    # of week 4, ranking between the stock bill and INV-A. It cannot help week 3,
    # which it was never in.
    due = quarterly_bas_due_date(SEP_QUARTER, LodgmentChannel.ONLINE)
    assert due == date(2026, 11, 11)
    payables = _payables_with_bas(due, "BAS 2026Q1 lodged online")
    actions = risk_week_actions(_config(RECEIVABLES, payables, 10000.0), RECEIVABLES, payables)
    week_4 = actions[actions["week"] == 4]
    assert week_4["source"].tolist() == [
        "payables bill STOCK-7", "payables bill BAS 2026Q1 lodged online", "receivables invoice INV-A"]
    assert week_4["detail"].tolist()[1] == (
        "Pay BAS 2026Q1 lodged online to ATO on its due date, 2026-11-11 (week 6), not in week 4")


def test_with_a_facility_the_weeks_below_the_buffer_are_the_risk_weeks():
    payables = _payables_with_bas(quarterly_bas_due_date(SEP_QUARTER))
    config = _config(RECEIVABLES, payables, 10000.0, facility_limit=10000.0, headroom_buffer=5000.0)
    # Headroom: week 3 4,000 (1,000 short of 5,000), week 4 -5,000 (10,000 short).
    actions = risk_week_actions(config, RECEIVABLES, payables)
    assert actions.groupby("week")["shortfall"].first().to_dict() == {3: 1000.0, 4: 10000.0}


def test_weeks_no_action_helps_say_nothing():
    # Week 1 is below zero, but rent is paid on its due date and INV-C is not yet due.
    receivables = _receivables(("INV-C", "Bay Co", 500.0, "2026-10-20", 3))
    payables = _payables(("RENT-10", "Landlord", 4000.0, "2026-10-05", 1),
                         ("LATE-1", "Supplier", 700.0, "2026-09-01", 1))  # already overdue
    actions = risk_week_actions(_config(receivables, payables, 1000.0), receivables, payables)
    assert actions.empty
    assert actions.columns.tolist() == ["week", "shortfall", "rank", "action", "amount", "source", "detail"]


def test_no_risk_weeks_gives_no_actions():
    payables = _payables_with_bas(quarterly_bas_due_date(SEP_QUARTER))
    assert risk_week_actions(_config(RECEIVABLES, payables, 100000.0), RECEIVABLES, payables).empty


@pytest.mark.parametrize(
    ("which", "change", "match"),
    [
        ("receivables", lambda f: f.drop(columns="due_on"), r"missing \['due_on'\]"),
        ("receivables", lambda f: f.assign(amount=[0.0, *f["amount"][1:]]), "finite number above 0"),
        ("receivables", lambda f: f.assign(invoice=["INV-A", *f["invoice"][:-1]]), "each invoice must appear once"),
        ("receivables", lambda f: f.assign(due_on=[None, *f["due_on"][1:]]), "needs a due_on date"),
        ("receivables", lambda f: f.assign(due_on=["20/09/2026", *f["due_on"][1:]]), "ISO date"),
        ("receivables", lambda f: f.assign(week=[14, *f["week"][1:]]), "from 1 to 13 or missing"),
        ("receivables", lambda f: f.assign(week=["soon", *f["week"][1:]]), "from 1 to 13 or missing"),
        ("receivables", lambda f: f.assign(week=[2.5, *f["week"][1:]]), "from 1 to 13 or missing"),
        ("payables", lambda f: f.assign(week=[pd.NA, *f["week"][1:]]), r"from 1 to 13$"),
        ("payables", lambda f: f.assign(amount=[float("nan"), *f["amount"][1:]]), "finite number above 0"),
        # A row that would name nobody in its action.
        ("receivables", lambda f: f.assign(customer=[None, *f["customer"][1:]]), "needs its invoice and a customer name"),
        ("receivables", lambda f: f.assign(invoice=[None, *f["invoice"][1:]]), "needs its invoice and a customer name"),
        ("payables", lambda f: f.assign(payee=[" ", *f["payee"][1:]]), "needs its bill and a payee name"),
    ],
)
def test_rows_that_cannot_be_ranked_are_refused(which, change, match):
    frames = {"receivables": RECEIVABLES, "payables": _payables_with_bas(quarterly_bas_due_date(SEP_QUARTER))}
    config = _config(frames["receivables"], frames["payables"], 10000.0)
    frames[which] = change(frames[which])
    with pytest.raises(ValueError, match=match):
        risk_week_actions(config, frames["receivables"], frames["payables"])


def test_a_config_without_window_start_is_refused():
    with pytest.raises(ValueError, match="window_start"):
        risk_week_actions(Cash13Config(opening_cash=-1.0), _receivables(), _payables())


def _ending(config: Cash13Config, week: int) -> float:
    return float(cash13_forecast(config).at[week, "ending_cash"])


def _moved(config: Cash13Config, side: str, name: str, week: int | None) -> Cash13Config:
    flows = [flow for flow in getattr(config, side) if flow.name != name]
    flows += [flow.model_copy(update={"start_week": week}) for flow in getattr(config, side)
              if flow.name == name and week is not None]
    return config.model_copy(update={side: flows})


@pytest.mark.parametrize("seed", range(200))
def test_each_action_adds_its_amount_to_its_week_and_nothing_passes_its_due_date(seed):
    rng = random.Random(seed)
    receivables = _receivables(*[
        (f"INV-{n}", f"Customer {n % 3}", round(rng.uniform(1, 20000), 2),
         (START + timedelta(days=rng.randint(-60, 60))).isoformat(), rng.choice([pd.NA, *range(1, 14)]))
        for n in range(rng.randint(0, 8))])
    payables = _payables(*[
        (f"BILL-{n}", rng.choice(["ATO", "Supplier"]), round(rng.uniform(1, 20000), 2),
         (START + timedelta(days=rng.randint(-20, 120))).isoformat(), rng.randint(1, 13))
        for n in range(rng.randint(0, 8))])
    config = _config(receivables, payables, round(rng.uniform(-5000, 30000), 2))
    actions = risk_week_actions(config, receivables, payables)
    due = dict(zip(payables["bill"], payables["due_on"], strict=True))
    for week, rows in actions.groupby("week"):
        assert rows["rank"].tolist() == list(range(1, len(rows) + 1)) and len(rows) <= 3
        assert rows["amount"].is_monotonic_decreasing
    for row in actions.itertuples():
        name = row.source.rsplit(" ", 1)[1]
        if row.action == "chase":
            changed = _moved(config, "receipts", name, row.week)
        else:
            due_on = date.fromisoformat(due[name])
            due_week = (due_on - START).days // 7 + 1
            assert due_week > row.week and f"on its due date, {due_on.isoformat()} " in row.detail
            changed = _moved(config, "disbursements", name, due_week if due_week <= 13 else None)
        assert _ending(changed, row.week) - _ending(config, row.week) == pytest.approx(row.amount)
