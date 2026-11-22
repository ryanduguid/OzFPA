# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Australian localisation pack for pyfpa.

Adds Australian fiscal-calendar helpers, effective-dated statutory rate
tables, payroll cost forecasting (super guarantee, state payroll tax,
workers compensation, leave provisions, bonuses) and GST/BAS cash-timing
for the monthly model and the 13-week cash forecast.

Scope: forecast-grade cash and P&L modelling. Not tax-return software.
Payroll tax grouping and per-state threshold apportionment are documented
simplifications. Contractor SG eligibility must be established by the caller.
"""

from pyfpa.au.calendar import (
    format_au_date,
    fy_half_label,
    fy_label,
    fy_month_range,
    fy_quarter_label,
    fy_summary,
    fy_year,
)
from pyfpa.au.company_tax import (
    CompanyTaxCategory,
    company_tax_due_date,
    company_tax_schedule,
)
from pyfpa.au.depreciation import (
    DepreciationEvidence,
    DepreciationEvidenceError,
    MovementCheck,
    asset_movement,
    cash_and_expense,
    load_evidence,
    straight_line_schedule,
)
from pyfpa.au.drivers import (
    DriverSeries,
    fetch_abs_series,
    fetch_rba_series,
    load_snapshot,
    save_snapshot,
)
from pyfpa.au.fbt import fbt_due_date, fbt_schedule, fbt_weekly_flows
from pyfpa.au.gst import (
    BasCycle,
    GstAssumptions,
    LodgmentChannel,
    bas_schedule,
    gst_weekly_flows,
    monthly_gst,
)
from pyfpa.au.payment_plan import (
    PaymentPlanEstimate,
    PlanFrequency,
    payment_plan_estimate,
    payment_plan_weekly_flows,
)
from pyfpa.au.payroll import PayrollAssumptions, Role, payroll_forecast
from pyfpa.au.rates import (
    load_gst_bas_data,
    load_payroll_tax_table,
    load_super_guarantee_table,
    rate_at,
)
from pyfpa.au.tax_report import tax_report

__all__ = [
    "BasCycle",
    "CompanyTaxCategory",
    "DepreciationEvidence",
    "DepreciationEvidenceError",
    "DriverSeries",
    "GstAssumptions",
    "LodgmentChannel",
    "MovementCheck",
    "PaymentPlanEstimate",
    "PayrollAssumptions",
    "PlanFrequency",
    "Role",
    "asset_movement",
    "bas_schedule",
    "cash_and_expense",
    "company_tax_due_date",
    "company_tax_schedule",
    "fbt_due_date",
    "fbt_schedule",
    "fbt_weekly_flows",
    "fetch_abs_series",
    "fetch_rba_series",
    "format_au_date",
    "fy_half_label",
    "fy_label",
    "fy_month_range",
    "fy_quarter_label",
    "fy_summary",
    "fy_year",
    "gst_weekly_flows",
    "load_evidence",
    "load_gst_bas_data",
    "load_payroll_tax_table",
    "load_snapshot",
    "load_super_guarantee_table",
    "monthly_gst",
    "payment_plan_estimate",
    "payment_plan_weekly_flows",
    "payroll_forecast",
    "rate_at",
    "save_snapshot",
    "straight_line_schedule",
    "tax_report",
]
