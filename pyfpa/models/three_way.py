# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Three-way forecast: profit and loss, balance sheet and cash flow from one configuration.

The statements share the drivers of `cashflow_from_config`. The balance sheet
rolls each balance forward on its own: receivables, stock and payables from the
working-capital model, fixed assets from capex less D&A, debt from its schedule,
tax, GST and payroll liabilities from what accrues less what is paid, and equity
from net income. Cash comes from the cash flow statement. `check_balance` is
assets less liabilities and equity, so a cash flow that missed a non-cash item
shows there; it is nil in every month.

Two optional layers use the pack's timing code unchanged:

- `gst`: net GST from `monthly_gst` on revenue and on purchases of stock,
  operating expenses and capex, paid or refunded on `bas_schedule`'s due dates.
  Receivables and payables carry GST on their taxable and creditable shares;
  operating expenses and capex are paid with their GST in the month.
  `opening_balances.gst_payable` is the net GST owed at the start for the BAS
  period holding the month before it, settled on that period's due date.
- `payroll`: events from `settlement_events`, whose due-date rules (such as
  `paygw_due_rule` and `super_due_rule`) set when PAYG withholding, super and
  the other payroll costs are paid. Obligations in a forecast month are its
  payroll expense; unpaid amounts are payroll liabilities, and an obligation
  before the first month is an opening liability.

Opening receivables and payables are stated excluding GST, as in the
configuration; their GST is added on the balance sheet. Opening equity is the
opening net assets. Leave provisions, GST on bad debts and deferred tax are not
modelled.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from pyfpa.au.gst import GstAssumptions, bas_schedule, monthly_gst
from pyfpa.au.payroll_settlement import COMPONENTS, SettlementEvent, monthly_settlement
from pyfpa.config._snapshot import _validated_snapshot
from pyfpa.config.schemas import EntityConfig, OpeningBalances
from pyfpa.models.cashflow import _compose, _require_finite_columns
from pyfpa.models.periods import month_index

# Dollars. Net book value this close below nil is floating-point noise.
_NEGATIVE_BALANCE_TOLERANCE = 1e-6
_OTHER_PAYROLL = ("net_wages", "payroll_tax", "workers_comp")


@dataclass(frozen=True)
class ThreeWayForecast:
    """Monthly statements; the balance sheet adds an opening row for the month before."""

    profit_and_loss: pd.DataFrame
    balance_sheet: pd.DataFrame
    cash_flow: pd.DataFrame


def _opening_and_closing(opening: float, closing: pd.Series) -> pd.Series:
    index = pd.PeriodIndex([closing.index[0] - 1]).append(closing.index)
    return pd.Series([opening, *closing], index=index, dtype=float)


def _movement(closing: pd.Series, opening: float) -> pd.Series:
    return closing.diff().fillna(closing.iloc[0] - opening)


def _payroll_layer(
    payroll: Sequence[SettlementEvent], months: pd.PeriodIndex
) -> tuple[pd.DataFrame | None, dict[str, tuple[float, pd.Series]]]:
    """Accrued cost and cash paid by month, and each liability's opening and closing balances."""
    zero = pd.Series(0.0, index=months)
    groups = {"paygw_payable": ("payg_withholding",), "super_payable": ("super_guarantee",),
              "other_payroll_payable": _OTHER_PAYROLL}
    if not payroll:
        return None, dict.fromkeys(groups, (0.0, zero))
    settled = monthly_settlement(payroll, months)
    costs = pd.DataFrame({
        "cost": settled[[f"{c}_obligations" for c in COMPONENTS]].sum(axis=1),
        "paid": settled["total_cash"],
    })
    balances = {}
    for name, components in groups.items():
        closing = sum((settled[f"{c}_closing"] for c in components), zero)
        first_movement = sum(settled[f"{c}_obligations"].iloc[0] - settled[f"{c}_cash"].iloc[0] for c in components)
        balances[name] = (float(closing.iloc[0] - first_movement), closing)
    return costs, balances


@dataclass(frozen=True)
class _GstLayer:
    sales_rate: float
    purchases_rate: float
    cash: pd.Series
    payable: pd.Series


def _gst_layer(gst: GstAssumptions, forecast: pd.DataFrame, wc: pd.DataFrame, opening: OpeningBalances) -> _GstLayer:
    """Net GST accrued by month, the GST cash it moves and the balance owed until each BAS is paid."""
    rate = gst.resolved_rate()
    sales_rate, purchases_rate = rate * gst.taxable_sales_pct, rate * gst.creditable_purchases_pct
    stock = wc["purchases"] if "purchases" in wc else forecast["cogs"] + wc["d_inventory"]
    accrued = monthly_gst(forecast["revenue"], stock + forecast["opex"] + forecast["capex"], gst)
    net = accrued["net_gst"]
    if opening.gst_payable:
        # The opening balance joins the BAS period of the month before the start.
        before = pd.Series([opening.gst_payable], index=pd.PeriodIndex([net.index[0] - 1], freq="M"))
        net = pd.concat([before, net])
    schedule = bas_schedule(net, gst)
    due = pd.PeriodIndex([pd.Period(day, freq="M") for day in schedule["due_date"]], freq="M")
    bas_paid = schedule["amount"].astype(float).groupby(due).sum().reindex(forecast.index, fill_value=0.0)
    cash = (accrued["output_gst"] - _movement(wc["ar"] * sales_rate, opening.ar * sales_rate)
            - accrued["input_gst"] + _movement(wc["ap"] * purchases_rate, opening.ap * purchases_rate)
            - bas_paid)
    return _GstLayer(sales_rate, purchases_rate, cash, opening.gst_payable + (accrued["net_gst"] - bas_paid).cumsum())


