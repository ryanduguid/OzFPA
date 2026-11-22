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

### Three-way forecast

`three_way_from_config` turns the same configuration into a monthly profit and
loss, balance sheet and cash flow statement. The balance sheet opens on the
month before `start_month` with the configured opening balances, and opening
equity is the opening net assets. Each balance rolls forward on its own:
receivables, stock and payables from the working-capital model, fixed assets
from capex less D&A, debt from its schedule, income tax from the provision less
`income_tax.payments`, and equity from net income. Cash is the cash flow
statement's closing cash, and `check_balance` (assets less liabilities and
equity) is nil in every month.

```python
import pyfpa
from pyfpa.au.gst import GstAssumptions

config = pyfpa.load_config("examples/ridgeline/config.yaml")
three_way = pyfpa.three_way_from_config(config, gst=GstAssumptions())
assert three_way.balance_sheet["check_balance"].abs().max() < 0.01
print(three_way.cash_flow[["operating_cash_flow", "gst", "closing_cash"]])
```

Without `gst` or `payroll`, the profit and loss and closing cash equal
`cashflow_from_config`'s. The optional layers use the Australian timing code
unchanged:

- `gst=GstAssumptions(...)` accrues net GST with `monthly_gst` on revenue and on
  stock purchases, operating expenses and capex, and pays it on `bas_schedule`'s
  due dates; a BAS due after the last month stays in `gst_payable`. Receivables
  and payables carry GST on their taxable and creditable shares. Opening
  receivables and payables are stated excluding GST. Set
  `opening_balances.gst_payable` (negative when refundable) to the net GST owed at
  the start for the BAS period holding the month before it: it is paid on that
  period's `bas_schedule` due date, so a quarter that ends before the start is
  paid on its own date and one still open joins the forecast months' BAS. GST
  overdue from an earlier period is not modelled.
- `payroll=settlement_events(...)` adds the payroll expense (gross wages, super,
  payroll tax and workers compensation) and the liabilities left by each
  component's due-date rule, such as `paygw_due_rule` and `super_due_rule`. An
  obligation before the first month is an opening liability.

Set `opening_balances.fixed_assets` to the book value `da_monthly` depreciates:
D&A that would take fixed assets below nil is refused. Set
`opening_balances.income_tax_payable` (negative when refundable) with
`income_tax`, whose payments settle it. For a company, `pyfpa.au.company_tax_schedule`
dates last year's balance and `payments_by_month(pd.concat([instalments, company_tax]))`
turns it and `payg_instalment_schedule`'s rows into `income_tax.payments`, so a
12-month forecast pays each on its due date; `individual_trust_tax_schedule` does
the same for an individual or trust. GST combined with `bad_debt_share` is
refused, because GST on bad debts is not modelled. Leave provisions and deferred
tax are not modelled either.

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

`reforecast_from_actuals(config, actuals_by_week, predicted, invoices, receipts,
open_invoices)` is the opt-in next step. It takes the same closed weeks, with the
same checks of their weeks, values and balances (it scores nothing, so a week with
no receipts is accepted), and returns `Reforecast(config, receivables, changes)`:

- `config` starts the week after the last closed week, from its actual closing
  balance, and keeps the window's length. Scheduled flows keep their dates: a
  flow in a closed week leaves, and one with no `end_week` runs on into the
  weeks the window gains.
- `receivables` is `predicted_receipts` as at the new start, from the paid
  history as it now stands. `predicted` is the result the forecast's invoice
  receipts came from; those receipts are replaced, so an invoice paid in the
  closed weeks leaves the forecast.
- `changes` lists each invoice either placement holds as `paid`, `new`,
  `changed` (amount or expected date) or `unchanged`.

It refuses invoice receipts the forecast does not hold, and an invoice that was
forecast but is now neither open nor paid in full in the history.
`tests/test_cash13_reforecast.py` rolls a forecast past 4 closed weeks.

Actual weeks are keyed by their first day and run from week 1 without a gap; a
week that does not start on a forecast week, a missing week before the last one
given, or a missing value or one that is not a number is refused. Each week's
closing balance must equal the last one plus that week's receipts less
disbursements, to the cent, starting from the forecast's `opening_cash`, or the
actuals are refused as being on a different basis, such as flows net of GST
against bank balances. The check catches flows and balances that disagree; it
cannot tell whether they cover the same bank accounts as the forecast, so take
them from those accounts. A zero actual
on a weighted line refuses the whole score and names its week, as it does for a
month: give that line a zero weight to leave it out of every week.

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
