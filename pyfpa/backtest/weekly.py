"""A 13-week cash forecast scored against the weeks that followed it.

The weekly counterpart of `holdout_backtest`: the forecast and the actuals are
reduced by `extract_lines` and `aggregate_periods` and scored by
`score_forecast`, so a week is measured, and refused, as a month is. A person
runs it on their own actuals once weeks have closed; it does not change or
refresh the forecast.
"""

from __future__ import annotations

import math
import numbers
import re
from collections.abc import Mapping, Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict

from pyfpa.backtest.holdout import scored_lines
from pyfpa.backtest.score import (
    ScoreResult,
    aggregate_periods,
    extract_lines,
    score_forecast,
)
from pyfpa.cash13.forecast import cash13_forecast
from pyfpa.cash13.schemas import Cash13Config

WEEKLY_SCORE_LINES = ("ending_cash", "receipts", "disbursements")  # a tuple: it is the default argument
# Dollars. A difference up to half a cent is rounding, not a different basis.
# shortcut: float sums hold cent-exact amounts to this below about 10^12 dollars;
# above that, correct actuals can be refused, and Decimal amounts would be needed.
_TOLERANCE = 0.005


class WeeklyScore(BaseModel):
    model_config = ConfigDict(revalidate_instances="always")

    as_at: date                       # the forecast's window_start, the first day of week 1
    per_week: dict[int, ScoreResult]  # each closed week on its own
    overall: ScoreResult              # the closed weeks together: flows summed, ending_cash at the last


def _week_start(label: str) -> date:
    # fromisoformat alone would also read '20261102' and '2026-W45-1'.
    if not isinstance(label, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", label):
        raise ValueError(f"each actual week is labelled by its first day, YYYY-MM-DD, got {label!r}")
    return date.fromisoformat(label)


def _require_same_basis(cfg: Cash13Config, weeks: Sequence[Mapping[str, float]]) -> None:
    """Refuse actual balances that the actual flows do not carry from the forecast's opening cash."""
    balance = cfg.opening_cash
    for week, actual in enumerate(weeks, start=1):
        for field in ("receipts", "disbursements", "ending_cash"):
            if field not in actual:
                raise ValueError(f"actual week {week} is missing {field!r}")
            value = actual[field]
            # math.isfinite reads True as 1 and float() would score it as a dollar.
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise ValueError(f"actual week {week} {field!r} must be a number, got {value!r}")
            if not math.isfinite(value):
                raise ValueError(f"actual week {week} {field!r} must be finite")
        expected = balance + actual["receipts"] - actual["disbursements"]
        if abs(actual["ending_cash"] - expected) > _TOLERANCE:
            raise ValueError(
                f"actual week {week} ends at {actual['ending_cash']:.2f}, not the {expected:.2f} its receipts and "
                f"disbursements give from {balance:.2f}: the actuals are on a different basis from the forecast, "
                "which starts from its opening_cash and counts every receipt and payment in those accounts")
        balance = actual["ending_cash"]


def weekly_actuals_score(
    cfg: Cash13Config,
    actuals_by_week: Mapping[str, Mapping[str, float]],
    *,
    score_lines: Sequence[str] = WEEKLY_SCORE_LINES,
    weights: Mapping[str, float] | None = None,
) -> WeeklyScore:
    """Score `cash13_forecast(cfg)` against the actual weeks that have closed.

    `actuals_by_week` is keyed by each week's first day as YYYY-MM-DD,
    `window_start` plus whole weeks, and gives that week's receipts,
    disbursements and ending_cash (the closing bank balance). The weeks scored
    run from week 1 to the last week given. Each is scored on its own and all
    together, by the weighted MAPE `holdout_backtest` uses, with the same
    default weights.

    Refuses a config without window_start, a week that does not start a
    forecast week, a missing week before the last one given, a missing,
    non-numeric or non-finite receipts, disbursements or ending_cash, and actual balances the
    actual flows do not carry, to the cent, from the forecast's opening_cash,
    which would be on a different basis. A zero actual on a weighted line
    refuses the whole call, naming its week, as `score_forecast` refuses it for
    a month.
    """
    if cfg.window_start is None:
        raise ValueError("the forecast needs window_start, the date it was made as at")
    start = cfg.window_start
    by_week: dict[int, Mapping[str, float]] = {}
    for label, values in actuals_by_week.items():
        offset = (_week_start(label) - start).days
        if offset < 0 or offset % 7 or offset // 7 >= cfg.weeks:
            raise ValueError(f"actual week {label!r} does not start one of the forecast's {cfg.weeks} weeks "
                             f"from {start.isoformat()}")
        # Labels are unique dates in one form, so no 2 of them name the same week.
        by_week[offset // 7 + 1] = values
    if not by_week:
        raise ValueError("at least one actual week is required")
    last = max(by_week)
    missing = [week for week in range(1, last + 1) if week not in by_week]
    if missing:
        raise ValueError(f"actuals are missing for weeks {missing}, before week {last}")
    actuals = [dict(by_week[week]) for week in range(1, last + 1)]
    _require_same_basis(cfg, actuals)

    selected, scored = scored_lines(score_lines, weights)
    forecast = cash13_forecast(cfg)
    per_week: dict[int, ScoreResult] = {}
    for week, actual in enumerate(actuals, start=1):
        try:
            per_week[week] = score_forecast(extract_lines(forecast.loc[[week]], scored),
                                            aggregate_periods([actual], scored), weights=selected)
        except ValueError as error:
            raise ValueError(f"week {week}: {error}") from error
    overall = score_forecast(extract_lines(forecast.loc[1:last], scored),
                             aggregate_periods(actuals, scored), weights=selected)
    return WeeklyScore(as_at=start, per_week=per_week, overall=overall)
