"""A 13-week cash forecast scored against the weeks that followed it.

The first test is the worked example in docs/python-kernel.md, figure for figure.
"""

from datetime import date

import pytest

from pyfpa import weekly_actuals_score
from pyfpa.backtest import ScoreResult
from pyfpa.cash13.schemas import Cash13Config, WeeklyFlow

# Made as at Monday 2 November 2026: 10,000 in the bank, 4,000 in and 3,000 out each week.
CONFIG = Cash13Config(
    opening_cash=10000.0, window_start=date(2026, 11, 2),
    receipts=[WeeklyFlow(name="Sales", amount=4000.0, start_week=1, recurrence="weekly")],
    disbursements=[WeeklyFlow(name="Costs", amount=3000.0, start_week=1, recurrence="weekly")])

ACTUALS = {
    "2026-11-02": {"receipts": 3000.0, "disbursements": 3000.0, "ending_cash": 10000.0},
    "2026-11-09": {"receipts": 5000.0, "disbursements": 2500.0, "ending_cash": 12500.0},
}


def test_the_worked_example_scores_each_week_and_both_together():
    score = weekly_actuals_score(CONFIG, ACTUALS)
    assert score.as_at == date(2026, 11, 2)
    # The default weights are holdout_backtest's: ending_cash 0.4, other lines 1.0, over 2.4.
    assert score.overall.weights == pytest.approx(
        {"ending_cash": 1 / 6, "receipts": 5 / 12, "disbursements": 5 / 12})
    # Week 1: forecast ending cash 11,000 against 10,000, receipts 4,000 against 3,000.
    assert score.per_week[1].per_line == pytest.approx(
        {"ending_cash": 0.1, "receipts": 1 / 3, "disbursements": 0.0})
    assert score.per_week[1].fitness == pytest.approx(0.155556, abs=1e-6)
    # Week 2: 12,000 against 12,500; 4,000 against 5,000; 3,000 against 2,500.
    assert score.per_week[2].per_line == pytest.approx(
        {"ending_cash": -0.04, "receipts": -0.2, "disbursements": 0.2})
    assert score.per_week[2].fitness == pytest.approx(0.173333, abs=1e-6)
    # Together: receipts 8,000 against 8,000 hide both weekly misses.
    assert score.overall.per_line == pytest.approx(
        {"ending_cash": -0.04, "receipts": 0.0, "disbursements": 1 / 11})
    assert score.overall.fitness == pytest.approx(0.044545, abs=1e-6)


def test_one_closed_week_is_scored_alone():
    score = weekly_actuals_score(CONFIG, {"2026-11-02": ACTUALS["2026-11-02"]})
    assert list(score.per_week) == [1]
    assert score.overall == score.per_week[1]


def test_closing_balances_agree_to_the_cent_whatever_the_float_sum():
    # 10,000 + 3,000.10 - 3,000.20 is 9,999.900000000001 in floating point.
    week = {"receipts": 3000.1, "disbursements": 3000.2, "ending_cash": 9999.9}
    score = weekly_actuals_score(CONFIG, {"2026-11-02": week})
    assert score.per_week[1].per_line["ending_cash"] == pytest.approx(1000.1 / 9999.9)
    with pytest.raises(ValueError, match="ends at 9999.89, not the 9999.90 .* different basis"):
        weekly_actuals_score(CONFIG, {"2026-11-02": {**week, "ending_cash": 9999.89}})


def test_weights_and_lines_follow_the_monthly_holdout():
    score = weekly_actuals_score(CONFIG, ACTUALS, score_lines=["ending_cash", "net_cash"],
                                 weights={"ending_cash": 1.0, "net_cash": 0.0})
    assert isinstance(score.overall, ScoreResult)
    # A zero weight switches a line off, as in holdout_backtest.
    assert score.overall.per_line == pytest.approx({"ending_cash": -0.04})


@pytest.mark.parametrize(
    ("actuals", "match"),
    [
        # Weeks that do not line up with the forecast's.
        ({"2026-11-03": ACTUALS["2026-11-02"]}, r"'2026-11-03' does not start one of the forecast's 13 weeks"),
        ({"2026-10-26": ACTUALS["2026-11-02"]}, "does not start one of the forecast's"),
        ({"2027-02-01": ACTUALS["2026-11-02"]}, "does not start one of the forecast's"),
        ({"2/11/2026": ACTUALS["2026-11-02"]}, "labelled by its first day, YYYY-MM-DD"),
        ({"20261102": ACTUALS["2026-11-02"]}, "labelled by its first day, YYYY-MM-DD"),
        # Actuals missing for a scored week.
        ({}, "at least one actual week"),
        ({"2026-11-09": ACTUALS["2026-11-09"]}, r"missing for weeks \[1\], before week 2"),
        ({"2026-11-02": {"receipts": 3000.0, "ending_cash": 10000.0}}, "week 1 is missing 'disbursements'"),
        ({"2026-11-02": {**ACTUALS["2026-11-02"], "receipts": float("nan")}}, "week 1 'receipts' must be finite"),
        # True would pass math.isfinite and score as one dollar.
        ({"2026-11-02": {"receipts": True, "disbursements": True, "ending_cash": 10000.0}},
         "week 1 'receipts' must be a number, got True"),
        ({"2026-11-02": {**ACTUALS["2026-11-02"], "ending_cash": "10000"}},
         "week 1 'ending_cash' must be a number, got '10000'"),
        # A different basis: flows net of GST against gross balances, or another opening balance.
        ({"2026-11-02": {"receipts": 2727.27, "disbursements": 2727.27, "ending_cash": 10000.0},
          "2026-11-09": {"receipts": 4545.45, "disbursements": 2272.73, "ending_cash": 12500.0}},
         r"actual week 2 ends at 12500.00, not the 12272.72 .* different basis"),
        ({"2026-11-02": {"receipts": 3000.0, "disbursements": 3000.0, "ending_cash": 15000.0}},
         "actual week 1 ends at 15000.00, not the 10000.00 .* from 10000.00: the actuals are on a different basis"),
        # A zero actual has no relative error, so the week is refused, as a month would be.
        ({"2026-11-02": {"receipts": 0.0, "disbursements": 0.0, "ending_cash": 10000.0}},
         r"week 1: no scorable lines for requested evidence: \['receipts', 'disbursements'\]"),
    ],
)
def test_actuals_that_cannot_be_scored_without_guessing_are_refused(actuals, match):
    with pytest.raises(ValueError, match=match):
        weekly_actuals_score(CONFIG, actuals)


def test_a_forecast_without_a_date_and_a_week_not_labelled_by_text_are_refused():
    with pytest.raises(ValueError, match="needs window_start"):
        weekly_actuals_score(CONFIG.model_copy(update={"window_start": None}), ACTUALS)
    with pytest.raises(ValueError, match="labelled by its first day"):
        weekly_actuals_score(CONFIG, {date(2026, 11, 2): ACTUALS["2026-11-02"]})  # type: ignore[dict-item]
