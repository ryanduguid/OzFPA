<p align="center">
  <picture>
    <source media="(max-width: 600px) and (prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/banner-phone-light.svg">
    <source media="(max-width: 600px)" srcset="https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/banner-phone.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/banner-light.svg">
    <img src="https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/banner.svg" width="100%" alt="AU FP&amp;A. Cash, budgets and variance on Australian 30 June years. Pixel art of a bar chart with a rising arrow beside the AU FP&amp;A wordmark in slab-serif block letters.">
  </picture>
</p>

<div align="center">

[![tests](https://github.com/ryanduguid/au-fpa-pack/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ryanduguid/au-fpa-pack/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/ryanduguid/au-fpa-pack/graph/badge.svg)](https://codecov.io/gh/ryanduguid/au-fpa-pack)
[![CodeQL](https://github.com/ryanduguid/au-fpa-pack/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/ryanduguid/au-fpa-pack/actions/workflows/codeql.yml)
[![SonarCloud](https://sonarcloud.io/api/project_badges/measure?project=ryanduguid_au-fpa-pack&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ryanduguid_au-fpa-pack)
[![Codacy code quality](https://app.codacy.com/project/badge/Grade/04c98b58f66e4339b598720a05aa6bc7)](https://app.codacy.com/gh/ryanduguid/au-fpa-pack/dashboard)<br>
[![OpenSSF Scorecard](https://raw.githubusercontent.com/ryanduguid/.github/badges/ryanduguid/au-fpa-pack.svg)](https://scorecard.dev/viewer/?uri=github.com/ryanduguid/au-fpa-pack)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15426/badge)](https://www.bestpractices.dev/projects/15426)
[![SLSA provenance](https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/badges/slsa.svg)](https://github.com/ryanduguid/au-fpa-pack/attestations)
[![VirusTotal](https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/badges/virustotal.svg)](https://github.com/ryanduguid/au-fpa-pack/releases/latest)<br>
[![PyPI](https://badgen.net/pypi/v/au-fpa-pack?label=pypi&color=66023C&labelColor=000000)](https://pypi.org/project/au-fpa-pack/)
[![python: 3.14+](https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/badges/python.svg)](https://www.python.org/)
[![licence: Apache-2.0](https://raw.githubusercontent.com/ryanduguid/au-fpa-pack/main/.github/assets/badges/licence.svg)](LICENSE)

[Worked example](#worked-example) · [Package](#package) · [Skills](#skills) · [Licence](#licence)

</div>

au-fpa-pack is an Australian extension of [openfpa](https://github.com/JeffBrines/openfpa),
by Guiderail, for accountants and analysts doing forecasting and month-end work: 30 June
financial years, Xero AU account mapping, GST and BAS cash timing and payroll on-costs.

au-fpa-pack builds monthly, weekly and daily cash forecasts, a three-way monthly forecast
(profit and loss, balance sheet and cash flow, with GST and payroll liabilities paid on
their due dates) and a management briefing from a company's own records. Every assumption is declared in a file you can read, and
the funding decision stays with a person.

**Start here:** [the worked Lumbridge case](examples/lumbridge-services/README.md) ·
[setup](docs/installation.md) ·
[Australian scope and source dates](docs/australian-pack.md) ·
[the case explained on the web](https://duguid.com.au/examples/profit-vs-cash-flow/)

Source examples also cover [refreshing the cash forecast from actuals](examples/lumbridge-services/RECURRING.md),
[passing the opening balances to close controls](examples/lumbridge-services/CLOSE-HANDOFF.md),
[tracing WIP into project cash](examples/job-to-cash/README.md) and
[separating restricted cash](examples/restricted-cash/README.md).

Continue with the [3-month close simulation](examples/quarter-close/README.md),
[supplier payment plans](examples/creditor-cash/README.md),
[grant-to-cash handoff](examples/restricted-cash/GRANT-HANDOFF.md) and
[Ridgeline receipt-delay and hiring sensitivities](examples/ridgeline/README.md).

## Worked example

The Lumbridge worked example is synthetic, and a human approves the assumptions and funding decision.

**Input:** [Lumbridge Services' fabricated records](examples/lumbridge-services/data/), NSW payroll assumptions and dated customer receipts and payments for October to December 2026.

Lumbridge Services is a fictional Newcastle maintenance business. Its Varrock and Falador service lines are Old School RuneScape references; no game knowledge is needed. All amounts are AUD.

**Try it without Python:** [download the Excel workbook](https://duguid.com.au/assets/examples/lumbridge/lumbridge.xlsx), or [get the sample pack with its source files](https://duguid.com.au/assets/examples/lumbridge/lumbridge-sample-pack.zip). Use desktop Excel with automatic calculation. [Read the case and compare both scenarios](https://duguid.com.au/examples/profit-vs-cash-flow/) in your browser before opening the file.

To reproduce it from a clone, use Python 3.14 and the locked development environment:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev python examples/lumbridge-services/models/generated/lumbridge.py
```

**Output:** `briefing.md`, `lumbridge.xlsx`, monthly and cash schedules in `examples/lumbridge-services/output/`.

The briefing, the monthly and cash schedules and the JSON summary from that run are committed under `examples/lumbridge-services/output/`, so the result can be read without installing anything; the workbook is rebuilt locally. A rendered chart of the 13-week cash line with the 45-day delay, exported from the workbook in Excel, is on the site at <https://duguid.com.au/assets/examples/lumbridge/cash-preview.png> with its capture record.

| Forecast measure | Receipt on time | Receipt 45 days late |
| --- | ---: | ---: |
| Quarter revenue | $180,000.00 | $180,000.00 |
| Quarter profit before income tax | $35,957.55 | $35,957.55 |
| October closing cash | $32,040.00 | ($11,960.00) |
| Lowest daily closing cash | $16,800.00 | ($25,160.00) |
| December closing cash | $67,320.00 | $67,320.00 |

**Human decision:** Can the business meet its next payments if a customer pays late, and should the owner defer discretionary equipment spending?

In desktop Excel, change `Assumptions!B2` from 0 to 45. This delays one $44,000 receipt and creates a $25,160 cash shortfall on 6 November without changing profit. Restore 0 after use. The workbook supports only whole-day receipt delays from 0 to 120; CSVs and briefing text are fixed exports.

Read the [assumptions and limits](examples/lumbridge-services/README.md) before using the example. This synthetic case does not establish client outcomes or forecast accuracy, and the commands above create files without establishing native Excel recalculation.

[Harbour Light](examples/harbour-light/README.md) provides a separate Victorian wholesale example with FY2027 reporting and quarterly BAS cash timing; [other examples](docs/examples.md) use synthetic and public data.

## Package

**Package lifecycle:** published. The distribution is `au-fpa-pack`, the import is `pyfpa` and the command is `openfpa`. Version 0.7.0 is on PyPI as `au-fpa-pack` and has an immutable GitHub release; a clone stays the way to develop it.

On Python 3.14 or newer, run `python -m pip install au-fpa-pack`. Never install the PyPI distribution named `pyfpa`: it is an unrelated project that also installs a top-level `pyfpa` package.

## Skills

The au-fpa-pack [`skills/`](skills/) folder holds 17 skills. Sixteen are the pack's own, grouped by what
they are for:

- **Australian rules:** `fpa-au-drivers`, `fpa-au-gst-bas`, `fpa-au-payroll`, `fpa-au-xero`
- **Onboarding and building:** `fpa-learn-business`, `fpa-configure-actuals`, `fpa-scaffold-model`, `fpa-excel-model`
- **Running the month:** `fpa-monthly-close`, `fpa-cash-runway`, `fpa-board-briefing`, `fpa-cfo-judgment`
- **Learning from outcomes:** `fpa-capture-correction`, `fpa-backtest-learn`, `fpa-research-loop`, `fpa-portfolio-learn`

The seventeenth, [`skills/generated/sku-profitability`](skills/generated/sku-profitability/SKILL.md),
is the worked example of a company-specific skill the workflow writes, not a
skill the pack ships for every company.

[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) declares the
repository as the `au-fpa-pack` plugin, at the package's version, licensed `Apache-2.0 AND MIT` (the MIT part is Guiderail's upstream work). The repository is
also its own marketplace, so Claude Code installs the skills with:

```text
/plugin marketplace add ryanduguid/au-fpa-pack
/plugin install au-fpa-pack@au-fpa-pack
```

## Alternatives

au-fpa-pack is built for Australian cash, GST and BAS timing. As read on 5 November 2026, these
tools cover nearby ground:

- [openfpa](https://github.com/JeffBrines/openfpa): the upstream workbench, for work that needs no Australian rules.
- A comparable plugin collection offered variance analysis and a 30/60/90-day cash flow forecast at
  commit d900840. Its listing showed no 13-week forecast.
- A skills collection for US practice offered budget-versus-actual analysis, narratives explaining
  variances and board packs, with scripts.
- Commercial cash flow forecasting products also cover this work.

Read on 12 November 2026:

- [CFI's free Claude skills](https://corporatefinanceinstitute.com/resources/financial-modeling/free-claude-skills-financial-modeling/)
  (11 November): one builds a three-statement, DCF, LBO, budget or forecast model to CFI's guidelines and one reviews a
  model against them, in the Claude app and Claude in Excel, after a name and email form. The page states no Australian
  rules.
- [Xero New Budgets](https://blog.xero.com/product-updates/new-budgets/) (11 November): scenario budgets inside Xero,
  from zeros or last month's or the last 12 months' actuals, per tracking category, with an adjustment history. The
  post does not mention GST, BAS or tax due dates. This pack adds the Australian cash timing a budget leaves out: BAS,
  PAYG and FBT due dates moved past whole-of-state public holidays, lodgment-channel dates and the GIC cost of paying an
  ATO debt by instalments.

Read on 15 November 2026:

- [XBert 13-Week Cashflow](https://github.com/XBertIntelligence/XBert-Plugins/tree/main/plugins/xbert-cashflow-13week)
  (MIT in its plugin manifest, though the repository has no licence file; at commit e8f489f5, and the plugin last
  changed on 23 July 2026): a Claude plugin for
  accountants that pulls the bank balance, receivables, payables, payroll and tax obligations from a client's live
  Xero, MYOB or QuickBooks Online ledger and bank feed through XBert's service. Its instructions put each open invoice
  in the week of its due date plus that debtor's average delay past due (the median when skewed), name each week below
  a chosen cash threshold with its drivers, and suggest 3 actions for each: chase debtors, delay suppliers or draw on a
  facility. It needs an XBert account and at least 90 days of bank feed history. This pack needs no account and works
  from the records the firm supplies. From those records, `predicted_receipts` places each open invoice on the median
  days to pay of its customer's paid invoices that took at least as long as the open one is old (every customer's
  below 6 of those, and no date below 6 again), and `risk_week_actions` ranks up to 3 actions for each risk week:
  chase an overdue invoice or pay a bill on its due date instead of earlier, never later than due and never a
  facility draw.
- [Xero's Cash flow manager](https://central.xero.com/0/article/Cash-flow-manager-with-Analytics-powered-by-Syft), in
  Analytics: projects 7 to 180 days from the bank balances in Xero, the amounts owing on invoices and bills, quotes,
  cash movements entered by hand and [recurring weekly and monthly payments](https://central.xero.com/0/article/About-cash-flow-predictions-in-Analytics-powered-by-Syft)
  predicted from the previous 3 months. [ITBrief reported](https://itbrief.co.nz/story/xero-adds-ai-analytics-cash-flow-forecasting-in-anz)
  on 11 March 2026 that its forecasts use predicted payment dates based on observed payment behaviour; the Xero Central
  articles do not say how. The articles, the report and Xero's [Australian cash flow page](https://www.xero.com/au/accounting-software/analytics/cash-flow/)
  do not mention GST, BAS or PAYG due dates.
- [Float](https://floatapp.com/pricing): cash flow forecasting connected to Xero or QuickBooks, with a 13-week view
  and 8 scenarios, after a 14-day trial. Its [Small Business](https://floatapp.com/pricing-for-small-businesses) plan,
  for companies below £2m in revenue, forecasts 12 months for A$155 a month billed annually or A$189 monthly; Growth,
  for companies over £2m, forecasts 36 months for A$300 a month billed annually or A$379 monthly. Prices exclude VAT.
- [Luca AI](https://ask-luca.com/product-docs/forecasting/cash-flow-forecast): 13-week and 12-month forecasts for
  online brands from Xero or QuickBooks beside Shopify, refreshed overnight and checked against actuals every night.
  This pack's `weekly_actuals_score` is a check a person runs on their own closed weeks: it scores the 13-week
  forecast against actual receipts, payments and bank balances, week by week and together, and refuses actuals that
  do not line up. It does not fetch actuals or run nightly. `reforecast_from_actuals` then rolls the forecast past
  the closed weeks from their actual closing balance and places open invoices again from the latest payments.
- [anthropics/knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins/tree/main/small-business/skills/cash-flow-snapshot)
  `cash-flow-snapshot` (at commit e91a1345): a 30/60/90-day forecast that times each customer's receipts by its mean
  days from invoice to receipt, using every customer's mean below 3 payments. It is written instructions without
  scripts.
- [OneWave-AI/claude-skills](https://github.com/OneWave-AI/claude-skills/tree/main/cash-flow-forecaster)
  `cash-flow-forecaster` (MIT): a 13-week method that places open invoices at their due date plus the customer's
  historical lateness and lists levers for each crunch week. It is a single instruction file and names no Australian
  tax dates.

Read on 15 November 2026: Xero Central's [Export a budget](https://central.xero.com/s/article/Export-a-budget) article
says New Budgets, in early access, cannot export a budget; Budget Manager exports CSV, Excel or Google Sheets files.
This pack reads a Budget Manager budget from Xero's Accounting API (`pyfpa.io.xero_budget`, see the
[Xero recipe](docs/recipes/xero-au.md#budget-from-the-xero-api)) and carries it through the BAS timing above. The
reader is built to Xero's published API documentation and has not been run against a live Xero organisation. XBert's
13-week plugin README and skill (commit e8f489f5) do not mention a budget as an input.

<details>
<summary>Kernel packages, upstream workbench and reference</summary>

## Kernel packages and how each is reached

The CLI and the skills reach 3 au-fpa-pack kernel packages:

| Package | What it is for | How it is reached |
| --- | --- | --- |
| `pyfpa/memory` | Company memory on disk: the `.fpa/` workspace, intake, sources, mappings, connectors, corrections, experiments, entrypoints and the retrieval index. | The `openfpa` CLI. Every workspace command in the [CLI reference](docs/cli-reference.md) goes through it. |
| `pyfpa/research` | The champion and challenger loop: a company objective, scored epochs and a model registry that only a recorded human approval changes. | `openfpa status` reads the model registry. The loop itself runs from [`skills/fpa-research-loop`](skills/fpa-research-loop/SKILL.md) against the Python API. |
| `pyfpa/portfolio` | Cross-client learning: a portfolio manifest, priors mined and validated across clients, and recurring generated skills promoted into a shared library. Promotion is default-deny: mining and validation propose, and nothing reaches the library without a `PromotionApproval` the practitioner records for that exact candidate. | The Python API only. No CLI command reaches it, and today the one documented route is [`skills/fpa-portfolio-learn`](skills/fpa-portfolio-learn/SKILL.md). |

Promotion is the one place the pack would move one client's information into another
client's work, so it refuses to until you record the decision. The approval is an
acknowledgement of a judgement you made, not authentication and not legal proof that the
client consented. Running locally means nothing goes out over the network; it does not by
itself make that reuse permissible, so read [SECURITY.md](SECURITY.md) and the
[`fpa-portfolio-learn`](skills/fpa-portfolio-learn/SKILL.md) guardrails first.

## Guides

The au-fpa-pack guides are grouped as how-to and reference pages.

**How-to**

- [Verify a downloaded release](https://github.com/ryanduguid/release-policy/blob/main/docs/verify-a-release.md): checksum and SLSA provenance
- [Supplier information for a firm's AI register](docs/ai-register-entry.md)

**Reference**

- [Agent CLI reference](docs/cli-reference.md)

**Background**

- [Upstream workbench and company workspace](docs/upstream-workbench.md)
- [Python kernel](docs/python-kernel.md)

**Contribute**

- [Contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md)

</details>

## Licence

Ryan Duguid's original work is licensed under the [Apache License, Version 2.0](LICENSE). Guiderail's upstream code remains under MIT, as recorded in [NOTICE](NOTICE). When redistributing this work or a derivative, preserve the applicable attribution notices in [NOTICE](NOTICE) as required by section 4(d). Versions released before this change keep the licence they were released with.

The licence does not cover the scripture quotation in the footer. Scripture quoted by permission. Quotations designated (NET) are from the NET Bible® copyright ©1996, 2019 by Biblical Studies Press, L.L.C. [netbible.com](https://netbible.com) All rights reserved.

<sub>Planning aid, not professional advice, an assessment, a private ruling or a statutory lodgement; confirm rates, caps, thresholds and treatments against current rules. See [DISCLAIMER.md](DISCLAIMER.md).</sub>

---

<p align="center"><sub><i>'The plans of the diligent lead only to plenty.'</i> Proverbs 21:5 (<a href="https://netbible.org/">NET</a>)<br>Reusing this code? See <a href="NOTICE">NOTICE</a> for attribution. AI agents: see <a href="https://github.com/ryanduguid/au-fpa-pack/blob/main/AGENTS.md#reusing-this-code">AGENTS.md</a>.<br>Made in Newcastle, Australia by <a href="https://duguid.com.au/">Ryan Duguid</a>.</sub></p>