def _balance_sheet(
    assets: dict[str, tuple[float, pd.Series]],
    liabilities: dict[str, tuple[float, pd.Series]],
    net_income: pd.Series,
) -> pd.DataFrame:
    """Opening and closing balances, with equity rolled by net income and the balance check."""
    sheet = pd.DataFrame({name: _opening_and_closing(*pair) for name, pair in (assets | liabilities).items()})
    sheet["total_assets"] = sheet[list(assets)].sum(axis=1)
    sheet["total_liabilities"] = sheet[list(liabilities)].sum(axis=1)
    opening_equity = float(sheet["total_assets"].iloc[0] - sheet["total_liabilities"].iloc[0])
    sheet["equity"] = _opening_and_closing(opening_equity, opening_equity + net_income.cumsum())
    sheet["check_balance"] = sheet["total_assets"] - sheet["total_liabilities"] - sheet["equity"]
    return sheet


def _cash_flow(forecast: pd.DataFrame, payroll: pd.DataFrame | None, gst_cash: pd.Series,
               opening_cash: float) -> pd.DataFrame:
    """The cash flow statement: the forecast's operating cash plus GST, then capex and debt repaid."""
    zero = pd.Series(0.0, index=forecast.index)
    operating = forecast["operating_cash_flow"] + gst_cash
    closing_cash = forecast["ending_cash"] + gst_cash.cumsum()
    return pd.DataFrame({
        "net_income": forecast["net_income"],
        "da": forecast["da"],
        "working_capital": forecast["wc_cash_impact"],
        "payroll_unpaid": zero if payroll is None else payroll["cost"] - payroll["paid"],
        "income_tax_unpaid": forecast["tax"] - forecast["tax_paid"] if "tax_paid" in forecast else zero,
        "gst": gst_cash,
        "operating_cash_flow": operating,
        "capex": -forecast["capex"],
        "debt_repaid": -forecast["principal"],
        "change_in_cash": operating - forecast["capex"] - forecast["principal"],
        "opening_cash": closing_cash.shift(1, fill_value=opening_cash),
        "closing_cash": closing_cash,
    })


def three_way_from_config(
    cfg: EntityConfig,
    *,
    gst: GstAssumptions | None = None,
    payroll: Sequence[SettlementEvent] = (),
) -> ThreeWayForecast:
    """Profit and loss, balance sheet and cash flow by month from one configuration.

    Raises ValueError when GST is combined with bad debts, when an opening GST
    balance has no `gst`, when D&A would take fixed assets below nil, when a
    statement total is not finite, or for any error `cashflow_from_config` raises.
    """
    cfg = _validated_snapshot(cfg)
    if gst is not None and cfg.working_capital.bad_debt_share:
        raise ValueError("GST on bad debts is not modelled: give gst or bad_debt_share, not both")
    if gst is None and cfg.opening_balances.gst_payable:
        raise ValueError("opening_balances.gst_payable needs gst: without it no BAS settles the balance")
    months = month_index(cfg.start_month, cfg.horizon_months)
    zero = pd.Series(0.0, index=months)
    opening = cfg.opening_balances
    costs, payroll_balances = _payroll_layer(payroll, months)
    forecast, wc, debt = _compose(cfg, costs)
    gst_part = _GstLayer(0.0, 0.0, zero, zero) if gst is None else _gst_layer(gst, forecast, wc, opening)

    cash_flow = _cash_flow(forecast, costs, gst_part.cash, opening.cash)
    closing_cash = cash_flow["closing_cash"]
    tax_unpaid = cash_flow["income_tax_unpaid"]

    fixed_assets = opening.fixed_assets + (forecast["capex"] - forecast["da"]).cumsum()
    short = fixed_assets[fixed_assets < -_NEGATIVE_BALANCE_TOLERANCE]
    if len(short):
        raise ValueError(f"D&A takes fixed assets below nil in {short.index[0]}: "
                         "set opening_balances.fixed_assets to the book value it depreciates")
    assets = {
        "cash": (opening.cash, closing_cash),
        "receivables": (opening.ar * (1 + gst_part.sales_rate), wc["ar"] * (1 + gst_part.sales_rate)),
        "inventory": (opening.inventory, wc["inventory"]),
        "fixed_assets": (opening.fixed_assets, fixed_assets),
    }
    liabilities = {
        "payables": (opening.ap * (1 + gst_part.purchases_rate), wc["ap"] * (1 + gst_part.purchases_rate)),
        "gst_payable": (opening.gst_payable, gst_part.payable),
        **payroll_balances,
        "income_tax_payable": (opening.income_tax_payable, opening.income_tax_payable + tax_unpaid.cumsum()),
        "debt": (sum(item.opening_balance for item in cfg.debt), debt["ending_debt"]),
    }
    sheet = _balance_sheet(assets, liabilities, forecast["net_income"])
    _require_finite_columns(sheet, sheet.columns)
    _require_finite_columns(cash_flow, cash_flow.columns)

    pnl_columns = ["revenue", "cogs", "gross_profit", "opex", "bad_debts", "payroll", "ebitda",
                   "da", "interest", "pretax_income", "tax", "net_income"]
    profit_and_loss = forecast[[column for column in pnl_columns if column in forecast]]
    return ThreeWayForecast(profit_and_loss.copy(), sheet, cash_flow)
