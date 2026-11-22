# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Company income tax on its payment date, in a 12-month forecast.

Dates are from company_tax.yaml, which cites the ATO pages; weekdays are worked
out by hand beside each case.
"""

from datetime import date

import pandas as pd
import pytest

from pyfpa import three_way_from_config
from pyfpa.au import (
    CompanyTaxCategory,
    company_tax_due_date,
    company_tax_schedule,
    tax_report,
)
from pyfpa.au.company_tax import company_tax_nominal_due_date
from pyfpa.au.payg_instalments import payg_instalment_schedule, payments_by_month
from pyfpa.au.rates import load_company_tax_data
from pyfpa.config.schemas import (
    Channel,
    EntityConfig,
    IncomeTaxConfig,
    OpeningBalances,
    WorkingCapitalConfig,
)
from pyfpa.models.cashflow import cashflow_from_config


@pytest.mark.parametrize(("category", "nominal", "due"), [
    # Tuesday 1 December 2026.
    ("required_by_31_october", date(2026, 12, 1), date(2026, 12, 1)),
    ("large_medium_taxable_last_year", date(2026, 12, 1), date(2026, 12, 1)),
    # Sunday 28 February 2027, then Monday 1 March, Labour Day in WA: Tuesday 2 March.
    ("self_preparing_other", date(2027, 2, 28), date(2027, 3, 2)),
    ("large_medium_not_taxable_last_year", date(2027, 2, 28), date(2027, 3, 2)),
    # Wednesday 31 March 2027.
    ("agent_total_income_over_2m", date(2027, 3, 31), date(2027, 3, 31)),
    # Saturday 15 May 2027 moves to Monday 17 May.
    ("agent_other", date(2027, 5, 15), date(2027, 5, 17)),
])
def test_each_lodgment_program_row_has_its_date(category, nominal, due):
    assert company_tax_nominal_due_date(2026, category) == nominal
    assert company_tax_due_date(2026, CompanyTaxCategory(category)) == due
    schedule = company_tax_schedule(2026, 5000.0, category)
    assert schedule.to_dict("records") == [
        {"period_label": "2025-26", "nominal_due_date": nominal, "due_date": due, "amount": 5000.0}]


def test_the_recorded_rows_are_the_categories_in_their_order_of_precedence():
    assert list(load_company_tax_data()["payment_due"][2026]) == [category.value for category in CompanyTaxCategory]


def test_an_income_year_without_recorded_dates_is_refused():
    with pytest.raises(ValueError, match="income year ending 30 June 2027; company_tax.yaml covers \\[2026\\]"):
        company_tax_due_date(2027, CompanyTaxCategory.SELF_PREPARING_OTHER)


@pytest.mark.parametrize("amount", [-1.0, float("nan"), float("inf")])
def test_a_refund_or_a_non_finite_amount_is_refused(amount):
    with pytest.raises(ValueError, match="a refund has no due date"):
        company_tax_schedule(2026, amount, CompanyTaxCategory.SELF_PREPARING_OTHER)


def test_a_12_month_forecast_pays_last_years_tax_on_its_date_with_the_instalments():
    owed = 18000.0
    cfg = EntityConfig(
        name="Twelve Month Co", start_month="2026-07", horizon_months=12, tax_rate=0.25,
        channels=[Channel(name="Shop", annual_revenue=600000.0, seasonality=[1.0] * 12, cogs_pct=0.4)],
        working_capital=WorkingCapitalConfig(dso_days=30, dpo_days=30, dio_days=0),
        opening_balances=OpeningBalances(cash=50000.0, income_tax_payable=owed),
        income_tax=IncomeTaxConfig(forecast_losses_deductible=False))
    income = cashflow_from_config(cfg)["revenue"]
    instalments = payg_instalment_schedule(income, deferred_bas_payer=True, rate=0.02)
    # The June quarter's instalment falls due in July 2027, after the forecast.
    instalments = instalments[instalments["due_date"] < date(2027, 7, 1)]
    company_tax = company_tax_schedule(2026, owed, CompanyTaxCategory.SELF_PREPARING_OTHER)
    payments = payments_by_month(pd.concat([instalments, company_tax]))
    cfg = cfg.model_copy(update={"income_tax": IncomeTaxConfig(forecast_losses_deductible=False, payments=payments)})

    result = three_way_from_config(cfg)
    payable = result.balance_sheet["income_tax_payable"]
    assert result.balance_sheet["check_balance"].abs().max() == pytest.approx(0.0, abs=1e-6)
    # Paid on Tuesday 2 March 2027 with the December quarter's instalment.
    december_quarter = instalments.loc[instalments["due_date"] == date(2027, 3, 2), "amount"].sum()
    assert december_quarter > 0
    assert payments["2027-03"] == pytest.approx(owed + december_quarter)
    tax = result.profit_and_loss["tax"]
    february, march = pd.Period("2027-02", freq="M"), pd.Period("2027-03", freq="M")
    assert payable[march] - payable[february] == pytest.approx(tax[march] - owed - december_quarter)
    report = tax_report(payg_instalments=instalments, company_tax=company_tax)
    assert report.loc[report["obligation"] == "Company income tax", ["due_date", "period", "amount"]].values.tolist() \
        == [[date(2027, 3, 2), "2025-26", owed]]
