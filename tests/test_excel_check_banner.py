import pytest
from openpyxl import load_workbook

from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.excel.structure import verify_structure

_BASE = {
    "name": "T", "start_month": "2026-01", "horizon_months": 6, "tax_rate": 0.25,
    "channels": [
        {"name": "A", "annual_revenue": 1_200_000.0, "growth_rate": 0.10,
         "seasonality": [1.0] * 12, "cogs_pct": 0.5},
        {"name": "B", "annual_revenue": 600_000.0, "growth_rate": 0.0,
         "seasonality": [1, 1, 1, 1, 1, 1, 2, 2, 2, 1, 1, 1], "cogs_pct": 0.4},
    ],
    "opex": [
        {"name": "salaries", "kind": "fixed", "monthly_amount": 30_000.0},
        {"name": "marketing", "kind": "variable", "pct_of_revenue": 0.05},
    ],
    "debt": [
        {"name": "term", "kind": "term_loan", "opening_balance": 500_000.0,
         "annual_rate": 0.08, "monthly_principal": 10_000.0},
        {"name": "loc", "kind": "loc", "opening_balance": 100_000.0, "annual_rate": 0.10},
    ],
    "working_capital": {"dso_days": 45.0, "dpo_days": 30.0, "dio_days": 60.0},
    "opening_balances": {"cash": 50_000.0, "ar": 100_000.0, "ap": 60_000.0,
                          "inventory": 120_000.0, "nol": 40_000.0},
    "da_monthly": 2_000.0, "capex_monthly": 5_000.0,
}
_PARTS = ["check_revenue_parts", "check_opex_parts", "check_interest_parts",
          "check_principal_parts"]


def _build(tmp_path, **changes):
    path = tmp_path / "model.xlsx"
    model_to_excel(EntityConfig.model_validate({**_BASE, **changes}), path)
    return path


def _labels(ws):
    return {ws.cell(row=r, column=1).value: r for r in range(2, ws.max_row + 1)}


def _status(path):
    formulas = pytest.importorskip("formulas")
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate()
    found = {
        sheet: solution[f"'[{path.name}]{sheet.upper()}'!{ref}"].value[0][0]
        for sheet, ref in (("Checks", "B1"), ("Model", "A1"), ("Assumptions", "B1"))
    }
    assert len(set(found.values())) == 1, found
    return found["Checks"]


def test_every_tab_shows_the_checks_status_from_one_sheet(tmp_path):
    wb = load_workbook(_build(tmp_path))
    assert wb.sheetnames == ["Assumptions", "Model", "Checks"]
    assert wb["Model"]["A1"].value == "=Checks!$B$1"
    assert wb["Assumptions"]["B1"].value == "=Checks!$B$1"
    model_checks = [k for k in _labels(wb["Model"]) if str(k).startswith("check_")]
    checks = wb["Checks"]
    listed = [checks.cell(row=r, column=1).value for r in range(4, checks.max_row + 1)]
    assert listed == model_checks
    assert set(_PARTS) <= set(listed)


def test_status_passes_on_an_intact_model_and_structure_holds(tmp_path):
    path = _build(tmp_path)
    assert verify_structure(path).passed
    wb = load_workbook(path)
    n = sum(1 for k in _labels(wb["Model"]) if str(k).startswith("check_"))
    assert _status(path) == f"All {n} checks pass"


@pytest.mark.parametrize(("line", "check"), [
    ("revenue", "check_revenue_parts"),
    ("opex", "check_opex_parts"),
    ("interest", "check_interest_parts"),
    ("principal", "check_principal_parts"),
])
def test_an_overtyped_schedule_total_fails_its_parts_check_on_every_tab(tmp_path, line, check):
    path = _build(tmp_path)
    wb = load_workbook(path)
    model = wb["Model"]
    # A hardcoded total: every other check stays consistent with it.
    model.cell(row=_labels(model)[line], column=4, value=123456.0)
    wb.save(path)
    assert _status(path) == f"CHECK FAILS: {check}"


def test_a_line_dropped_from_a_total_fails_its_parts_check(tmp_path):
    path = _build(tmp_path)
    wb = load_workbook(path)
    model = wb["Model"]
    rows = _labels(model)
    model.cell(row=rows["revenue"], column=3, value=f"=SUM(C{rows['revenue_ch1']}:C{rows['revenue_ch1']})")
    wb.save(path)
    assert _status(path) == "CHECK FAILS: check_revenue_parts"


def test_direct_cash_tolerance_carries_its_rounding_allowance(tmp_path):
    checks = load_workbook(_build(tmp_path))["Checks"]
    rows = _labels(checks)
    assert checks.cell(row=rows["check_direct_cash"], column=3).value.startswith("=0.000001+MAX(")
    assert checks.cell(row=rows["check_cash_roll"], column=3).value == 0.000001


def test_schedules_without_lines_get_no_parts_check(tmp_path):
    wb = load_workbook(_build(tmp_path, opex=[], debt=[]))
    labels = _labels(wb["Model"])
    assert "check_revenue_parts" in labels
    assert not {"check_opex_parts", "check_interest_parts", "check_principal_parts"} & set(labels)


def test_a_sheet_without_checks_is_refused():
    from openpyxl import Workbook

    from pyfpa.excel.toolkit import add_checks_sheet

    wb = Workbook()
    wb.active.cell(row=2, column=1, value="revenue")
    with pytest.raises(ValueError, match="no check_ rows"):
        add_checks_sheet(wb, wb.active, first_col=2, last_col=3, banners=[])
