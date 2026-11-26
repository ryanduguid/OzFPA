<p align="center">
  <picture>
    <source media="(max-width: 600px) and (prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/banner-phone-light.svg">
    <source media="(max-width: 600px)" srcset="https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/banner-phone.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/banner-light.svg">
    <img src="https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/banner.svg" width="100%" alt="AU FP&amp;A. Cash, budgets and variance on Australian 30 June years. Pixel art of a bar chart with a rising arrow beside the AU FP&amp;A wordmark in slab-serif block letters.">
  </picture>
</p>

<div align="center">

[![tests](https://img.shields.io/github/actions/workflow/status/ryanduguid/OzFPA/ci.yml?branch=main&label=tests&labelColor=000000&style=flat)](https://github.com/ryanduguid/OzFPA/actions/workflows/ci.yml)
[![Codecov](https://img.shields.io/codecov/c/github/ryanduguid/OzFPA?label=Codecov&labelColor=000000&style=flat)](https://codecov.io/gh/ryanduguid/OzFPA)
[![CodeQL](https://img.shields.io/github/actions/workflow/status/ryanduguid/OzFPA/codeql.yml?branch=main&label=CodeQL&labelColor=000000&style=flat)](https://github.com/ryanduguid/OzFPA/actions/workflows/codeql.yml)
[![SonarCloud](https://img.shields.io/sonar/quality_gate/ryanduguid_au-fpa-pack?server=https%3A%2F%2Fsonarcloud.io&label=SonarCloud&labelColor=000000&style=flat)](https://sonarcloud.io/summary/new_code?id=ryanduguid_au-fpa-pack)
[![Codacy code quality](https://img.shields.io/codacy/grade/04c98b58f66e4339b598720a05aa6bc7?label=Codacy&labelColor=000000&style=flat)](https://app.codacy.com/gh/ryanduguid/OzFPA/dashboard)<br>
[![OpenSSF Scorecard](https://raw.githubusercontent.com/ryanduguid/.github/badges/ryanduguid/OzFPA.svg)](https://scorecard.dev/viewer/?uri=github.com/ryanduguid/OzFPA)
[![OpenSSF Best Practices](https://img.shields.io/cii/level/15426?label=Best%20Practices&labelColor=000000&style=flat)](https://www.bestpractices.dev/projects/15426)
[![SLSA provenance](https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/badges/slsa.svg)](https://github.com/ryanduguid/OzFPA/attestations)
[![VirusTotal](https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/badges/virustotal.svg)](https://github.com/ryanduguid/OzFPA/releases/latest)<br>
[![PyPI](https://badgen.net/pypi/v/au-fpa-pack?label=pypi&color=66023C&labelColor=000000)](https://pypi.org/project/au-fpa-pack/)
[![python: 3.14+](https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/badges/python.svg)](https://www.python.org/)
[![licence: Apache-2.0](https://raw.githubusercontent.com/ryanduguid/OzFPA/main/.github/assets/badges/licence.svg)](LICENSE)

[Worked example](#worked-example) · [Package](#package) · [Skills](#skills) · [Licence](#licence)

</div>

OzFPA is an Australian extension of [openfpa](https://github.com/JeffBrines/openfpa),
by Guiderail, for accountants and analysts doing forecasting and month-end work: 30 June
financial years, Xero AU account mapping, GST and BAS cash timing and payroll on-costs.

OzFPA builds monthly, weekly and daily cash forecasts, a three-way monthly forecast
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

**Package lifecycle:** published. The distribution is `au-fpa-pack`, the import is `pyfpa` and the command is `openfpa`. Version 0.8.1 is on PyPI as `au-fpa-pack` and has an immutable GitHub release; a clone stays the way to develop it.

On Python 3.14 or newer, run `python -m pip install au-fpa-pack`. Never install the PyPI distribution named `pyfpa`: it is an unrelated project that also installs a top-level `pyfpa` package.

### Connect a local MCP client

Install the release that includes the stdio server with
`python -m pip install au-fpa-pack==0.8.1`. Configure the client's command
as `openfpa` and its arguments as `mcp-serve` and the absolute path to an
existing working folder. To launch the server manually from that folder,
run `openfpa mcp-serve .`. The client sends one JSON-RPC message per line
on standard input.

Version 0.8.1 negotiates `2025-11-25`, `2025-06-18`, `2025-03-26` and
`2024-11-05` through `initialize`. An unknown version receives an offer of
`2025-11-25`. After initialisation, `tools/list` exposes `cash13_workbook`,
which writes a 13-week cash forecast workbook under the working folder, and
`variance_summary`, which summarises supplied budget and actual figures.

## Skills

The OzFPA [`skills/`](skills/) folder holds 17 skills. Sixteen are the pack's own, grouped by what
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
/plugin marketplace add ryanduguid/OzFPA
/plugin install au-fpa-pack@au-fpa-pack
```

## Alternatives and scope

OzFPA is built for local Australian cash, GST, BAS and tax-timing modelling from records a firm supplies, rather than a hosted subscription or live bank-feed service:

- [openfpa](https://github.com/JeffBrines/openfpa): the upstream workbench, for work that needs no Australian rules.
- **Offline receipts, actions and reforecasting:** `predicted_receipts` times open invoices from observed customer payment lag, `risk_week_actions` ranks debtor-chase and payment-timing levers (never facility draws), `weekly_actuals_score` checks closed weeks against actuals, and `reforecast_from_actuals` rolls the 13-week forecast forward without nightly polling or live bank feeds.
- **Budgets and BAS timing:** `pyfpa.io.xero_budget` reads 2 saved JSON responses from Xero's Accounting API (`GET /Budgets/{BudgetID}` and `GET /Accounts`, without credentials or network calls; see the [Xero recipe](docs/recipes/xero-au.md#budget-from-the-xero-api)) and carries them through BAS, PAYG, FBT and public-holiday-adjusted payment dates (built to published API documentation; not run against a live Xero organisation).

<details>
<summary>Kernel packages, upstream workbench and reference</summary>

## Kernel packages and how each is reached

The CLI and the skills reach 3 OzFPA kernel packages:

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

The OzFPA guides are grouped as how-to and reference pages.

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

<p align="center"><sub><i>'The plans of the diligent lead only to plenty.'</i> Proverbs 21:5 (<a href="https://netbible.org/">NET</a>)<br>Reusing this code? See <a href="NOTICE">NOTICE</a> for attribution. AI agents: see <a href="https://github.com/ryanduguid/OzFPA/blob/main/AGENTS.md#reusing-this-code">AGENTS.md</a>.<br>Made in Newcastle, Australia by <a href="https://duguid.com.au/">Ryan Duguid</a>.</sub></p>
