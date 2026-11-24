"""Workbook verification harness: evaluate live-formula workbook and compare to engine.

The ``formulas`` package is a dev-only dependency; it is imported lazily so
the runtime library works without it.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from types import ModuleType

import pandas as pd
from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter
from pydantic import BaseModel


class Hardcode(BaseModel):
    cell: str
    line: str
    value: float
    in_formula: bool


class HardcodeReport(BaseModel):
    passed: bool
    hardcodes: list[Hardcode]
    cells_checked: int


# The kernel's own constants: zero and one, months per year, its 30-day month
# and the direct-cash rounding factor. Anything else in a formula is reported.
KERNEL_LITERALS = frozenset({0.0, 1.0, 12.0, 30.0, 4e-15})
_STRING = re.compile(r'"(?:[^"]|"")*"')
_SHEET_PREFIX = re.compile(r"(?:'(?:[^']|'')*'|[A-Za-z_][A-Za-z0-9_.]*)!")
_TOKEN = re.compile(
    r"(?P<rows>\$?\d+\s*:\s*\$?\d+)"
    r"|(?P<ref>\$?[A-Za-z]{1,3}\$?\d+(?![A-Za-z0-9_.(]))"
    r"|(?P<name>[A-Za-z_\\][A-Za-z0-9_.]*)"
    r"|(?P<num>(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?)"
)


_OPERAND_START = "(,=<>+-*/^&"


def formula_literals(formula: str) -> list[float]:
    """Numbers typed into a formula, with any unary sign and percent applied.

    Cell references, whole-row ranges, names, text and whole-number powers
    (the kernel's growth exponent is the year index) are not numbers.
    """
    body = _SHEET_PREFIX.sub("", _STRING.sub('""', formula.lstrip("=")))
    found: list[float] = []
    for token in _TOKEN.finditer(body):
        number = token.group("num")
        if number is None:
            continue
        value = float(number)
        before = body[:token.start()].rstrip()
        # A sign is unary at the start or after an operator or open bracket.
        while before[-1:] in ("+", "-") and before[:-1].rstrip()[-1:] in ("", *_OPERAND_START):
            value = -value if before[-1] == "-" else value
            before = before[:-1].rstrip()
        if before.endswith("^") and number.isdigit():
            continue
        if body[token.end():].lstrip().startswith("%"):
            value /= 100
        found.append(value)
    return found


def hardcode_report(
    path: str | Path,
    *,
    sheet: str = "Model",
    allowed: frozenset[float] = KERNEL_LITERALS,
) -> HardcodeReport:
    """List every hardcoded number in a model sheet's formula range.

    The range is every labelled row from row 2 and every month column the
    header row names. A number typed over a cell is reported with
    ``in_formula`` false; a number inside a formula that is not in ``allowed``,
    nor the negative of one, is reported with ``in_formula`` true, once per
    occurrence. No formula is
    evaluated, so ``formulas`` is not needed.
    """
    wb = load_workbook(Path(path))
    if sheet not in wb.sheetnames:
        raise ValueError(f"{sheet} sheet is missing")
    ws = wb[sheet]
    last_col = 1
    while ws.cell(row=1, column=last_col + 1).value not in (None, ""):
        last_col += 1
    found: list[Hardcode] = []
    checked = 0
    for row in range(2, ws.max_row + 1):
        label = ws.cell(row=row, column=1).value
        if label is None or str(label).strip() == "":
            continue
        for col in range(2, last_col + 1):
            cell = ws.cell(row=row, column=col)
            value = cell.value
            if isinstance(value, bool) or value is None:
                continue
            checked += 1
            if isinstance(value, (int, float)):
                found.append(Hardcode(cell=cell.coordinate, line=str(label), value=float(value), in_formula=False))
            elif cell.data_type == "f" and isinstance(value, str):
                found.extend(
                    Hardcode(cell=cell.coordinate, line=str(label), value=number, in_formula=True)
                    for number in formula_literals(value)
                    if abs(number) not in allowed
                )
    return HardcodeReport(passed=not found, hardcodes=found, cells_checked=checked)


class VerifyReport(BaseModel):
    passed: bool
    failures: list[str]
    max_rel_deviation: float
    lines_checked: int


def _load_formulas() -> ModuleType:
    try:
        import formulas
    except ImportError as exc:
        raise RuntimeError(
            "workbook verification requires the 'formulas' package: pip install formulas"
        ) from exc
    module: ModuleType = formulas
    return module


def _period_label(value: object, freq: str | None) -> str:
    """Normalise a Model-sheet header cell to the label form ``expected`` uses.

    The kernel exporter writes ``str(period)``; a company exporter may write the
    month's start datetime instead. Both are compared on the same footing.
    """
    if value is None:
        return ""
    if isinstance(value, (dt.datetime, dt.date)) and freq:
        return str(pd.Period(value, freq=freq))
    return str(value).strip()


def verify_workbook(
    path: str | Path,
    expected: pd.DataFrame,
    *,
    rel_tol: float = 1e-6,
    inputs: dict[str, float] | None = None,
) -> VerifyReport:
    """Evaluate the workbook's formulas in Python and compare every column of
    ``expected`` against the Model sheet, month by month.

    Every column of ``expected`` is required: a line the workbook does not carry
    is a failure, not a skipped check. The Model sheet's header row must also
    name the same periods as ``expected``, in the same order, so a workbook built
    for other months cannot pass on position alone.

    NaN or unevaluated cells are failures, never skipped.

    Rows labelled ``check_*`` are the workbook's own ties: every month must
    evaluate to zero within ``rel_tol``, or the verification fails.
    For positive tolerances, ``check_direct_cash`` also permits the finite,
    non-negative dollar allowance in ``direct_cash_rounding`` for binary64
    rounding across its two independent arithmetic paths. Zero tolerance
    requires exact equality for every check.

    ``inputs`` maps ``'Sheet!A1'`` to a value that replaces that input cell
    before calculation, as a user changing it in Excel would, so a scenario
    control is tested in the file as shipped. Each must name an existing
    non-formula cell; ``formulas`` would silently accept any other key.

    Key format confirmed against formulas 1.3.4:
        ``'[<filename_exact_case>]MODEL'!<COL><ROW>``
    The sheet name is stored as-uppercase in the solution dict.
    """
    if not math.isfinite(rel_tol) or rel_tol < 0:
        raise ValueError("rel_tol must be finite and non-negative")
    if expected.empty:
        raise ValueError("expected forecast must not be empty")
    formulas = _load_formulas()
    path = Path(path)
    wb = load_workbook(path)
    overrides = {}
    sheets = {name.upper(): wb[name] for name in wb.sheetnames}
    for target, value in (inputs or {}).items():
        sheet, _, ref = target.rpartition("!")
        ws = sheets.get(sheet.strip("'").upper())
        cell = ws[ref.replace("$", "")] if ws is not None and ref else None
        # A range gives a tuple; a formula or empty cell is not an input.
        if ws is None or not isinstance(cell, Cell) or cell.value is None or cell.data_type == "f":
            raise ValueError(f"input {target!r} is not an existing value cell")
        overrides[f"'[{path.name}]{ws.title.upper()}'!{cell.coordinate}"] = value
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate(inputs=overrides)

    model_ws = wb["Model"]
    labels = {
        model_ws.cell(row=r, column=1).value: r
        for r in range(2, model_ws.max_row + 1)
    }

    failures: list[str] = []
    max_dev = 0.0
    lines = 0

    freq = expected.index.freqstr if isinstance(expected.index, pd.PeriodIndex) else None
    for m_idx, period in enumerate(expected.index):
        want_label = str(period)
        got_label = _period_label(
            model_ws.cell(row=1, column=2 + m_idx).value, freq
        )
        if got_label != want_label:
            failures.append(
                f"month {m_idx + 1}: workbook header {got_label!r} vs expected {want_label!r}"
            )

    for line in expected.columns:
        if line not in labels:
            failures.append(f"{line}: required output missing from the Model sheet")
            continue
        lines += 1
        row = labels[line]
        for m_idx in range(len(expected.index)):
            col_letter = get_column_letter(2 + m_idx)
            ref = f"'[{path.name}]MODEL'!{col_letter}{row}"
            if ref not in solution:
                failures.append(f"{line} month {m_idx + 1}: cell not evaluated (key {ref!r} missing)")
                continue
            raw = solution[ref].value[0][0]
            if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                failures.append(f"{line} month {m_idx + 1}: workbook returned NaN/None")
                continue
            if not isinstance(raw, (int, float)):
                # Excel error sentinels (#DIV/0!, #VALUE!, ...) arrive as XlError
                # objects. An errored cell is a failed verification, never a crash.
                failures.append(f"{line} month {m_idx + 1}: workbook returned error {raw!s}")
                continue
            got = float(raw)
            want = float(expected[line].iloc[m_idx])
            # Hybrid tolerance: relative above magnitude 1, absolute below it,
            # so zero-valued lines (for example, tax with full NOL cover) stay checkable.
            denom = max(abs(want), 1.0)
            dev = abs(got - want) / denom
            max_dev = max(max_dev, dev)
            if not dev <= rel_tol:
                failures.append(
                    f"{line} month {m_idx + 1}: workbook {got!r} vs engine {want!r}"
                    f" (rel_dev={dev:.2e})"
                )

    for label, row in labels.items():
        if not isinstance(label, str) or not label.startswith("check_"):
            continue
        for m_idx in range(len(expected.index)):
            col_letter = get_column_letter(2 + m_idx)
            ref = f"'[{path.name}]MODEL'!{col_letter}{row}"
            if ref not in solution:
                failures.append(
                    f"{label} month {m_idx + 1}: cell not evaluated (key {ref!r} missing)"
                )
                continue
            raw = solution[ref].value[0][0]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                failures.append(f"{label} month {m_idx + 1}: check returned {raw!s}, expected 0")
                continue
            rounding = 0.0
            if label == "check_direct_cash" and rel_tol > 0:
                budget_row = labels.get("direct_cash_rounding")
                budget_ref = f"'[{path.name}]MODEL'!{col_letter}{budget_row}"
                budget = solution[budget_ref].value[0][0] if budget_ref in solution else None
                if (isinstance(budget, bool) or not isinstance(budget, (int, float))
                        or not math.isfinite(budget) or budget < 0):
                    failures.append(f"{label} month {m_idx + 1}: invalid direct cash rounding allowance")
                    continue
                rounding = float(budget)
            # Subtract the finite tolerance instead of adding it to the budget,
            # which could overflow and accidentally permit a non-finite check.
            if not math.isfinite(raw) or abs(float(raw)) - rel_tol > rounding:
                failures.append(f"{label} month {m_idx + 1}: check is non-zero ({float(raw)})")

    return VerifyReport(
        passed=not failures and lines > 0,
        failures=failures,
        max_rel_deviation=max_dev,
        lines_checked=lines,
    )
