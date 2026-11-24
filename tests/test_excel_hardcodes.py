import pytest
from openpyxl import load_workbook

from pyfpa.config.schemas import EntityConfig
from pyfpa.excel.model_workbook import model_to_excel
from pyfpa.excel.verify import formula_literals, hardcode_report

_CFG = {
    "name": "T", "start_month": "2026-01", "horizon_months": 30, "tax_rate": 0.25,
    "channels": [{"name": "A", "annual_revenue": 1_200_000.0, "growth_rate": 0.10,
                  "seasonality": [1.0] * 12, "cogs_pct": 0.5}],
    "opex": [{"name": "salaries", "kind": "fixed", "monthly_amount": 30_000.0},
             {"name": "marketing", "kind": "variable", "pct_of_revenue": 0.05}],
    "debt": [{"name": "term", "kind": "term_loan", "opening_balance": 500_000.0,
              "annual_rate": 0.08, "monthly_principal": 10_000.0}],
    "working_capital": {"dso_days": 45.0, "dpo_days": 30.0, "dio_days": 60.0},
    "opening_balances": {"cash": 50_000.0, "ar": 100_000.0, "ap": 60_000.0,
                          "inventory": 120_000.0, "nol": 40_000.0},
    "da_monthly": 2_000.0, "capex_monthly": 5_000.0,
}


def _model(tmp_path):
    path = tmp_path / "model.xlsx"
    model_to_excel(EntityConfig.model_validate(_CFG), path)
    return path


def _rows(ws):
    return {ws.cell(row=r, column=1).value: r for r in range(2, ws.max_row + 1)}


def test_a_built_model_has_no_hardcodes_and_every_cell_is_read(tmp_path):
    path = _model(tmp_path)
    report = hardcode_report(path)
    assert report.passed, report.hardcodes
    model = load_workbook(path)["Model"]
    assert report.cells_checked == len(_rows(model)) * 30


def test_a_typed_number_and_plugs_inside_formulas_are_each_listed(tmp_path):
    path = _model(tmp_path)
    wb = load_workbook(path)
    model = wb["Model"]
    rows = _rows(model)
    model.cell(row=rows["revenue"], column=4, value=123456.0)
    model.cell(row=rows["opex"], column=5, value=f"=SUM(E{rows['opex_1']}:E{rows['opex_2']})*1.1+500")
    wb.save(path)
    found = [(h.cell, h.line, h.value, h.in_formula) for h in hardcode_report(path).hardcodes]
    r, o = rows["revenue"], rows["opex"]
    assert found == [(f"D{r}", "revenue", 123456.0, False),
                     (f"E{o}", "opex", 1.1, True), (f"E{o}", "opex", 500.0, True)]


def test_allowed_literals_can_be_narrowed(tmp_path):
    report = hardcode_report(_model(tmp_path), allowed=frozenset({0.0, 1.0}))
    assert {h.value for h in report.hardcodes} == {12.0, 30.0, 4e-15}


@pytest.mark.parametrize(("formula", "numbers"), [
    ("=B2*1.1", [1.1]),
    ("=rev_annual_ch1*(1+growth_ch1)^2", [1.0]),
    ("=B2^1.5", [1.5]),
    ("='FY 2026'!B3+Sheet2!C4+2", [2.0]),
    ('=IF(B2>0,"Q3 2026",3)', [0.0, 3.0]),
    ("=$B$12+AB12+.5", [0.5]),
    ("=4E-15*MAX(B2,-B2)", [4e-15]),
    ("=LOG10(B2)", []),
])
def test_formula_literals(formula, numbers):
    assert formula_literals(formula) == numbers


def test_unlabelled_rows_and_booleans_are_skipped_and_a_missing_sheet_is_refused(tmp_path):
    path = _model(tmp_path)
    wb = load_workbook(path)
    model = wb["Model"]
    model.cell(row=model.max_row + 2, column=2, value=99.0)
    model.cell(row=model.max_row + 1, column=1, value="flag")
    model.cell(row=model.max_row, column=2, value=True)
    wb.save(path)
    assert hardcode_report(path).passed
    with pytest.raises(ValueError, match="Forecast sheet is missing"):
        hardcode_report(path, sheet="Forecast")
