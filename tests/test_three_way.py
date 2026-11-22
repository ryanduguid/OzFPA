# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Three-way forecast: the balance sheet balances and cash reconciles in every month."""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from pyfpa import load_config, three_way_from_config
from pyfpa.au.gst import BasCycle, GstAssumptions, LodgmentChannel, monthly_gst
from pyfpa.au.paygw import paygw_due_rule
from pyfpa.au.payroll_settlement import monthly_settlement, settlement_events
from pyfpa.au.super_guarantee import super_due_rule
from pyfpa.config.schemas import (
    Channel,
    DebtInstrument,
    EntityConfig,
    IncomeTaxConfig,
    OpeningBalances,
    OpexLine,
    WorkingCapitalConfig,
)
from pyfpa.models.cashflow import cashflow_from_config

OPERATING_LINES = ["net_income", "da", "working_capital", "payroll_unpaid", "income_tax_unpaid", "gst"]


def _config(**changes: Any) -> EntityConfig:
    fields: dict[str, Any] = {
        "name": "Three Way Co", "start_month": "2026-07", "horizon_months": 12, "tax_rate": 0.25,
        "da_monthly": 50.0, "capex_monthly": 40.0,
        "channels": [Channel(name="Shop", annual_revenue=120000.0, growth_rate=0.1,
                             seasonality=[1.0] * 6 + [1.5] * 6, cogs_pct=0.4)],
        "opex": [OpexLine(name="Rent", kind="fixed", monthly_amount=2000.0),
                 OpexLine(name="Ads", kind="variable", pct_of_revenue=0.05)],
        "debt": [DebtInstrument(name="Loan", kind="term_loan", opening_balance=20000.0,
                                annual_rate=0.08, monthly_principal=500.0),
                 DebtInstrument(name="Facility", kind="loc", opening_balance=5000.0, annual_rate=0.1)],
        "working_capital": WorkingCapitalConfig(dso_days=45, dpo_days=30, dio_days=60),
        "opening_balances": OpeningBalances(cash=10000.0, ar=14000.0, ap=3500.0, inventory=8000.0,
                                            fixed_assets=6000.0),
    }
    return EntityConfig(**(fields | changes))


def _assert_statements_hold(result, cfg: EntityConfig) -> None:
    sheet, flows, pnl = result.balance_sheet, result.cash_flow, result.profit_and_loss
    assert len(sheet) == cfg.horizon_months + 1
    assert sheet.index[0] == pd.Period(cfg.start_month, freq="M") - 1
    assert sheet["check_balance"].abs().max() == pytest.approx(0.0, abs=1e-6)
    # Cash on the balance sheet is the cash flow statement's, month by month.
    assert flows["opening_cash"].tolist() == pytest.approx(sheet["cash"].iloc[:-1].tolist())
    assert flows["closing_cash"].tolist() == pytest.approx(sheet["cash"].iloc[1:].tolist())
    assert (flows["closing_cash"] - flows["opening_cash"]).tolist() == pytest.approx(flows["change_in_cash"].tolist())
    assert flows[OPERATING_LINES].sum(axis=1).tolist() == pytest.approx(flows["operating_cash_flow"].tolist())
    assert (flows["operating_cash_flow"] + flows["capex"] + flows["debt_repaid"]).tolist() == pytest.approx(
        flows["change_in_cash"].tolist())
    # Equity moves only by net income, which is the profit and loss's.
    assert sheet["equity"].diff().iloc[1:].tolist() == pytest.approx(pnl["net_income"].tolist())
    assert flows["net_income"].tolist() == pytest.approx(pnl["net_income"].tolist())


def _net_gst(result, gst: GstAssumptions) -> pd.Series:
    """Net GST recomputed from the statements: stock bought plus operating expenses and capex."""
    pnl, sheet, flows = result.profit_and_loss, result.balance_sheet, result.cash_flow
    stock_bought = pnl["cogs"] + sheet["inventory"].diff().iloc[1:]
    purchases = stock_bought + pnl["opex"] - flows["capex"]
    return monthly_gst(pnl["revenue"], purchases, gst)["net_gst"]


def test_without_tax_layers_the_statements_match_the_monthly_forecast():
    cfg = _config()
    result = three_way_from_config(cfg)
    _assert_statements_hold(result, cfg)
    monthly = cashflow_from_config(cfg)
    pd.testing.assert_frame_equal(result.profit_and_loss, monthly[list(result.profit_and_loss.columns)])
    assert result.cash_flow["closing_cash"].tolist() == pytest.approx(monthly["ending_cash"].tolist())
    assert list(result.profit_and_loss.columns) == [
        "revenue", "cogs", "gross_profit", "opex", "ebitda", "da", "interest", "pretax_income", "tax", "net_income"]


