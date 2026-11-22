# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""When a company pays its income tax for the year, so a 12-month forecast can hold the date.

The ATO's lodgment program sets the payment date for a 30 June balancing
company by its circumstances, in rows that apply in order: 1 December for a
company that must lodge by 31 October or was a taxable medium to large client in
the prior year, 28 February for other medium to large taxpayers and for any
other company preparing its own return, and later dates for a tax agent's other
clients. `company_tax.yaml` holds the dates for each income year it records,
with their sources; a date on a weekend or public holiday moves to the next
business day. The caller states the first `CompanyTaxCategory` that fits the
company, as the ATO decides that from records this code cannot see.

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
    """The lodgment program row a company falls in; the caller states it.

    Take the first row that fits, in this order: each later row applies only to
    a company that no earlier row covers, as the ATO's 'unless required earlier'
    and 'not due at an earlier date' say.
    """

    # Has a prior year return outstanding at 30 June, did not lodge last year's on
    # time, was prosecuted for non-lodgment or was asked to lodge early: 1 December.
    REQUIRED_BY_31_OCTOBER = "required_by_31_october"
    # A medium or large taxpayer whose return for the prior year was taxable,
    # lodging itself or through an agent: 1 December.
    LARGE_MEDIUM_TAXABLE_LAST_YEAR = "large_medium_taxable_last_year"
    # A medium or large taxpayer whose prior year return was non-taxable or not
    # necessary, or a new registrant medium or large taxpayer, taxable or not: 28 February.
    LARGE_MEDIUM_NOT_TAXABLE_LAST_YEAR = "large_medium_not_taxable_last_year"
    # A subsidiary member that left its consolidated group during the income year: 28 February.
    EXITED_CONSOLIDATED_GROUP = "exited_consolidated_group"
    # Lodging its own return and in none of the rows above: 28 February.
    SELF_PREPARING_OTHER = "self_preparing_other"
    # A tax agent's client with total income above $2 million in the year before
    # the prior year (2024-25 for the year to 30 June 2026): 31 March.
    AGENT_TOTAL_INCOME_OVER_2M = "agent_total_income_over_2m"
    # Every other tax agent client: 15 May.
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
