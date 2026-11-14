# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Xero budgets read from the Accounting API.

Reads 2 saved JSON responses, GET /Budgets/{BudgetID} and GET /Accounts, into
one ``XeroReport`` per budget month, so the checks the pack applies to report
exports (``by_account``, ``account_identities``, ``detect_gst_inclusive`` and
``openfpa reconcile-source`` on the account totals) apply to a budget unchanged.

The input shape is the one Xero publishes: the Budgets, Accounts and Types and
Codes pages at developer.xero.com/documentation/api/accounting/ and the Budget,
BudgetLine and BudgetBalance schemas in Xero's OpenAPI file xero_accounting.yaml
(version 20.1.0), all read on 15 November 2026. This reader has not been run
against a live organisation; docs/recipes/xero-au.md lists what a demo-company
check must still confirm.

A budget line carries an AccountID and AccountCode but no account name or
type, so the chart of accounts supplies both. Refused rather than guessed:
a list response (lines come back only for a single budget), a line on an
account the chart lacks or on a balance-sheet or unknown account type, a code
that disagrees with the chart, lines that do not cover the same unbroken run
of months, a repeated month or account, an amount that is not a plain number,
and a balance carrying ``UnitAmount``: the Budgets page describes ``Amount`` as
"LineItem Quantity" and ``UnitAmount`` as "Budgeted amount", yet both published
examples carry the budget in ``Amount`` alone, so a balance with both is
ambiguous.

This module holds no credentials and makes no network call.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyfpa.io.xero_au import XeroReport, XeroRow, detect_gst_inclusive

# Account types from developer.xero.com/documentation/api/accounting/types.
_INCOME_TYPES = {"REVENUE", "SALES", "OTHERINCOME"}
_EXPENSE_TYPES = {"EXPENSE", "DIRECTCOSTS", "OVERHEADS", "DEPRECIATN"}
_BALANCE_SHEET_TYPES = {
    "BANK", "CURRENT", "CURRLIAB", "EQUITY", "FIXED", "INVENTORY",
    "LIABILITY", "NONCURRENT", "PREPAYMENT", "TERMLIAB",
}
_PERIOD = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class XeroBudget:
    budget_id: str
    description: str
    budget_type: str
    periods: tuple[str, ...]
    reports: dict[str, XeroReport]

    def gst_inclusive(self, controls: Mapping[str, float]) -> bool | None:
        """GST basis of the budget's revenue against GST-exclusive monthly controls.

        Runs ``detect_gst_inclusive`` on each month that has a control. True
        when any month reads inclusive, False only when every budget month has
        a control and reads exclusive, otherwise None (undetermined). A budget
        whose months disagree is refused: a mixed basis cannot feed
        ``pyfpa.au.monthly_gst``.
        """
        unknown = sorted(set(controls) - set(self.periods))
        if unknown:
            raise ValueError(f"controls name months outside the budget: {unknown}")
        results = {
            period: detect_gst_inclusive(self.reports[period], control_total=total)
            for period, total in controls.items()
        }
        found = set(results.values())
        if {True, False} <= found:
            raise ValueError(f"mixed GST basis across budget months: {dict(sorted(results.items()))}")
        if True in found:
            return True
        if set(results) == set(self.periods) and found == {False}:
            return False
        return None


def _load(path: str | Path, key: str) -> Any:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or key not in payload:
        raise ValueError(f"expected a Xero API response holding {key!r} in {path}")
    return payload[key]


def _objects(value: object, what: str) -> list[dict[str, Any]]:
    """`value` as a list of JSON objects; a missing element reads as empty."""
    items = [] if value is None else value
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError(f"expected {what} to be a list of objects")
    return items


def _amount(balance: Mapping[str, Any]) -> float:
    if "UnitAmount" in balance:
        raise ValueError(
            "budget balance carries UnitAmount as well as Amount; "
            "Xero's documentation does not settle which is the budgeted amount"
        )
    raw = balance.get("Amount")
    if isinstance(raw, str) and _PLAIN_NUMBER.fullmatch(raw):
        return float(raw)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw):
        return float(raw)
    raise ValueError(f"budget amount {raw!r} is not a plain finite number")


def _period(raw: object) -> str:
    if isinstance(raw, str) and _PERIOD.fullmatch(raw):
        return raw
    raise ValueError(f"budget period {raw!r} is not YYYY-MM")


def _month_number(period: str) -> int:
    year, month = period.split("-")
    return int(year) * 12 + int(month)


def _chart(accounts: object) -> dict[str, dict[str, Any]]:
    chart: dict[str, dict[str, Any]] = {}
    for account in _objects(accounts, "Accounts"):
        account_id = account.get("AccountID")
        if not isinstance(account_id, str):
            raise ValueError(f"chart account without an AccountID: {account.get('Name')!r}")
        if account_id in chart:
            raise ValueError(f"chart lists account {account_id} more than once")
        chart[account_id] = account
    return chart