def test_the_opening_balance_sheet_is_the_configuration():
    opening = three_way_from_config(_config()).balance_sheet.iloc[0]
    assert opening[["cash", "receivables", "inventory", "fixed_assets", "payables", "debt"]].tolist() == [
        10000.0, 14000.0, 8000.0, 6000.0, 3500.0, 25000.0]
    # Assets of 38,000 less liabilities of 28,500.
    assert opening["equity"] == 9500.0


def test_fixed_assets_roll_forward_by_capex_less_depreciation():
    sheet = three_way_from_config(_config()).balance_sheet
    assert sheet["fixed_assets"].iloc[-1] == pytest.approx(6000.0 + 12 * (40.0 - 50.0))
    assert sheet["debt"].iloc[-1] == pytest.approx(25000.0 - 12 * 500.0)


def test_bad_debts_and_replenished_stock_still_balance():
    cfg = _config(working_capital=WorkingCapitalConfig(
        collection_profile=[0.5, 0.45], bad_debt_share=0.05, write_off_after_months=3,
        opening_ar_collection_profile=[0.6, 0.4], dpo_days=30, dio_days=60, inventory_basis="replenishment"))
    result = three_way_from_config(cfg)
    _assert_statements_hold(result, cfg)
    assert "bad_debts" in result.profit_and_loss


def test_income_tax_payable_rolls_from_the_opening_balance_by_provision_less_payments():
    payments = {"2026-07": 3000.0, "2026-10": 1500.0, "2027-02": 1500.0}
    cfg = _config(
        income_tax=IncomeTaxConfig(forecast_losses_deductible=True, payments=payments),
        opening_balances=OpeningBalances(cash=10000.0, ar=14000.0, ap=3500.0, inventory=8000.0,
                                         fixed_assets=6000.0, income_tax_payable=3000.0))
    result = three_way_from_config(cfg)
    _assert_statements_hold(result, cfg)
    payable = result.balance_sheet["income_tax_payable"]
    assert payable.iloc[0] == 3000.0
    expected = 3000.0 + result.profit_and_loss["tax"].sum() - sum(payments.values())
    assert payable.iloc[-1] == pytest.approx(expected)
    assert result.cash_flow["income_tax_unpaid"].iloc[0] == pytest.approx(
        result.profit_and_loss["tax"].iloc[0] - 3000.0)


def test_opening_income_tax_payable_needs_a_payment_schedule():
    with pytest.raises(ValidationError, match="income_tax_payable needs income_tax"):
        _config(opening_balances=OpeningBalances(income_tax_payable=100.0))


def test_gst_is_paid_on_the_bas_due_dates():
    cfg = _config()
    result = three_way_from_config(cfg, gst=GstAssumptions(gst_rate=0.1))
    _assert_statements_hold(result, cfg)
    sheet, pnl = result.balance_sheet, result.profit_and_loss
    monthly = cashflow_from_config(cfg)
    net = _net_gst(result, GstAssumptions(gst_rate=0.1))
    payable = sheet["gst_payable"]
    # July to September is owed until its BAS is paid on 28 October 2026.
    assert payable[pd.Period("2026-09", freq="M")] == pytest.approx(net["2026-07":"2026-09"].sum())
    assert payable[pd.Period("2026-10", freq="M")] == pytest.approx(net["2026-10"])
    # April to June 2027 falls due after the forecast ends.
    assert payable.iloc[-1] == pytest.approx(net["2027-04":"2027-06"].sum())
    # Receivables and payables carry GST; the profit and loss does not.
    assert sheet["receivables"].iloc[1:].tolist() == pytest.approx((monthly["revenue"] * 45 / 30 * 1.1).tolist())
    pd.testing.assert_series_equal(pnl["revenue"], monthly["revenue"])


def test_monthly_gst_with_partly_taxable_sales_balances():
    cfg = _config(horizon_months=6)
    gst = GstAssumptions(bas_cycle=BasCycle.MONTHLY, taxable_sales_pct=0.7, creditable_purchases_pct=0.8)
    result = three_way_from_config(cfg, gst=gst)
    _assert_statements_hold(result, cfg)
    # Each month's GST is paid on the 21st of the next, so only December's is owed at the end.
    net = _net_gst(result, gst)
    assert result.balance_sheet["gst_payable"].iloc[1:].tolist() == pytest.approx(net.tolist())


def test_gst_for_a_quarter_still_open_at_the_end_stays_owed():
    cfg = _config(horizon_months=2)
    result = three_way_from_config(cfg, gst=GstAssumptions())
    _assert_statements_hold(result, cfg)
    assert result.balance_sheet["gst_payable"].iloc[-1] == pytest.approx(_net_gst(result, GstAssumptions()).sum())

