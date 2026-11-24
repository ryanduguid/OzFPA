import itertools
import json

import pytest

from pyfpa.memory.lineage import MappingRegistry, MappingRule, flat_actuals_table

_RULES = MappingRegistry(mappings=[
    MappingRule(source_id="gl", source_value="4000", target="revenue"),
    MappingRule(source_id="gl", source_value="4010", target="revenue"),
    MappingRule(source_id="gl", source_value="6100", target="opex"),
    MappingRule(source_id="gl", source_value="1100", target="cash"),
    MappingRule(source_id="gl", source_value="9999", target="", status="ignored", rationale="suspense"),
    MappingRule(source_id="other", source_value="7000", target="opex"),
])


def _table(tmp_path, body, header="account_id,period,amount"):
    path = tmp_path / "actuals.csv"
    path.write_text(f"{header}\n{body}", encoding="utf-8")
    return path


def _read(path, **columns):
    return flat_actuals_table(path, source_id="gl", mappings=_RULES, **columns)


def test_flows_and_balances_map_to_each_target_by_month(tmp_path):
    result = _read(_table(tmp_path, (
        "4000,2026-07,100\n4010,2026-07,\"1,250.50\"\n6100,2026-07,(40)\n1100,2026-07,500\n"
        "4000,2026-08,120\n1100,2026-08,640\n9999,2026-08,3\n\n"
    )))
    assert result["passed"]
    assert result["periods"] == ["2026-07", "2026-08"]
    assert result["actuals"] == {
        "cash": {"2026-07": 500.0, "2026-08": 640.0},
        "opex": {"2026-07": -40.0, "2026-08": 0.0},
        "revenue": {"2026-07": 1350.5, "2026-08": 120.0},
    }
    assert result["ignored"] == ["9999"]
    assert result["row_count"] == 7
    json.dumps(result)


def test_duplicates_unmapped_accounts_and_missing_months_each_fail(tmp_path):
    result = _read(_table(tmp_path, (
        "4000,2026-07,100\n4000,2026-07,5\n7000,2026-07,9\n4000,2026-10,1\n"
    )))
    assert not result["passed"]
    assert result["duplicates"] == ["4000 2026-07"]
    # A rule for another source does not map this one.
    assert result["unmapped"] == ["7000"]
    assert result["missing_periods"] == ["2026-08", "2026-09"]
    assert result["actuals"]["revenue"] == {"2026-07": 105.0, "2026-08": 0.0, "2026-09": 0.0, "2026-10": 1.0}


@pytest.mark.parametrize("order", list(itertools.permutations(["4000", "4010", "6100"])))
def test_a_month_total_is_exact_in_any_row_order(tmp_path, order):
    rules = MappingRegistry(mappings=[
        MappingRule(source_id="gl", source_value=account, target="revenue") for account in order
    ])
    amounts = {"4000": "9007199254740992", "4010": "1", "6100": "-9007199254740992"}
    path = _table(tmp_path, "".join(f"{account},2026-07,{amounts[account]}\n" for account in order))
    result = flat_actuals_table(path, source_id="gl", mappings=rules)
    assert result["passed"]
    assert result["actuals"] == {"revenue": {"2026-07": 1.0}}


# The last case is 2026-08 with its year in Arabic-Indic digits, which a Unicode \d accepts.
@pytest.mark.parametrize("period", [
    "2026-7", "2026-13", "July 2026", "2026-07-31", "", "٢٠٢٦-08",
])
def test_a_period_that_is_not_a_month_is_refused(tmp_path, period):
    with pytest.raises(ValueError, match="row 2 must be a month written YYYY-MM"):
        _read(_table(tmp_path, f"4000,{period},1\n"))


def test_named_columns_and_table_shape_are_checked(tmp_path):
    path = _table(tmp_path, "4000,2026-07,1\n", header="Account,Month,Net")
    assert _read(path, account_column="Account", period_column="Month", amount_column="Net")["passed"]
    with pytest.raises(ValueError, match="expected columns 'account_id' and 'period' and 'amount'"):
        _read(path)
    with pytest.raises(ValueError, match="no account rows"):
        _read(_table(tmp_path, "\n"))
    with pytest.raises(ValueError, match="missing account in source CSV row 2"):
        _read(_table(tmp_path, ",2026-07,1\n"))
    with pytest.raises(ValueError, match="must be finite"):
        _read(_table(tmp_path, "4000,2026-07,1e308\n4010,2026-07,1e308\n"))


def _workspace(tmp_path, run_cli, body):
    assert run_cli("init", str(tmp_path)).returncode == 0
    (tmp_path / "actuals.csv").write_text(f"account_id,period,amount\n{body}", encoding="utf-8")
    assert run_cli(
        "source-register", str(tmp_path), "--source-id", "gl", "--kind", "local_file",
        "--location", "actuals.csv", "--entity", "Acme", "--currency", "AUD",
        "--extraction-method", "Manual export",
    ).returncode == 0
    assert run_cli(
        "mapping-register", str(tmp_path), "--source-id", "gl", "--source-value", "4000",
        "--target", "revenue",
    ).returncode == 0


def _flat(tmp_path, run_cli, *extra):
    result = run_cli(
        "reconcile-source", str(tmp_path), "--source-id", "gl", "--account-column", "account_id",
        "--amount-column", "amount", "--period-column", "period", *extra,
    )
    return result.returncode, json.loads(result.stdout)


def test_reconcile_source_maps_a_flat_table_by_month(tmp_path, run_cli):
    _workspace(tmp_path, run_cli, "4000,2026-07,10\n4000,2026-08,12\n")
    code, payload = _flat(tmp_path, run_cli)
    assert code == 0
    assert payload["data"]["actuals"] == {"revenue": {"2026-07": 10.0, "2026-08": 12.0}}


def test_reconcile_source_flat_failures(tmp_path, run_cli):
    _workspace(tmp_path, run_cli, "4000,2026-07,10\n5000,2026-07,1\n")
    code, payload = _flat(tmp_path, run_cli)
    assert code == 1
    assert payload["data"]["unmapped"] == ["5000"]
    code, payload = _flat(tmp_path, run_cli, "--allow-unmapped")
    assert code == 0
    for expected in ('{"revenue": 10}', ""):
        code, payload = _flat(tmp_path, run_cli, "--expected-json", expected)
        assert code == 1
        assert "takes no --expected-json" in payload["error"]["message"]


# --allow-unmapped waives only unmapped accounts: a repeated month or a gap still fails.
@pytest.mark.parametrize("body", ["4000,2026-07,10\n4000,2026-07,1\n", "4000,2026-07,10\n4000,2026-09,1\n"])
@pytest.mark.parametrize("extra", [(), ("--allow-unmapped",)])
def test_reconcile_source_flat_duplicate_or_gap_fails_even_when_unmapped_allowed(
    tmp_path, run_cli, body, extra,
):
    _workspace(tmp_path, run_cli, body)
    code, payload = _flat(tmp_path, run_cli, *extra)
    assert code == 1
    assert payload["data"]["passed"] is False
