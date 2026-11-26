## Agent toolbelt CLI

The `openfpa` command is an interface for Codex, Claude
Code, and other capable coding agents. It emits JSON, performs deterministic
workspace operations, and leaves reasoning and conversation to the host agent.

The command set is:

```text
openfpa init
openfpa inspect-data
openfpa status
openfpa source-profile
openfpa source-register
openfpa source-list
openfpa mapping-register
openfpa mapping-list
openfpa reconcile-source
openfpa connector-scaffold
openfpa connector-list
openfpa connector-validate
openfpa intake-next
openfpa intake-record
openfpa doctor
openfpa entrypoint-list
openfpa entrypoint-register
openfpa correction-record
openfpa correction-list
openfpa scorecard-render
openfpa experiment-list
openfpa context-pack
openfpa onboarding-render
openfpa model-export
openfpa mcp-serve
openfpa model-assumptions
```

In a source checkout without the `openfpa` console script installed, every
command also works as `python3 -m pyfpa.cli <command>`.

The CLI can:

- initialise and validate the workspace
- inventory local files and likely financial artefacts
- profile CSV, TSV, and Excel tables without changing them
- register source provenance, coverage, entities, and currencies
- persist exact source-to-model mappings and deliberate ignores
- reconcile account-amount CSV files while surfacing duplicates and unmapped values
- scaffold company connector bundles from redacted fixtures
- execute fixture-mode connector contracts and compare golden mapped totals
- show unresolved intake questions
- expose source, mapping, model, and research status
- run deterministic checks and reports
- provide structured context for the AI to continue the work
- support non-interactive automation where the operation is deterministic.

The AI should still decide what questions matter, what data path to use, what
model fits the business, and what experiment to run next.

All commands return a versioned JSON envelope. Exit code `0` means success, `1`
means the requested operation or a diagnostic check failed, and `2` means the
command arguments were invalid.

`intake-record` writes one sourced fact to `.fpa/intake.md`. Generated company
workflows are published in `.fpa/models/entrypoints.yaml` with
`entrypoint-register`. The registry lets an agent discover the tested command,
working directory, inputs, and outputs. Registration does not execute the
command.

```bash
openfpa source-register . \
  --source-id monthly-pl \
  --kind local_file \
  --location data/monthly-pl.csv \
  --entity "Acme Inc." \
  --currency USD \
  --period 2026-05 \
  --extraction-method "Controller export from the accounting system"

openfpa mapping-register . \
  --source-id monthly-pl \
  --source-value "Product Revenue" \
  --target income_statement.product_revenue

# --expected-json is required: reviewed target-to-total control figures from an
# independent source. Mapping coverage alone does not reconcile the export.
openfpa reconcile-source . \
  --source-id monthly-pl \
  --account-column Account \
  --amount-column Amount \
  --expected-json '{"income_statement.product_revenue": 100000}'

# An unpivoted table, one row per account and month (YYYY-MM), for income
# statement flows or balance sheet balances: --period-column maps every month
# through the same rules and reports each target's total by month. It fails on
# a repeated account and month, an unmapped account or a month missing between
# the first and last, and takes no --expected-json.
openfpa reconcile-source .   --source-id gl-actuals   --account-column account_id   --period-column period   --amount-column amount

openfpa connector-scaffold . \
  --name accounting-pl \
  --source-id monthly-pl \
  --description "Pull and normalize the monthly P&L" \
  --auth-method host_environment \
  --fixture fixtures/redacted-monthly-pl.csv

openfpa connector-validate . --name accounting-pl

openfpa intake-record . \
  --key business_model \
  --answer "Commercial coffee roasting" \
  --source-type user

openfpa entrypoint-register . \
  --name forecast \
  --kind forecast \
  --description "Run the approved monthly forecast" \
  --command-json '["python3", "models/generated/run_forecast.py"]' \
  --input data/actuals.csv \
  --output output/forecast.xlsx
```

`connector-scaffold` creates:

```text
connectors/generated/accounting-pl/
|-- connector.yaml
|-- connector.py
|-- run.py
|-- README.md
`-- fixtures/source.csv
```

The scaffold requires a registered source, complete mappings, and a redacted
CSV fixture with no duplicate or unmapped accounts. It stores golden mapped
totals in `connector.yaml`. `connector-validate` parses the fixture in-process
through the closed `account-amount-csv` adapter and reconciles it against those
totals. It does not import or run bundle code, and it does not contact a live
system.

The account-and-amount reader also refuses duplicate or unnamed column headings,
extra row fields and non-blank rows without an account. The generated connector applies
the same checks. Entirely blank rows and declared metadata columns remain valid;
amounts containing thousands separators need CSV quotes.

The generated `extract_live()` function intentionally fails until the agent
implements host-authenticated access. After the live path has its own
fixture-backed tests and safe failure behaviour, register the recurring command
with `entrypoint-register --kind connector`.

### Local MCP server

`openfpa mcp-serve <folder>` speaks the Model Context Protocol over stdin and
stdout (newline-delimited JSON-RPC 2.0, the initialize handshake of revisions
2024-11-05 to 2025-11-25) until stdin closes. It opens no network port. Every
path a tool reads or writes must resolve inside `<folder>`: an absolute path, a
`..` that climbs out or a symbolic link that leads out is refused.

- `cash13_workbook` takes `config` (a Cash13Config YAML file) and `out` (an
  `.xlsx` path), writes the 13-week direct-method forecast with
  `forecast_to_excel` and returns the cash trough, its week, closing cash and
  every week below zero (`runway_summary`).
- `variance_summary` takes `model` and `actual` objects of line name to amount
  and an optional `tolerance` (default 0.01) and returns `reconcile`'s lines,
  the lines outside tolerance, the line with the largest absolute variance and
  the net variance. A percentage against a zero actual is `null`.

A tool that refuses its arguments returns a result with `isError: true` and the
reason, so the agent can correct the call. Register it with a client as a stdio
server whose command is `openfpa mcp-serve /path/to/folder`.