def test_a_gst_refund_is_received_on_the_bas_due_date():
    # Capex of 30,000 a month buys more than the shop sells, so every quarter is a refund.
    cfg = _config(capex_monthly=30000.0)
    gst = GstAssumptions(gst_rate=0.1)
    result = three_way_from_config(cfg, gst=gst)
    _assert_statements_hold(result, cfg)
    net = _net_gst(result, gst)
    payable, flows = result.balance_sheet["gst_payable"], result.cash_flow
    september, october = pd.Period("2026-09", freq="M"), pd.Period("2026-10", freq="M")
    refund = net["2026-07":"2026-09"].sum()
    assert refund < 0
    assert payable[september] == pytest.approx(refund)
    assert payable[october] == pytest.approx(net["2026-10"])
    # October's GST cash is the GST collected less GST paid that month, plus the refund.
    sheet = result.balance_sheet
    trade_gst = net + (sheet["payables"] / 11).diff().iloc[1:] - (sheet["receivables"] / 11).diff().iloc[1:]
    assert flows["gst"][october] == pytest.approx(trade_gst[october] - refund)


def _with_opening_gst(gst: GstAssumptions, opening_gst: float, **changes: Any):
    """The forecast with and without an opening GST balance, which nothing else distinguishes."""
    balances = {"cash": 10000.0, "ar": 14000.0, "ap": 3500.0, "inventory": 8000.0, "fixed_assets": 6000.0}
    cfg = _config(opening_balances=OpeningBalances(**balances, gst_payable=opening_gst), **changes)
    result = three_way_from_config(cfg, gst=gst)
    _assert_statements_hold(result, cfg)
    return result, three_way_from_config(_config(opening_balances=OpeningBalances(**balances), **changes), gst=gst)


@pytest.mark.parametrize(("start", "cycle", "opening_gst", "settled"), [
    # The June quarter's BAS is due on 28 July 2026.
    ("2026-07", BasCycle.QUARTERLY, 3000.0, "2026-07"),
    # July is part of the September quarter, whose BAS is due on 28 October 2026.
    ("2026-08", BasCycle.QUARTERLY, 3000.0, "2026-10"),
    # June's monthly statement is due on 21 July 2026; a negative balance is a refund.
    ("2026-07", BasCycle.MONTHLY, -500.0, "2026-07"),
])
def test_an_opening_gst_balance_is_settled_on_the_prior_periods_bas_date(start, cycle, opening_gst, settled):
    with_balance, without = _with_opening_gst(GstAssumptions(bas_cycle=cycle), opening_gst, start_month=start)
    owed = with_balance.balance_sheet["gst_payable"] - without.balance_sheet["gst_payable"]
    cash = with_balance.balance_sheet["cash"] - without.balance_sheet["cash"]
    paid = pd.Period(settled, freq="M")
    assert owed[:paid - 1].tolist() == pytest.approx([opening_gst] * len(owed[:paid - 1]))
    assert owed[paid:].tolist() == pytest.approx([0.0] * len(owed[paid:]))
    assert cash[:paid - 1].tolist() == pytest.approx([0.0] * len(cash[:paid - 1]))
    assert cash[paid:].tolist() == pytest.approx([-opening_gst] * len(cash[paid:]))
    assert with_balance.cash_flow["gst"][paid] - without.cash_flow["gst"][paid] == pytest.approx(-opening_gst)
    pd.testing.assert_frame_equal(with_balance.profit_and_loss, without.profit_and_loss)


def test_an_opening_gst_balance_due_after_the_forecast_stays_owed():
    with_balance, without = _with_opening_gst(GstAssumptions(), 3000.0, start_month="2026-08", horizon_months=2)
    owed = with_balance.balance_sheet["gst_payable"] - without.balance_sheet["gst_payable"]
    assert owed.tolist() == pytest.approx([3000.0] * 3)


def test_without_an_opening_gst_balance_the_prior_quarter_is_not_looked_up():
    # No agent program date is recorded for the March 2026 quarter.
    cfg = _config(start_month="2026-04", horizon_months=3)
    _assert_statements_hold(three_way_from_config(cfg, gst=GstAssumptions(lodgment_channel=LodgmentChannel.AGENT)), cfg)
    with pytest.raises(ValueError, match="no agent program date is recorded for the quarter ending 2026-03"):
        _with_opening_gst(GstAssumptions(lodgment_channel=LodgmentChannel.AGENT), 100.0,
                          start_month="2026-04", horizon_months=3)


