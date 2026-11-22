# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Individual and trust income tax on its payment date.

Dates are from individual_trust_tax.yaml, which cites the ATO pages and
ITAA 1997 s 5-5; weekdays are worked out by hand beside each case.
"""

from datetime import date

import pytest

from pyfpa.au import (
    IndividualTrustTaxCategory,
    individual_trust_lodgment_due_date,
    individual_trust_tax_due_date,
    individual_trust_tax_schedule,
)
from pyfpa.au.individual_trust_tax import individual_trust_tax_nominal_due_date
from pyfpa.au.payg_instalments import payments_by_month
from pyfpa.au.rates import load_individual_trust_tax_data

Category = IndividualTrustTaxCategory


@pytest.mark.parametrize(("category", "return_day", "nominal", "due"), [
    # Saturday 21 November 2026 moves to Monday 23 November.
    ("self_lodger", date(2026, 10, 31), date(2026, 11, 21), date(2026, 11, 23)),
    ("prior_return_outstanding", date(2026, 10, 31), date(2026, 11, 21), date(2026, 11, 23)),
    # Sunday 21 February 2027 moves to Monday 22 February.
    ("large_medium_trust_taxable", date(2027, 1, 31), date(2027, 2, 21), date(2027, 2, 22)),
    # Sunday 21 March 2027 moves to Monday 22 March.
    ("large_medium_trust_not_taxable", date(2027, 2, 28), date(2027, 3, 21), date(2027, 3, 22)),
    ("new_registrant_large_medium_trust", date(2027, 2, 28), date(2027, 3, 21), date(2027, 3, 22)),
    # Wednesday 21 April 2027.
    ("liability_20000_or_more", date(2027, 3, 31), date(2027, 4, 21), date(2027, 4, 21)),
])
def test_a_return_not_due_15_may_pays_21_days_after_its_lodgment_due_date(category, return_day, nominal, due):
    assert individual_trust_lodgment_due_date(2026, category) == return_day
    lodged_on = date(2026, 8, 1)
    assert individual_trust_tax_nominal_due_date(2026, category, lodged_on) == nominal
    assert individual_trust_tax_due_date(2026, Category(category), lodged_on) == due
    assert individual_trust_tax_schedule(2026, 900.0, category, lodged_on).to_dict("records") == [
        {"period_label": "2025-26", "nominal_due_date": nominal, "due_date": due, "amount": 900.0}]


def test_a_notice_given_after_the_lodgment_due_date_moves_payment_to_21_days_after_it():
    # Lodged on time on 30 October 2026; notice given Friday 6 November, so due Friday 27 November.
    assert individual_trust_tax_due_date(2026, Category.SELF_LODGER, date(2026, 10, 30),
                                         notice_given_on=date(2026, 11, 6)) == date(2026, 11, 27)


@pytest.mark.parametrize("lodged_on", [
    # On the return day itself, Saturday 31 October 2026.
    date(2026, 10, 31),
    # On Monday 2 November, the first business day after it (TAA 1953 Sch 1 s 388-52).
    date(2026, 11, 2),
])
def test_a_return_lodged_by_the_rolled_lodgment_due_date_is_on_time(lodged_on):
    # Notice given Monday 9 November, so due Monday 30 November.
    assert individual_trust_tax_due_date(2026, Category.SELF_LODGER, lodged_on,
                                         notice_given_on=date(2026, 11, 9)) == date(2026, 11, 30)


def test_a_return_lodged_after_the_rolled_lodgment_due_date_is_late():
    # Tuesday 3 November 2026 is late, so 21 November, a Saturday, moves to Monday 23 November.
    assert individual_trust_tax_due_date(2026, Category.SELF_LODGER, date(2026, 11, 3),
                                         notice_given_on=date(2026, 11, 9)) == date(2026, 11, 23)


def test_a_notice_given_before_the_lodgment_due_date_leaves_21_days_after_that_date():
    assert individual_trust_tax_nominal_due_date(2026, Category.SELF_LODGER, date(2026, 8, 1),
                                                 notice_given_on=date(2026, 8, 20)) == date(2026, 11, 21)


def test_a_late_return_pays_21_days_after_the_lodgment_due_date_whenever_the_notice_comes():
    assert individual_trust_tax_nominal_due_date(2026, Category.LIABILITY_20000_OR_MORE, date(2027, 5, 1),
                                                 notice_given_on=date(2027, 5, 20)) == date(2027, 4, 21)


@pytest.mark.parametrize(("lodged_on", "nominal", "due"), [
    # Sunday 21 March 2027 moves to Monday 22 March.
    (date(2026, 7, 15), date(2027, 3, 21), date(2027, 3, 22)),
    (date(2027, 2, 12), date(2027, 3, 21), date(2027, 3, 22)),
    # Wednesday 21 April 2027.
    (date(2027, 2, 13), date(2027, 4, 21), date(2027, 4, 21)),
    (date(2027, 3, 12), date(2027, 4, 21), date(2027, 4, 21)),
    # Saturday 5 June 2027, then Monday 7 June, Western Australia Day: Tuesday 8 June.
    (date(2027, 3, 13), date(2027, 6, 5), date(2027, 6, 8)),
    (date(2027, 6, 5), date(2027, 6, 5), date(2027, 6, 8)),
])
def test_a_return_due_15_may_pays_on_the_staggered_date_for_when_it_is_lodged(lodged_on, nominal, due):
    assert individual_trust_lodgment_due_date(2026, Category.DUE_15_MAY) == date(2027, 5, 15)
    assert individual_trust_tax_nominal_due_date(2026, "due_15_may", lodged_on) == nominal
    assert individual_trust_tax_due_date(2026, Category.DUE_15_MAY, lodged_on) == due


def test_a_return_due_15_may_lodged_after_5_june_is_refused():
    with pytest.raises(ValueError, match="lodged after 05 June 2027, the concession date, has no payment date"):
        individual_trust_tax_due_date(2026, Category.DUE_15_MAY, date(2027, 6, 6))


def test_a_notice_date_for_a_return_due_15_may_is_refused():
    with pytest.raises(ValueError, match="a notice of assessment sets any later date"):
        individual_trust_tax_due_date(2026, Category.DUE_15_MAY, date(2027, 1, 10), notice_given_on=date(2027, 4, 1))


def test_the_recorded_rows_are_the_categories_in_their_order_of_precedence():
    data = load_individual_trust_tax_data()
    assert list(data["lodgment_due"][2026]) == [category.value for category in Category]
    assert list(data["staggered_payment_15_may"]) == list(data["lodgment_due"])


@pytest.mark.parametrize("category", [Category.SELF_LODGER, Category.DUE_15_MAY])
def test_an_income_year_without_recorded_dates_is_refused(category):
    with pytest.raises(ValueError, match="30 June 2027; individual_trust_tax.yaml covers \\[2026\\]"):
        individual_trust_tax_due_date(2027, category, date(2027, 8, 1))


@pytest.mark.parametrize("amount", [-1.0, float("nan"), float("inf")])
def test_a_refund_or_a_non_finite_amount_is_refused(amount):
    with pytest.raises(ValueError, match="a refund has no due date"):
        individual_trust_tax_schedule(2026, amount, Category.SELF_LODGER, date(2026, 8, 1))


def test_payments_by_month_puts_the_payment_in_its_month():
    schedule = individual_trust_tax_schedule(2026, 4200.0, Category.DUE_15_MAY, date(2027, 3, 1))
    assert payments_by_month(schedule)["2027-04"] == pytest.approx(4200.0)
