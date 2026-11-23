# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""When an individual or a trust pays its income tax for the year, so a 12-month forecast can hold the date.

An individual or trust is not a self-assessment entity, so its tax is due 21
days after the day its return must be lodged, or 21 days after the notice of
assessment when that is given later to a taxpayer who lodged on time (Income Tax
Assessment Act 1997 s 5-5(5) and (6)). The ATO's lodgment program sets the
lodgment due date by the taxpayer's circumstances, and staggers the payment of
returns due 15 May by when they are lodged. `individual_trust_tax.yaml` holds
the dates for each income year it records, with their sources; a date on a
weekend or public holiday moves to the next business day. The caller states the
first `IndividualTrustTaxCategory` that fits, as the ATO decides that from
records this code cannot see.

The income year is named by the 30 June it ends on, so 2026 is the year to
30 June 2026, whose tax is paid in 2026-27. `amount` is the tax left to pay
after PAYG instalments; a refund is refused, as for a company.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Any

import pandas as pd

from pyfpa.au.company_tax import income_tax_payment
from pyfpa.au.gst import _next_business_day
from pyfpa.au.rates import load_individual_trust_tax_data

_DAYS_TO_PAY = timedelta(days=21)


class IndividualTrustTaxCategory(str, Enum):
    """The lodgment program row an individual or trust falls in; the caller states it.

    Take the first row that fits, in this order, as the ATO's 'not required
    earlier' says. Every row after SELF_LODGER is a registered agent's client.
    """

    # Lodging its own return: 31 October.
    SELF_LODGER = "self_lodger"
    # One or more prior year returns outstanding at 30 June, or prosecuted for
    # non-lodgment and told to lodge by 31 October: 31 October.
    PRIOR_RETURN_OUTSTANDING = "prior_return_outstanding"
    # A trust with total income above $10 million in the latest year lodged,
    # taxable in that year: 31 January.
    LARGE_MEDIUM_TRUST_TAXABLE = "large_medium_trust_taxable"
    # The same, non-taxable in that year: 28 February.
    LARGE_MEDIUM_TRUST_NOT_TAXABLE = "large_medium_trust_not_taxable"
    # A newly registered large or medium trust: 28 February.
    NEW_REGISTRANT_LARGE_MEDIUM_TRUST = "new_registrant_large_medium_trust"
    # Latest return gave a tax liability of $20,000 or more: 31 March.
    LIABILITY_20000_OR_MORE = "liability_20000_or_more"
    # Every other agent client: 15 May, paid by when the return is lodged.
    DUE_15_MAY = "due_15_may"


def _recorded(income_year: int) -> dict[str, Any]:
    data = load_individual_trust_tax_data()
    if income_year not in data["lodgment_due"]:
        raise ValueError(f"no individual or trust tax date is recorded for the income year ending 30 June "
                         f"{income_year}; individual_trust_tax.yaml covers {sorted(data['lodgment_due'])}")
    return {key: rows[income_year] for key, rows in data.items()}


def individual_trust_lodgment_due_date(income_year: int, category: IndividualTrustTaxCategory | str) -> date:
    """The day the return for the income year ending 30 June `income_year` must be lodged."""
    due: dict[str, date] = _recorded(income_year)["lodgment_due"]
    return due[IndividualTrustTaxCategory(category).value]


def _staggered_payment_date(income_year: int, lodged_on: date, notice_given_on: date | None) -> date:
    if notice_given_on is not None:
        raise ValueError("a return due 15 May is paid on the ATO's staggered date, the latest unless processing "
                         "takes longer; a notice of assessment sets any later date, so enter that date in "
                         "income_tax.payments")
    rows: list[dict[str, date]] = _recorded(income_year)["staggered_payment_15_may"]
    for row in rows:
        if lodged_on <= row["lodged_by"]:
            return row["pay_on"]
    raise ValueError(f"a return due 15 May lodged after {rows[-1]['lodged_by']:%d %B %Y}, the concession date, "
                     f"has no payment date on the ATO's page; enter the date on its notice of assessment in "
                     f"income_tax.payments")


def individual_trust_tax_nominal_due_date(income_year: int, category: IndividualTrustTaxCategory | str,
                                          lodged_on: date, notice_given_on: date | None = None) -> date:
    """The date the tax is due for the income year ending 30 June `income_year`, before any roll.

    `lodged_on` is the day the return is (or is planned to be) lodged; a return
    lodged by the lodgment due date, or the next business day when that is not one,
    is on time.
    For a timely self-lodger, pass the assessment issue date as `notice_given_on`.
    For a timely registered-agent lodgment outside the 15 May schedule, the
    ATO program uses deemed receipt 7 business days after issue. Leave the
    date out when unknown and use the due date on the actual notice if available.
    """
    category = IndividualTrustTaxCategory(category)
    if category is IndividualTrustTaxCategory.DUE_15_MAY:
        return _staggered_payment_date(income_year, lodged_on, notice_given_on)
    return_day = individual_trust_lodgment_due_date(income_year, category)
    # A return due on a day that is not a business day may be lodged on the next
    # one (TAA 1953 Sch 1 s 388-52), so lodging then is on time.
    if notice_given_on is None or lodged_on > _next_business_day(return_day):
        return return_day + _DAYS_TO_PAY
    return max(return_day, notice_given_on) + _DAYS_TO_PAY


def individual_trust_tax_due_date(income_year: int, category: IndividualTrustTaxCategory | str,
                                  lodged_on: date, notice_given_on: date | None = None) -> date:
    """Effective date to pay the tax for the income year ending 30 June `income_year`."""
    return _next_business_day(
        individual_trust_tax_nominal_due_date(income_year, category, lodged_on, notice_given_on))


def individual_trust_tax_schedule(income_year: int, amount: float, category: IndividualTrustTaxCategory | str,
                                  lodged_on: date, notice_given_on: date | None = None) -> pd.DataFrame:
    """The year's payment: columns period_label, nominal_due_date, due_date, amount.

    `payments_by_month` turns it, alone or with `payg_instalment_schedule`'s rows,
    into `income_tax.payments`.
    """
    nominal = individual_trust_tax_nominal_due_date(income_year, category, lodged_on, notice_given_on)
    return income_tax_payment(income_year, amount, nominal)