def test_an_opening_gst_balance_needs_gst():
    cfg = _config(opening_balances=OpeningBalances(gst_payable=100.0))
    with pytest.raises(ValueError, match="gst_payable needs gst"):
        three_way_from_config(cfg)


def test_statement_totals_that_overflow_are_refused():
    cfg = _config(opening_balances=OpeningBalances(cash=1e308, ar=14000.0, ap=3500.0, inventory=8000.0,
                                                   fixed_assets=1e308), horizon_months=1)
    with pytest.raises(ValueError, match="total_assets contains non-finite values"):
        three_way_from_config(cfg)

def test_gst_on_bad_debts_is_refused():
    cfg = _config(working_capital=WorkingCapitalConfig(
        collection_profile=[0.5, 0.45], bad_debt_share=0.05, write_off_after_months=3,
        opening_ar_collection_profile=[1.0], dpo_days=30, dio_days=60))
    with pytest.raises(ValueError, match="GST on bad debts is not modelled"):
        three_way_from_config(cfg, gst=GstAssumptions())


def test_depreciation_beyond_the_fixed_assets_is_refused():
    cfg = _config(opening_balances=OpeningBalances(cash=10000.0, ar=14000.0, ap=3500.0, inventory=8000.0),
                  capex_monthly=0.0)
    with pytest.raises(ValueError, match="fixed assets below nil in 2026-07"):
        three_way_from_config(cfg)


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


def _payroll_events():
    months = pd.period_range("2026-06", "2026-09", freq="M")
    payroll = pd.DataFrame({
        "gross_wages": [8000.0] * 4, "bonuses": [0.0] * 4, "super_guarantee": [960.0] * 4,
        "payroll_tax": [0.0] * 4, "workers_comp": [100.0] * 4, "leave_provisions": [200.0] * 4,
    }, index=months)
    paydays = [date(2026, 6, 26), date(2026, 7, 31), date(2026, 8, 28), date(2026, 9, 25)]
    rules = {
        "payg_withholding": paygw_due_rule("medium", deferred_bas_payer=False),
        "super_guarantee": super_due_rule(_Weekdays()),
        "payroll_tax": _seventh_of_next_month,
        "workers_comp": _seventh_of_next_month,
    }
    return settlement_events(payroll, paydays, payg_withholding_rate_assumption=0.2, due_rules=rules)


def test_payroll_liabilities_follow_the_settlement_events():
    cfg = _config(horizon_months=3)
    events = _payroll_events()
    result = three_way_from_config(cfg, payroll=events)
    _assert_statements_hold(result, cfg)
    settled = monthly_settlement(events, pd.period_range("2026-07", periods=3, freq="M"))
    sheet = result.balance_sheet.iloc[1:]
    assert sheet["paygw_payable"].tolist() == pytest.approx(settled["payg_withholding_closing"].tolist())
    assert sheet["super_payable"].tolist() == pytest.approx(settled["super_guarantee_closing"].tolist())
    # June's withholding is due on 21 July and its super on 28 July: both are owed at the start.
    opening = result.balance_sheet.iloc[0]
    assert opening["paygw_payable"] == pytest.approx(1600.0)
    assert opening["super_payable"] == pytest.approx(960.0)
    assert opening["other_payroll_payable"] == pytest.approx(100.0)
    # Gross wages, super and workers compensation; leave provisions are not settled here.
    assert result.profit_and_loss["payroll"].tolist() == pytest.approx([9060.0] * 3)
    without = three_way_from_config(cfg).profit_and_loss
    assert (without["ebitda"] - result.profit_and_loss["ebitda"]).tolist() == pytest.approx([9060.0] * 3)


def test_every_layer_together_balances():
    cfg = _config(
        income_tax=IncomeTaxConfig(forecast_losses_deductible=False, payments={"2026-08": 2000.0}),
        working_capital=WorkingCapitalConfig(dso_days=45, dpo_days=30, dio_days=60, inventory_basis="replenishment"),
        horizon_months=3)
    result = three_way_from_config(cfg, gst=GstAssumptions(bas_cycle=BasCycle.MONTHLY), payroll=_payroll_events())
    _assert_statements_hold(result, cfg)
    assert result.cash_flow["gst"].abs().sum() > 0
    assert result.balance_sheet["paygw_payable"].iloc[1:].gt(0).all()


def test_the_documented_ridgeline_example_balances():
    cfg = load_config(Path(__file__).resolve().parents[1] / "examples/ridgeline/config.yaml")
    result = three_way_from_config(cfg, gst=GstAssumptions())
    _assert_statements_hold(result, cfg)
    assert result.balance_sheet["check_balance"].abs().max() < 0.01
