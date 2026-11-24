# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Tie every figure in the Lumbridge briefing to the schedule or input it reports.

The generator computes the briefing's two tables, but several sentences carry
figures as written text. A model change that moved a schedule would leave
those sentences stale while the tables regenerated, and nothing would fail.
The example's shipped verifier, `models/generated/verify_briefing.py`, reads
each named figure from the committed briefing and compares it with exactly one
source, and reports any number no tie covers. These tests run it and prove it
catches changed, missing, repeated and untied figures. A separate test proves
the committed files regenerate from the inputs unchanged apart from line
endings.
"""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from pyfpa.io.manifest import verify_manifest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "lumbridge-services"
OUTPUT = EXAMPLE / "output"
DATA = EXAMPLE / "data"
GENERATOR = EXAMPLE / "models" / "generated" / "lumbridge.py"
VERIFIER = EXAMPLE / "models" / "generated" / "verify_briefing.py"
VERIFY = runpy.run_path(str(VERIFIER))
# The late case the briefing compares with on time; the generator uses the same delay.
LATE_DAYS = 45


def sources() -> dict:
    return VERIFY["sources"](OUTPUT, DATA)


def briefing_mismatches(text: str) -> list[str]:
    return VERIFY["briefing_problems"](text, OUTPUT, DATA)


def committed_briefing() -> str:
    return (OUTPUT / "briefing.md").read_text(encoding="utf-8")


def test_the_verifier_command_passes_the_committed_briefing_and_fails_an_untied_figure(tmp_path):
    passed = subprocess.run([sys.executable, str(VERIFIER)], capture_output=True, text=True, check=False)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert json.loads(passed.stdout)["problems"] == []
    output = tmp_path / "output"
    shutil.copytree(OUTPUT, output)
    (output / "briefing.md").write_text(committed_briefing() + "\nWork in progress is $4,321.\n", encoding="utf-8")
    failed = subprocess.run([sys.executable, str(VERIFIER), "--output", str(output)], capture_output=True, text=True, check=False)
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["problems"] == [f"untied figure '4,321' on line {committed_briefing().count(chr(10)) + 2}"]


def test_the_verifier_passes_a_briefing_regenerated_with_the_late_delay(tmp_path):
    runpy.run_path(str(GENERATOR))["run"](tmp_path, LATE_DAYS)
    assert "uses a 45-day receipt delay" in (tmp_path / "briefing.md").read_text(encoding="utf-8")
    assert VERIFY["main"](["--output", str(tmp_path)]) == 0


def test_every_number_in_the_briefing_is_tied():
    text = committed_briefing()
    for added in ("Debtors total $81,000.", "The review took 3 weeks.", "Cash recovers on 9 December."):
        assert any(problem.startswith("untied figure") for problem in briefing_mismatches(text + "\n" + added + "\n")), added


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("up to 14 days late and", "up to 15 days late and"),
        ("1 of 8 invoices is past due", "2 of 8 invoices are past due"),
        ("OPEN-V 0 to 60 days late", "OPEN-V 0 to 50 days late"),
        ("28 days sooner to ($11,960.00)", "30 days sooner to ($11,960.00)"),
        ("gives the 3 paths", "gives the 4 paths"),
        ("October to December 2026, AUD", "October to December 2027, AUD"),
        ("At 31 December, $12,600 GST", "At 30 December, $12,600 GST"),
    ],
)
def test_figures_the_old_test_left_untied_are_now_tied(old, new):
    text = committed_briefing()
    assert old in text
    assert briefing_mismatches(text.replace(old, new, 1))


def test_every_briefing_figure_matches_its_one_source():
    assert briefing_mismatches(committed_briefing()) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("October includes $12,600 of opening GST", "October includes $12,500 of opening GST"),
        ("| Minimum daily cash | $16,800.00 |", "| Minimum daily cash | $16,700.00 |"),
        ("The loan balance is $17,000", "The loan balance is $18,000"),
        ("reaches ($25,160) on 6 November", "reaches ($25,160) on 7 November"),
        ("| OPEN-V paid 45 days late |", "| OPEN-V paid 60 days late |"),
    ],
)
def test_a_changed_figure_is_reported(old, new):
    text = committed_briefing()
    assert old in text
    assert briefing_mismatches(text.replace(old, new, 1))


def test_a_missing_or_repeated_figure_is_reported():
    text = committed_briefing()
    sentence = "The loan balance is $17,000"
    assert any("loan balance: pattern matched 0" in p for p in briefing_mismatches(text.replace(sentence, "The loan balance is unchanged")))
    assert any("loan balance: pattern matched 2" in p for p in briefing_mismatches(text + "\n" + sentence + ".\n"))


def test_rewording_prose_that_carries_no_figure_is_not_reported():
    text = committed_briefing()
    old = "Treat the Grand Exchange collection date as an assumption until the customer confirms it."
    assert old in text
    assert briefing_mismatches(text.replace(old, "Confirm the Grand Exchange collection date with the customer.")) == []


def test_the_committed_outputs_regenerate_unchanged(tmp_path):
    # Line endings are normalised, because a Windows checkout may store CRLF;
    # every other byte must match.
    runpy.run_path(str(GENERATOR))["run"](tmp_path)
    names = ("briefing.md", "monthly.csv", "cash13.csv", "daily-cash.csv", "results.json", "cash-bands.csv",
             "debtor-lateness.csv", "pull-forward.csv", "manifest.json")
    for name in names:
        committed = (OUTPUT / name).read_bytes().replace(b"\r\n", b"\n")
        regenerated = (tmp_path / name).read_bytes().replace(b"\r\n", b"\n")
        assert regenerated == committed, name
    # The manifest hashes every committed output, and only those.
    assert sorted(json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))["files"]) == sorted(names[:-1])
    assert verify_manifest(tmp_path) == []


def test_the_committed_outputs_match_their_manifest_and_a_changed_one_fails(tmp_path):
    assert verify_manifest(OUTPUT) == []
    copy = tmp_path / "output"
    shutil.copytree(OUTPUT, copy, ignore=shutil.ignore_patterns("*.xlsx"))
    (copy / "results.json").write_text((copy / "results.json").read_text(encoding="utf-8").replace("20261002", "20261003"),
                                       encoding="utf-8")
    assert verify_manifest(copy) == ["changed: results.json"]


def test_the_flip_points_are_where_the_funding_conclusion_changes():
    """Each stated delay holds its line and one more day breaks it."""
    module = runpy.run_path(str(GENERATOR))
    points = module["flip_points"]()
    assert points == {"zero": 14, "buffer": 6}
    buffer = sources()["assumptions"]["minimum_cash_buffer"]

    def lowest(days: int) -> float:
        return module["forecast"](delay_days=days)["daily"]["ending_cash"].min()

    assert lowest(points["zero"]) >= 0 > lowest(points["zero"] + 1)
    assert lowest(points["buffer"]) >= buffer > lowest(points["buffer"] + 1)
    # The headline late case sits past both, so the briefing's two claims agree.
    assert points["zero"] < LATE_DAYS


def test_the_briefing_and_workbook_state_the_flip_points(tmp_path):
    module = runpy.run_path(str(GENERATOR))
    sentence = ("stays at or above zero if OPEN-V is up to 14 days late and "
                "stays at or above the assumed $15,000 buffer if OPEN-V is up to 6 days late")
    assert sentence in (OUTPUT / "briefing.md").read_text(encoding="utf-8")
    path = tmp_path / "lumbridge.xlsx"
    module["export_workbook"](path, module["forecast"]())
    note = load_workbook(path)["Assumptions"]["C2"].value
    assert "14 days late" in note and "6 days late" in note and "synthetic" in note.lower()


def test_a_threshold_missed_on_time_is_not_stated_as_met(tmp_path):
    module = runpy.run_path(str(GENERATOR))
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    assumptions = json.loads((data / "assumptions.json").read_text(encoding="utf-8"))
    assumptions["minimum_cash_buffer"] = 20000
    (data / "assumptions.json").write_text(json.dumps(assumptions), encoding="utf-8")
    assert module["flip_points"](data) == {"zero": 14, "buffer": None}
    path = tmp_path / "lumbridge.xlsx"
    module["export_workbook"](path, module["forecast"](data))
    note = load_workbook(path)["Assumptions"]["C2"].value
    assert "is below the buffer even if OPEN-V is on time" in note


def test_a_delay_safe_to_the_search_limit_is_not_stated_as_the_largest():
    clause = runpy.run_path(str(GENERATOR))["_limit_clause"](120, "zero")
    assert clause == "stays at or above zero for any delay to the model's 120-day limit"


def test_the_cash_bands_start_from_the_on_time_forecast_and_follow_their_stated_inputs():
    module = runpy.run_path(str(GENERATOR))
    settings = json.loads((DATA / "cash-bands.json").read_text(encoding="utf-8"))
    bands = sources()["results"]["cash_floor_bands"]
    assert (bands["seed"], bands["runs"], bands["delays"]) == (settings["seed"], settings["runs"], settings["delays"])
    assert bands["floor"]["p10"] <= bands["floor"]["p50"] <= bands["floor"]["p90"] <= sources()["results"]["minimum_daily_cash"]
    paths = pd.read_csv(OUTPUT / "cash-bands.csv", index_col="week")
    assert {p: paths[p].min() for p in ("p10", "p50", "p90")} == bands["floor"]
    # With every range set to 0 days, each run is the on-time forecast, week by week.
    on_time = module["forecast"]()["daily"]["ending_cash"]
    zero = [rule | {"low_days": 0, "high_days": 0} for rule in settings["delays"]]
    flat = module["cash_floor_bands"](
        float(sources()["opening"]["Business Bank Account"]), module["forecast"]()["ledger"], on_time.index[0].date(), on_time.index[-1].date(),
        [module["DelayRange"](**rule) for rule in zero], seed=1, runs=3)
    weekly_lows = on_time.groupby((on_time.index - on_time.index[0]).days // 7).min().tolist()
    assert flat.paths["p50"].tolist() == weekly_lows
    assert flat.summary["floor"]["p50"] == sources()["results"]["minimum_daily_cash"]


def test_the_pull_forward_levers_tie_to_the_late_case_and_the_on_time_forecast():
    results = sources()["results"]
    lateness = pd.read_csv(OUTPUT / "debtor-lateness.csv")
    assert lateness.iloc[0].tolist() == ["OPEN-V", 1, 44000.0, 44000.0, LATE_DAYS, float(LATE_DAYS)]
    assert (lateness.iloc[1:]["late_amount"] == 0).all() and len(lateness) == 8
    levers = pd.read_csv(OUTPUT / "pull-forward.csv")
    assert levers.to_dict("records") == results["pull_forward"]
    # Every lever starts from the late case's trough; OPEN-V collected the full 45 days
    # sooner is on time again, so it reaches the on-time floor.
    assert (levers["floor_before"] == sources()["late_daily"].min()).all()
    on_time = levers[(levers["debtor"] == "OPEN-V") & (levers["days_sooner"] == LATE_DAYS)]
    assert on_time["floor_after"].item() == results["minimum_daily_cash"]
    assert (levers.loc[levers["debtor"] != "OPEN-V", "gain"] == 0).all()