def _tracking_label(budget: Mapping[str, Any]) -> str:
    pairs = [(t.get("Name"), t.get("Option")) for t in _objects(budget.get("Tracking"), "Tracking")]
    if not all(isinstance(v, str) and v.strip() for pair in pairs for v in pair):
        raise ValueError("budget tracking needs a category name and option for each entry")
    labels = [f"{name}: {option}" for name, option in pairs]
    if (budget["Type"] == "TRACKING") != bool(labels):
        raise ValueError("a TRACKING budget needs tracking options and an OVERALL budget has none")
    return "; ".join(labels)


def _account(line: Mapping[str, Any], chart: Mapping[str, dict[str, Any]]) -> tuple[str, str, str, float]:
    """AccountID, code, name and sign of a budget line's account, from the chart."""
    account_id = line.get("AccountID")
    account = chart.get(account_id) if isinstance(account_id, str) else None
    if account is None:
        raise ValueError(f"budget account {account_id!r} is not in the chart of accounts")
    code = account.get("Code") or ""
    if "AccountCode" in line and line["AccountCode"] != code:
        raise ValueError(f"budget code {line['AccountCode']!r} differs from the chart's {code!r}")
    name = account.get("Name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"chart account {account_id} has no name")
    kind = account.get("Type")
    if kind in _BALANCE_SHEET_TYPES:
        raise ValueError(f"budget line on balance-sheet account {name!r} ({kind}); "
                         "this reader takes profit and loss budgets only")
    if kind not in _INCOME_TYPES | _EXPENSE_TYPES:
        raise ValueError(f"unknown account type {kind!r} for {name!r}")
    return account_id, code, name, 1.0 if kind in _INCOME_TYPES else -1.0


def _balances(line: Mapping[str, Any], name: str) -> dict[str, float]:
    balances: dict[str, float] = {}
    for balance in _objects(line.get("BudgetBalances"), "BudgetBalances"):
        period = _period(balance.get("Period"))
        if period in balances:
            raise ValueError(f"budget line for {name!r} repeats period {period}")
        balances[period] = _amount(balance)
    if not balances:
        raise ValueError(f"budget line for {name!r} has missing periods: none given")
    return balances


def read_xero_budget(budget_path: str | Path, accounts_path: str | Path) -> XeroBudget:
    """Read a single-budget response and the chart of accounts into monthly reports.

    Amounts are taken as natural balances, as both published examples show
    (a sales line and an expense line, both positive), and expense lines are
    negated to the convention ``read_xero_report`` uses: income positive,
    expenses negative. Whether a live budget returns expenses positive is
    unconfirmed; see docs/recipes/xero-au.md.
    """
    budget = _load(budget_path, "Budgets")
    if not isinstance(budget, dict):
        raise ValueError(
            "expected a single budget; budget lines come back only from GET /Budgets/{BudgetID}"
        )
    if budget.get("Type") not in {"OVERALL", "TRACKING"}:
        raise ValueError(f"unknown budget type {budget.get('Type')!r}")
    tracking = _tracking_label(budget)
    chart = _chart(_load(accounts_path, "Accounts"))
    lines = _objects(budget.get("BudgetLines"), "BudgetLines")
    if not lines:
        raise ValueError("no budget lines; request a single budget with GET /Budgets/{BudgetID}")

    rows: dict[str, list[XeroRow]] = {}
    names: dict[str, str] = {}
    expected: set[str] | None = None
    for line in lines:
        account_id, code, name, sign = _account(line, chart)
        if account_id in names.values():
            raise ValueError(f"budget lists account {account_id} more than once")
        if name in names:
            raise ValueError(f"accounts {names[name]} and {account_id} share the name {name!r}")
        names[name] = account_id
        balances = _balances(line, name)
        expected = set(balances) if expected is None else expected
        if set(balances) != expected:
            raise ValueError(f"budget line for {name!r} has missing periods: "
                             f"{sorted(expected ^ set(balances))}")
        for period, amount in balances.items():
            rows.setdefault(period, []).append(
                XeroRow(code=code, account=name, amount=sign * amount, tracking_option=tracking)
            )

    periods = tuple(sorted(rows))
    months = [_month_number(p) for p in periods]
    if months[-1] - months[0] + 1 != len(months):
        raise ValueError(f"budget has missing periods between {periods[0]} and {periods[-1]}")
    return XeroBudget(
        budget_id=str(budget.get("BudgetID") or ""),
        description=str(budget.get("Description") or ""),
        budget_type=budget["Type"],
        periods=periods,
        reports={p: XeroReport(rows=rows[p]) for p in periods},
    )
