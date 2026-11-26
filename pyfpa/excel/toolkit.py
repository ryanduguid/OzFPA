from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.worksheet import Worksheet

MONEY_FORMAT = "#,##0"
# Model outputs: plain commas under 100,000, K from 100,000 and M from 1,000,000.
# Excel allows 2 conditions in a format, so negatives take the third section and
# show plain commas. The cell value is unchanged; only its display is scaled.
AMOUNT_KM_FORMAT = '[>=1000000]#,##0.0,,"M";[>=100000]#,##0,"K";#,##0'
DATE_FORMAT = "dd/mm/yyyy"
PERCENT_FORMAT = "0.0%"
DAYS_FORMAT = "0.0"
# Editable drivers carry the spreadsheet convention for inputs: blue font.
INPUT_FONT_COLOR = "0000FF"
INPUT_FONT = Font(color=INPUT_FONT_COLOR)
# The same absolute tolerance verify_workbook applies to check_ rows by default.
CHECK_TOLERANCE = 0.000001
CHECKS_SHEET = "Checks"
CHECK_STATUS_REF = f"{CHECKS_SHEET}!$B$1"
_CHECKS_FIRST_ROW = 4

def add_named_cell(
    wb: Workbook,
    ws: Worksheet,
    *,
    name: str,
    row: int,
    col: int,
    value: float,
    number_format: str | None = None,
) -> None:
    """Write a value and register a workbook-scoped defined name for the cell."""
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = INPUT_FONT
    if number_format:
        cell.number_format = number_format
    ref = f"'{ws.title}'!${get_column_letter(col)}${row}"
    wb.defined_names[name] = DefinedName(name=name, attr_text=ref)

def add_named_row(
    wb: Workbook,
    ws: Worksheet,
    *,
    name: str,
    row: int,
    start_col: int,
    values: Sequence[float],
    number_format: str | None = None,
) -> None:
    """Write a horizontal run of values and register a defined name for the range."""
    for offset, value in enumerate(values):
        cell = ws.cell(row=row, column=start_col + offset, value=value)
        cell.font = INPUT_FONT
        if number_format:
            cell.number_format = number_format
    first = f"${get_column_letter(start_col)}${row}"
    last = f"${get_column_letter(start_col + len(values) - 1)}${row}"
    wb.defined_names[name] = DefinedName(
        name=name, attr_text=f"'{ws.title}'!{first}:{last}"
    )

def fill_formula_row(
    ws: Worksheet,
    *,
    row: int,
    label: str,
    start_col: int,
    n_cols: int,
    template: Callable[[int, str], str],
    number_format: str | None = None,
) -> None:
    """Label column A, then fill each month cell with template(month_index, column_letter).

    template receives the 1-based month index and that month's column letter and
    must return a full formula string starting with '='."""
    ws.cell(row=row, column=1, value=label)
    for m in range(1, n_cols + 1):
        col = get_column_letter(start_col + m - 1)
        cell = ws.cell(row=row, column=start_col + m - 1, value=template(m, col))
        if number_format:
            cell.number_format = number_format

def _check_rows(
    source: Worksheet, allowances: Mapping[str, str],
) -> tuple[dict[str, int], list[tuple[str, int]]]:
    """Row of every labelled line, and the check_ lines in order; refuses none or a bad allowance."""
    labels = {
        str(source.cell(row=r, column=1).value): r
        for r in range(2, source.max_row + 1)
        if source.cell(row=r, column=1).value is not None
    }
    checks = [(label, row) for label, row in labels.items() if label.startswith("check_")]
    if not checks:
        raise ValueError(f"{source.title} has no check_ rows to roll up")
    unknown = sorted(label for pair in allowances.items() for label in pair if label not in labels)
    if unknown:
        raise ValueError(f"allowance rows name labels {source.title} does not have: {unknown}")
    return labels, checks


def _write_excess_row(
    ws: Worksheet, source: Worksheet, row: int, check: int, allowance: int,
    first_col: int, last_col: int,
) -> None:
    """Each month's absolute check value less that month's own allowance."""
    for col in range(first_col, last_col + 1):
        month = f"'{source.title}'!{get_column_letter(col)}"
        ws.cell(row=row, column=col, value=f"=MAX({month}{check},-{month}{check})-{month}{allowance}")


def add_checks_sheet(
    wb: Workbook,
    source: Worksheet,
    *,
    first_col: int,
    last_col: int,
    banners: Sequence[tuple[Worksheet, str]],
    allowances: Mapping[str, str] | None = None,
) -> int:
    """Roll every ``check_`` row on ``source`` up to one status on a Checks sheet.

    Each check gets its largest absolute monthly value, its tolerance and OK or
    FAIL. Checks!B1 names the first failing check, or says all pass, and each
    ``(sheet, cell)`` in ``banners`` shows that status at the top of its tab.
    ``allowances`` maps a check label to the label of a row holding each
    month's own allowance (a rounding budget): that check's difference is its
    largest monthly excess over the allowance, worked out month by month in a
    row below the table. Returns the check count.
    """
    allowances = dict(allowances or {})
    labels, checks = _check_rows(source, allowances)
    first, last = get_column_letter(first_col), get_column_letter(last_col)

    def span(row: int, sheet: str = source.title) -> str:
        return f"'{sheet}'!${first}${row}:${last}${row}"

    ws = wb.create_sheet(CHECKS_SHEET)
    ws.cell(row=1, column=1, value="Model status")
    ws.cell(row=2, column=1, value="Each difference is the largest absolute monthly value of its check row, less that month's allowance where it has one.")
    for col, heading in enumerate(("Check", "Largest difference", "Tolerance", "Status"), start=1):
        ws.cell(row=_CHECKS_FIRST_ROW - 1, column=col, value=heading)
    status = f'"All {len(checks)} checks pass"'
    helper = _CHECKS_FIRST_ROW + len(checks) + 1
    for offset, (label, row) in reversed(list(enumerate(checks))):
        r = _CHECKS_FIRST_ROW + offset
        largest = f"=MAX(MAX({span(row)}),-MIN({span(row)}))"
        if label in allowances:
            ws.cell(row=helper, column=1, value=f"{label} less {allowances[label]}, by month")
            _write_excess_row(ws, source, helper, row, labels[allowances[label]], first_col, last_col)
            largest = f"=MAX({span(helper, CHECKS_SHEET)})"
            helper += 1
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=largest)
        ws.cell(row=r, column=3, value=CHECK_TOLERANCE)
        ws.cell(row=r, column=4, value=f'=IF(B{r}<=C{r},"OK","FAIL")')
        status = f'IF(D{r}="OK",{status},"CHECK FAILS: {label}")'
    ws.cell(row=1, column=2, value=f"={status}").font = Font(bold=True)
    for sheet, ref in banners:
        sheet[ref] = f"={CHECK_STATUS_REF}"
        sheet[ref].font = Font(bold=True)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 32
    return len(checks)
