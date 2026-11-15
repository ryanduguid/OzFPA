## Python kernel

The importable package is `pyfpa`. The distribution name is `au-fpa-pack`.

The account-and-amount CSV readers refuse duplicate or unnamed column headings,
extra row fields and non-blank rows without an account. These cases can otherwise discard
or misassign amounts. Entirely blank rows and declared metadata columns remain
supported. Quote amounts that contain thousands separators, such as `"1,234"`.

```python
import pyfpa

config = pyfpa.load_config("examples/ridgeline/config.yaml")
monthly = pyfpa.cashflow_from_config(config)

cash_config = pyfpa.load_cash13_config("examples/ridgeline/cash13.yaml")
weekly = pyfpa.cash13_forecast(cash_config)
# The buffer is passed on because the summary cannot read it from the config.
# A stated facility_limit also gives headroom and its first breach week.
runway = pyfpa.runway_summary(weekly, cash_config.headroom_buffer)

print(pyfpa.to_briefing_md(monthly, title="My Company", runway=runway))
```

Named scenarios change the declared 13-week flows instead of editing them. A
`FlowChange` scales every base flow of one name (`amount_factor`), pushes it
later (`delay_weeks`), or both; `add_receipts` and `add_disbursements` add new
flows. A name that matches no base flow is refused, so a misspelling cannot
leave a scenario identical to the base. A flow pushed past the horizon leaves
the forecast. A delay moves a `monthly` or `quarterly` flow's `anchor_date` by
the same number of weeks, so the flow recurs on the later date's day of month.

```python
scenarios = pyfpa.load_cash13_scenarios("examples/ridgeline/scenarios.yaml")
print(pyfpa.compare_scenarios(cash_config, scenarios))
```

`compare_scenarios` returns one row per scenario, base first, with the cash
trough (`min_cash`), its week, the first negative week, every week below zero
(`negative_weeks`, a list) and closing cash. With a facility it adds
`min_headroom`, `first_headroom_breach_week` and `headroom_breach_weeks`, the
list of weeks headroom is below the buffer. It compares declared assumptions; it
does not say which scenario is likely.

### The 13-week forecast against actuals

`holdout_backtest` scores a monthly forecast against held-out monthly actuals.
`weekly_actuals_score` is its weekly counterpart for the 13-week forecast: once
weeks have closed, it scores the forecast against what happened, each week on its
own and the closed weeks together, with the same weighted MAPE, default weights
and refusals. You run it on your own actuals; it does not change or refresh the
forecast.

A forecast made as at Monday 2 November 2026 starts with 10,000 in the bank and
expects 4,000 in and 3,000 out each week. The first 2 weeks close like this:

```python
from datetime import date

config = pyfpa.Cash13Config(
    opening_cash=10000.0, window_start=date(2026, 11, 2),
    receipts=[pyfpa.WeeklyFlow(name="Sales", amount=4000.0, start_week=1, recurrence="weekly")],
    disbursements=[pyfpa.WeeklyFlow(name="Costs", amount=3000.0, start_week=1, recurrence="weekly")])
score = pyfpa.weekly_actuals_score(config, {
    "2026-11-02": {"receipts": 3000.0, "disbursements": 3000.0, "ending_cash": 10000.0},
    "2026-11-09": {"receipts": 5000.0, "disbursements": 2500.0, "ending_cash": 12500.0},
})
```

| | Ending cash | Receipts | Disbursements | Fitness |
| --- | ---: | ---: | ---: | ---: |
| Week 1 | +10.0% (11,000 against 10,000) | +33.3% | 0.0% | 0.1556 |
| Week 2 | -4.0% (12,000 against 12,500) | -20.0% | +20.0% | 0.1733 |
| Both weeks | -4.0% | 0.0% | +9.1% | 0.0445 |

Each error is (forecast - actual) / |actual|, and fitness weighs ending cash at
0.4 and each flow at 1.0, as the monthly holdout does. Together, the receipts
match to the dollar, which hides a 1,000 miss each way in the weeks themselves.
`tests/test_backtest_weekly.py` asserts these figures.

Actual weeks are keyed by their first day and run from week 1 without a gap; a
week that does not start on a forecast week, a missing week before the last one
given, or a missing value is refused. Each week's closing balance must equal the
last one plus that week's receipts less disbursements, starting from the
forecast's `opening_cash`, or the actuals are refused as being on a different
basis, such as flows net of GST against bank balances. A zero actual on a
weighted line is refused for its week, as it is for a month: give that line a
zero weight to leave it out.

The base kernel includes:

- monthly P&L and indirect cash-flow modelling
- 13-week direct-method cash forecasting, with named scenario comparison
- revenue, COGS, operating-expense, debt, tax, and working-capital primitives
- reconciliation, segment, SKU, and divestiture analysis helpers
- CSV ingestion and Markdown or Excel reporting: static value export via
  `forecast_to_excel`, and a live-formula model workbook via `model_to_excel`
  (named assumption cells, real formulas, verified against the engine in CI);
- forecast snapshots, scoring, holdout backtests, and the 13-week forecast
  scored against closed weeks
- workspace, intake, correction, experiment, retrieval, and research records
- experimental cross-company prior and skill mining.

`EntityConfig` is a starting point; it does not prescribe every model. A company
with cohorts, projects, contracts, fleets, stores, or complex inventory may need
a different generated model.

The `model_to_excel` function compiles an `EntityConfig` into a 2-sheet workbook:
an Assumptions sheet of named, editable driver cells and a Model sheet where every
P&L and cash-flow line is a real formula referencing those names. The `verify_workbook`
function evaluates the workbook with a Python formula engine and compares every line
and month to `cashflow_from_config`, so the workbook is verified against the engine
before it is used. For cadences or layouts the kernel does not cover, compose
`pyfpa.excel.toolkit` in a company-specific exporter and verify it the same way.
