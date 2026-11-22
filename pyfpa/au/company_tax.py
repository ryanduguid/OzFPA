# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""When a company pays its income tax for the year, so a 12-month forecast can hold the date.

The ATO's lodgment program sets the payment date for a 30 June balancing
company by its circumstances: 1 December for a company that was a taxable
medium to large client in the prior year or must lodge by 31 October, 28
February for a company preparing its own return, and later dates for a tax
agent's clients. `company_tax.yaml` holds the dates for each income year it
records, with their sources; a date on a weekend or public holiday moves to the
next business day. The caller states which `CompanyTaxCategory` the company
falls in, as the ATO decides that from records this code cannot see.

The income year is named by the 30 June it ends on, so 2026 is the year to
30 June 2026, whose tax is paid in 2026-27. `amount` is the tax left to pay
after PAYG instalments. A refund has no due date, so a negative amount is
refused: enter it in `income_tax.payments` in the month you expect it.
"""

from __future__ import annotations

import math
from datetime import date
from enum import Enum

import pandas as pd

from pyfpa.au.gst import _next_business_day
from pyfpa.au.rates import load_company_tax_data


class CompanyTaxCategory(str, Enum):
    """The lodgment program row a company falls in; the caller states it."""

    REQUIRED_BY_31_OCTOBER = "required_by_31_october"
    LARGE_MEDIUM_TAXABLE = "large_medium_taxable"
    SELF_PREPARING = "self_preparing"
    AGENT_LARGE_MEDIUM_NON_TAXABLE = "agent_large_medium_non_taxable"
    AGENT_TOTAL_INCOME_OVER_2M = "agent_total_income_over_2m"
    AGENT_OTHER = "agent_other"


def company_tax_nominal_due_date(income_year: int, category: CompanyTaxCategory | str) -> date:
    """The date the ATO gives for the income year ending 30 June `income_year`, before any roll."""
    category = CompanyTaxCategory(category)
    recorded: dict[int, dict[str, date]] = load_company_tax_data()["payment_due"]
    if income_year not in recorded:
        raise ValueError(f"no company tax payment date is recorded for the income year ending 30 June "
                         f"{income_year}; company_tax.yaml covers {sorted(recorded)}")
    return recorded[income_year][category.value]


def company_tax_due_date(income_year: int, category: CompanyTaxCategory | str) -> date:
    """Effective date to pay the company tax for the income year ending 30 June `income_year`."""
    return _next_business_day(company_tax_nominal_due_date(income_year, category))


def company_tax_schedule(income_year: int, amount: float, category: CompanyTaxCategory | str) -> pd.DataFrame:
    """The year's payment: columns period_label, nominal_due_date, due_date, amount.

    `payments_by_month` turns it, alone or with `payg_instalment_schedule`'s rows,
    into `income_tax.payments`; `tax_report` lists it.
    """
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("the company tax amount must be a finite number of at least 0: a refund has no due "
                         "date, so enter it in income_tax.payments in the month you expect it")
    return pd.DataFrame([{
        "period_label": f"{income_year - 1}-{income_year % 100:02d}",
        "nominal_due_date": company_tax_nominal_due_date(income_year, category),
        "due_date": company_tax_due_date(income_year, category),
        "amount": float(amount),
    }])
