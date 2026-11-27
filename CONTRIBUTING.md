# Contributing to OzFPA

OzFPA builds on [openfpa](https://github.com/JeffBrines/openfpa), an open source experiment from [Guiderail](https://www.guiderail.io). It's
early, and help is genuinely welcome, whether that's a bug report, a sharper piece of
CFO judgement, or a whole new industry pack. No promises on response time, and please be
kind; this is a side-of-the-desk project.

## Getting set up

CI installs with [uv](https://docs.astral.sh/uv/) from the hash-locked `uv.lock`; do the same:

```bash
git clone https://github.com/ryanduguid/OzFPA
cd OzFPA
uv sync --locked --extra dev
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy
uv run --locked --extra dev pytest -q -n 4
```

`ruff check . --fix` applies the safe fixes. `mypy` checks against Python 3.14, the
minimum in `requires-python`; run lint and type checks in a Python 3.14 environment,
as CI does. Lint and the test lanes start together, so a lint failure does not hide a
test result.

## The checks CI runs

`ci-gates`, `public-fixtures-gates` and `codeql-gates` fail unless every job they cover
succeeded. These are the commands each job runs (`ci.yml` unless named):

- **lint:** `shellcheck -x .githooks/commit-msg .github/ci/joined-fixtures.sh`; `actionlint` over the workflows, with
  shellcheck on their scripts; `uv run --locked --extra dev ruff check .`;
  `uv run --locked --extra dev mypy`.
- **test (3.14):** builds the wheel and imports a fixture from it in a separate
  environment, away from the checkout; then
  `uv run --locked --extra dev coverage run --branch --source=pyfpa -m pytest -q` (serial,
  so coverage sees every test), `uv run --locked --extra dev coverage report --fail-under=100`,
  `diff-cover coverage.xml --compare-branch=origin/main --branch-coverage --fail-under=100`
  over `pyfpa/memory/connectors.py` and `pyfpa/memory/workspace.py`, and
  `uv audit --locked --no-config --python-version 3.14`. Codecov receives the same
  coverage and requires 100% of the project and of each patch.
- **test (3.15):** `uv run --locked --extra dev pytest -q -n 4`.
- **minimum-resolution** (Linux and Windows, Python 3.14):
  `uv sync --upgrade --resolution lowest-direct --extra dev`, then
  `uv audit --locked --no-config --python-version 3.14 --resolution lowest-direct` and
  `uv run --locked --resolution lowest-direct --extra dev pytest -q -n 4`.
- **connector-security-windows** (Python 3.15):
  `uv run --locked --extra dev pytest -q tests/test_memory_connectors.py`.
- **fixture-screen**, in `tools/fixture-screen` on Rust 1.99: `cargo fmt --check`,
  `cargo clippy --locked --all-targets -- -D warnings`,
  `cargo deny --locked --config ../../deny.toml check sources` and
  `cargo test --locked --release`.
- **fuzzing** (weekly and on demand, not a gate):
  `python -m pip install --require-hashes --only-binary :all: --requirement requirements-fuzz.txt`,
  then `python -m fuzz.xero_import fuzz/corpus -max_total_time=60 -max_len=4096 -timeout=2 -rss_limit_mb=1024`.
- **live-network** (weekly and on demand, not a gate):
  `uv run --locked --extra dev pytest -m network`.
- **public-fixtures** (`joined-fixtures.yml`, Linux and Windows): runs
  `utility_workflows.py` from Accounting Review Pipeline for the close-forecast, quarter,
  job-cash and grant-cash workflows; see 'The workflow' below.
- **Analyze (python)** and **Analyze (actions)** (`codeql.yml`): CodeQL, with no build.
- **secrets** (`secrets.yml`): the shared secrets scan, with this repository's `.gitleaks.toml`.
- **Attribution policy** (`no-ai-attribution.yml`): refuses AI authorship credit in PR
  titles, commit trailers and identities. `.githooks/commit-msg` is the local equivalent.
- Outside pull requests: `scorecard.yml` (weekly OpenSSF Scorecard),
  `joined-fixtures-heads.yml` (weekly, see below), `release.yml` and `virustotal.yml`
  (tagged releases).

`pytest.ini` deselects the `network` marker by default, so a Reserve Bank outage or a
published layout change cannot fail a branch that did not cause it. Run `pytest -m
network` when you touch `pyfpa/au/drivers.py` or refresh the RBA fixtures under
`tests/fixtures/`. CI also runs them weekly and on demand in the `live-network`
job, which does not gate merges.

The distribution is `au-fpa-pack`; the importable package is `pyfpa` (`import pyfpa`).

Pandas 3 requires openpyxl 3.1.5 or newer. Versions before 3.1.3 can retain workbook file handles
on Windows with Python 3.11.8 or newer, preventing verified exports from replacing
their destination. See [openpyxl issue 2149 in its release notes](https://openpyxl.readthedocs.io/en/stable/changes.html).
CI runs the minimum-dependency suite on Python 3.14 on both Linux
and Windows.

## The workflow

`joined-fixtures.yml` runs the fabricated close-to-forecast, quarter,
job-to-cash and grant-to-cash examples on weekly scheduled runs, pull requests, pushes to `main` and manual
runs. Linux and Windows jobs use the proposed FPA checkout with full commit pins for
Accounting Review Pipeline and Australian Accounting. Update those pins deliberately
when adopting compatible changes. `joined-fixtures-heads.yml` runs the same jobs weekly
with both companions at `main`; it gates nothing, and a failure there is the signal to
look at the drift before moving a pin. Each owner runs in a separate process and fresh
environment, using its workspace lock where applicable.

The existing [joined example driver](https://github.com/ryanduguid/accounting-review-pipeline/blob/3dcb5304f4c67c01de98b34638999b5f274d1810/packages/monthly-close-control-plane/docs/utility-workflows.md)
checks cash values and retained REVIEW findings. Separate operating-system artefacts
retain fabricated results, failure diagnostics, the escaped summary, success manifest
and replay record for seven days. These public routes require no
private grant checkout or cross-repository secret. Linux keeps the `public-fixtures`
check name and Windows adds `public-fixtures (Windows)`; branch protection requires
`public-fixtures-gates`, which needs both.

1. Fork, branch, and make your change.
2. **Add tests for new behaviour.** The project is test-first, and CI runs the suite on
   Python 3.14 and 3.15. A green suite is required to merge, as are clean
   `ruff check .` and `mypy` runs.
3. Open a PR describing what you changed and why. For anything non-trivial, describe the
   approach in an [issue](https://github.com/ryanduguid/OzFPA/issues) or a draft PR before
   you build. Changes to the shared openfpa core belong in [openfpa's issues](https://github.com/JeffBrines/openfpa/issues).

## What's most useful to contribute

The engine is deliberately lean; the value is in the skillset and how widely it covers
real businesses. The contributions that help most:

- **Industry packs:** a polished generated skill for a vertical the toolkit doesn't cover
  well yet (SaaS, restaurant, logistics, agency, and so on). The `fpa-learn-business` skill
  spins these up per business; a generalised, well-documented one helps everyone. See the
  `segment-rollup` skill in the Fox Factory example for the shape.
- **Data-access recipes:** teach the agent how to identify, request, map, test,
  and reconcile a source such as QuickBooks, Xero, NetSuite, Stripe, a bank
  export, or a local reporting folder. Reusable primitives are welcome, but live
  company connectors should remain generated for that company. See
  `examples/foxfactory/pull_edgar.py` for the pattern.
- **CFO judgement rules:** a real-world gotcha worth encoding into `fpa-cfo-judgment`.
- **Public-company proofs:** apply the workflow to another source-traced public
  company with honest accounting reproduction, a historical holdout, and clear
  forecast limitations.

## House rules

- **No real client data, ever, and no secrets.** Use synthetic data or public filings
  only (the Fox example uses nothing but public SEC data). Credentials come from the host
  environment or an MCP server, never committed. The `fixture-screen` job in `ci.yml` fails
  on a checksum-valid TFN, ABN, ACN or Medicare number in any tracked file, and on a file
  that is not UTF-8. It skips a match only when its first and last digit groups are both
  inside numbers: a hexadecimal token of 16 or more characters, a `0x` literal, a float's
  exponent or a percentage. Use a value whose check digit fails, or list a documented test
  value for its file, with its reason, in `tools/fixture-screen/tests/synthetic-identifiers.txt`.
- Keep modules small, pure, and immutable; config is pydantic-validated; disk I/O stays in
  the `io/` layer. Match the surrounding style.
- By contributing, you agree to offer your work under the [Apache License, Version 2.0](LICENSE). Retained Guiderail code remains under the MIT licence reproduced in [NOTICE](NOTICE).

Questions or ideas about the shared core go to [openfpa's issues](https://github.com/JeffBrines/openfpa/issues);
for the Australian layer, use [this repository's issues](https://github.com/ryanduguid/OzFPA/issues).

## Release checks

The release caller names the component checks that must have succeeded for the
exact release commit on `main`. It advances the policy SHA, `required-checks`
and `actions: read` together. Skipped, missing, cancelled or failed checks block
publication, including component tests skipped by a path filter. An aggregate
gates job cannot replace those checks. Before tagging, choose a main-branch
commit with successful component CI; a successful run for an older commit is
not evidence for the release. Tags and publication still require explicit approval.
