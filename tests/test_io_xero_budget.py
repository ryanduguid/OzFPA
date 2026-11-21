# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from pyfpa.au.gst import bas_schedule, monthly_gst
from pyfpa.io.xero_budget import read_xero_budget

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BUDGET = FIXTURES / "xero_budget_documented.json"
ACCOUNTS = FIXTURES / "xero_accounts_documented.json"


def _read_with(tmp_path: Path, change: Callable[[dict[str, Any], dict[str, Any]], None]) -> None:
    """Apply `change` to copies of both fixtures, then read them."""
    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    accounts = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    change(budget, accounts)
    budget_path = tmp_path / "budget.json"
    accounts_path = tmp_path / "accounts.json"
    budget_path.write_text(json.dumps(budget), encoding="utf-8")
    accounts_path.write_text(json.dumps(accounts), encoding="utf-8")
    read_xero_budget(budget_path, accounts_path)


def _lines(budget: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = budget["Budgets"]["BudgetLines"]
    return lines


def test_documented_example_becomes_one_report_per_month() -> None:
    budget = read_xero_budget(BUDGET, ACCOUNTS)
    assert budget.budget_id == "c1d195d4-92aa-4abd-867a-7ac2f9d60500"
    assert budget.budget_type == "TRACKING"
    assert budget.periods == ("2019-08", "2019-09", "2019-10")
    # Expense lines come out negative, the convention read_xero_report uses.
    assert budget.reports["2019-08"].by_account() == {"Sales": 1000.0, "Entertainment": -500.0}
    assert budget.reports["2019-10"].by_account() == {"Sales": 1102.0, "Entertainment": -510.0}
    identities = budget.reports["2019-09"].account_identities()
    assert [(i.code, i.name) for i in identities] == [("200", "Sales"), ("420", "Entertainment")]
    assert budget.reports["2019-09"].by_tracking() == {
        "Region: North; Salesperson: Daniel": {"Sales": 1050.0, "Entertainment": -505.0}
    }


def test_numeric_amounts_as_the_openapi_schema_types_them(tmp_path: Path) -> None:
    def numbers(budget: dict[str, Any], _accounts: dict[str, Any]) -> None:
        for line in _lines(budget):
            for balance in line["BudgetBalances"]:
                balance["Amount"] = float(balance["Amount"]) + 0.25

    _read_with(tmp_path, numbers)


def test_single_budget_as_the_openapi_schema_types_the_response(tmp_path: Path) -> None:
    # Xero's OpenAPI gives GET /Budgets/{BudgetID} the Budgets schema, a list of
    # budgets, whilst both published examples show one object.
    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    budget["Budgets"] = [budget["Budgets"]]
    path = tmp_path / "listed.json"
    path.write_text(json.dumps(budget), encoding="utf-8")
    assert read_xero_budget(path, ACCOUNTS) == read_xero_budget(BUDGET, ACCOUNTS)


def test_repeated_json_key_is_refused(tmp_path: Path) -> None:
    # json keeps only the last of repeated keys, so the second Amount would replace the first.
    text = BUDGET.read_text(encoding="utf-8")
    once = '{"Period": "2019-08", "Amount": "1000"}'
    assert text.count(once) == 1
    path = tmp_path / "repeated.json"
    path.write_text(text.replace(once, '{"Period": "2019-08", "Amount": "1000", "Amount": "9000"}'), encoding="utf-8")
    with pytest.raises(ValueError, match=r"repeats \['Amount'\]"):
        read_xero_budget(path, ACCOUNTS)


def test_overall_budget_is_untracked(tmp_path: Path) -> None:
    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    budget["Budgets"]["Type"] = "OVERALL"
    del budget["Budgets"]["Tracking"]
    path = tmp_path / "overall.json"
    path.write_text(json.dumps(budget), encoding="utf-8")
    report = read_xero_budget(path, ACCOUNTS).reports["2019-08"]
    assert set(report.by_tracking()) == {"(untracked)"}


def test_budget_feeds_monthly_gst_and_the_bas_schedule(tmp_path: Path) -> None:
    budget = json.loads(BUDGET.read_text(encoding="utf-8"))
    for line in _lines(budget):
        for balance, month in zip(line["BudgetBalances"], ("2026-07", "2026-08", "2026-09"), strict=True):
            balance["Period"] = month
    path = tmp_path / "fy2027.json"
    path.write_text(json.dumps(budget), encoding="utf-8")
    read = read_xero_budget(path, ACCOUNTS)
    months = pd.PeriodIndex(read.periods, freq="M")
    revenue = pd.Series([read.reports[p].by_account()["Sales"] for p in read.periods], index=months)
    purchases = pd.Series([-read.reports[p].by_account()["Entertainment"] for p in read.periods], index=months)
    schedule = bas_schedule(monthly_gst(revenue, purchases)["net_gst"])
    assert list(schedule["period_label"]) == ["2027Q1"]
    assert schedule["due_date"].iloc[0] == date(2026, 10, 28)
    assert schedule["amount"].iloc[0] == pytest.approx((3152 - 1515) * 0.1)


def test_gst_basis_from_controls() -> None:
    budget = read_xero_budget(BUDGET, ACCOUNTS)
    exclusive = {"2019-08": 1000.0, "2019-09": 1050.0, "2019-10": 1102.0}
    assert budget.gst_inclusive(exclusive) is False
    assert budget.gst_inclusive({p: v / 1.1 for p, v in exclusive.items()}) is True
    # A month without a control leaves the basis undetermined.
    assert budget.gst_inclusive({"2019-08": 1000.0, "2019-09": 1050.0}) is None
    assert budget.gst_inclusive({}) is None
    # Inclusive evidence in one month is reported even when others are uncontrolled.
    assert budget.gst_inclusive({"2019-08": 1000.0 / 1.1}) is True


def test_mixed_gst_basis_is_refused() -> None:
    budget = read_xero_budget(BUDGET, ACCOUNTS)
    with pytest.raises(ValueError, match="mixed GST basis"):
        budget.gst_inclusive({"2019-08": 1000.0, "2019-09": 1050.0 / 1.1})


def test_control_for_a_month_outside_the_budget_is_refused() -> None:
    budget = read_xero_budget(BUDGET, ACCOUNTS)
    with pytest.raises(ValueError, match="2019-11"):
        budget.gst_inclusive({"2019-11": 1000.0})


def _drop_one_month(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[1]["BudgetBalances"].pop()


def _gap(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    for line in _lines(budget):
        line["BudgetBalances"].pop(1)


def _repeat_month(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["BudgetBalances"][1]["Period"] = "2019-08"


def _no_balances(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["BudgetBalances"] = []


def _month_name(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["BudgetBalances"][0]["Period"] = "Aug-2019"


def _month_13(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["BudgetBalances"][0]["Period"] = "2019-13"


def _period_in_other_digits(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["BudgetBalances"][0]["Period"] = "٢٠١٩-08"


def _unit_amount(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["BudgetBalances"][0]["UnitAmount"] = "1000"


def _amount(value: object) -> Callable[[dict[str, Any], dict[str, Any]], None]:
    def change(budget: dict[str, Any], _a: dict[str, Any]) -> None:
        _lines(budget)[0]["BudgetBalances"][0]["Amount"] = value

    return change


def _not_in_chart(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts["Accounts"].pop(0)


def _code_differs(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["AccountCode"] = "201"


def _balance_sheet(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts["Accounts"][1]["Type"] = "CURRLIAB"


def _unknown_type(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts["Accounts"][1]["Type"] = "SUSPENSE"


def _repeated_account(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[1]["AccountID"] = _lines(budget)[0]["AccountID"]
    _lines(budget)[1]["AccountCode"] = "200"


def _shared_name(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts["Accounts"][1]["Name"] = "Sales"


def _chart_repeats_id(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts["Accounts"][2]["AccountID"] = accounts["Accounts"][0]["AccountID"]


def _list_endpoint(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"] = [budget["Budgets"], dict(budget["Budgets"], BudgetID="another")]


def _no_budget_id(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    del budget["Budgets"]["BudgetID"]


def _numeric_budget_id(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["BudgetID"] = 123


def _no_lines(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["BudgetLines"] = []


def _budget_type(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["Type"] = "FORECAST"


def _blank_option(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["Tracking"][0]["Option"] = ""


def _tracking_without_options(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["Tracking"] = []


def _overall_with_tracking(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["Type"] = "OVERALL"


def _lines_not_a_list(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    budget["Budgets"]["BudgetLines"] = {"AccountID": "9c24de87-a2b7-439d-a216-35d1af7bdec3"}


def _id_not_text(budget: dict[str, Any], _a: dict[str, Any]) -> None:
    _lines(budget)[0]["AccountID"] = ["9c24de87-a2b7-439d-a216-35d1af7bdec3"]


def _chart_without_id(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    del accounts["Accounts"][2]["AccountID"]


def _nameless(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts["Accounts"][0]["Name"] = " "


def _no_accounts_key(_b: dict[str, Any], accounts: dict[str, Any]) -> None:
    accounts.pop("Accounts")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_drop_one_month, "missing periods"),
        (_gap, "missing periods"),
        (_repeat_month, "repeats period 2019-08"),
        (_no_balances, "missing periods"),
        (_month_name, "period 'Aug-2019'"),
        (_month_13, "period '2019-13'"),
        (_period_in_other_digits, "is not YYYY-MM"),
        (_unit_amount, "UnitAmount"),
        (_amount("1,000"), "amount '1,000'"),
        (_amount("1e3"), "amount '1e3'"),
        (_amount("١٠٠٠"), "not a plain finite number"),
        (_amount("9" * 400), "not a plain finite number"),
        (_amount(10**400), "not a plain finite number"),
        (_no_budget_id, "without a BudgetID"),
        (_numeric_budget_id, "without a BudgetID: 123"),
        (_amount("NaN"), "amount 'NaN'"),
        (_amount(float("inf")), "amount inf"),
        (_amount(True), "amount True"),
        (_amount(None), "amount None"),
        (_not_in_chart, "not in the chart"),
        (_code_differs, "code '201'"),
        (_balance_sheet, "balance-sheet account"),
        (_unknown_type, "unknown account type 'SUSPENSE'"),
        (_repeated_account, "more than once"),
        (_shared_name, "share the name 'Sales'"),
        (_chart_repeats_id, "chart lists account"),
        (_list_endpoint, "single budget"),
        (_no_lines, "no budget lines"),
        (_budget_type, "budget type 'FORECAST'"),
        (_blank_option, "tracking"),
        (_tracking_without_options, "tracking"),
        (_overall_with_tracking, "tracking"),
        (_no_accounts_key, "Accounts"),
        (_lines_not_a_list, "BudgetLines to be a list"),
        (_id_not_text, "not in the chart"),
        (_chart_without_id, "without an AccountID"),
        (_nameless, "has no name"),
    ],
)
def test_malformed_or_ambiguous_budget_is_refused(
    tmp_path: Path, change: Callable[[dict[str, Any], dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _read_with(tmp_path, change)
