# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""The Lumbridge eval case: its graders accept the model's answers and refuse wrong ones."""
import json
import re
import runpy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "evals" / "lumbridge-cash-trough.json"
CASE = json.loads(CASE_PATH.read_text(encoding="utf-8"))
GRADER: dict[str, Any] = runpy.run_path(str(ROOT / "evals" / "grade.py"))
MODEL = ROOT / "examples" / "lumbridge-services" / "models" / "generated" / "lumbridge.py"


def money(value: float) -> str:
    return f"{'-' if value < 0 else ''}${abs(value):,.0f}"


def model_reply() -> str:
    """The answer block, built from the generated model rather than the reviewer key."""
    forecast = runpy.run_path(str(MODEL))["forecast"]
    base, late = forecast(), forecast(delay_days=45)
    base_daily, late_daily = base["daily"]["ending_cash"], late["daily"]["ending_cash"]
    first_negative = late_daily[late_daily < 0].index[0]
    changed = not base["monthly"]["Profit before tax"].equals(late["monthly"]["Profit before tax"])
    return "\n".join([
        "Working shown above.",
        f"LOWEST_BASE: {money(base_daily.min())} on {base_daily.idxmin().date()}",
        f"FIRST_NEGATIVE_DELAYED: {first_negative.date()}",
        f"LOWEST_DELAYED: {money(late_daily.min())} on {late_daily.idxmin().date()}",
        f"OCTOBER_CLOSE_DELAYED: {money(late['monthly']['Closing cash'].iloc[0])}",
        f"PROFIT_CHANGED: {'yes' if changed else 'no'}",
    ])


def test_the_model_answer_passes_every_grader() -> None:
    results = GRADER["grade"](CASE, model_reply())
    assert [name for name, _ in results] == [grader["name"] for grader in CASE["graders"]]
    assert all(passed for _, passed in results)


def test_negative_amounts_may_be_written_in_brackets() -> None:
    reply = model_reply().replace("-$25,160", "($25,160)").replace("-$11,960", "($11,960.00)")
    assert all(passed for _, passed in GRADER["grade"](CASE, reply))


@pytest.mark.parametrize(("wrong", "right", "failed"), [
    # Reading only December's closing cash misses the trough the case is about.
    ("LOWEST_BASE: $16,800", "LOWEST_BASE: $67,320", "base trough and its date"),
    ("on 2026-11-06", "on 2026-11-07", "delayed trough and its date"),
    ("LOWEST_DELAYED: -$25,160", "LOWEST_DELAYED: $25,160", "delayed trough and its date"),
    ("FIRST_NEGATIVE_DELAYED: 2026-10-28", "FIRST_NEGATIVE_DELAYED: 2026-11-06",
     "first negative day after the delay"),
    ("OCTOBER_CLOSE_DELAYED: -$11,960", "OCTOBER_CLOSE_DELAYED: $32,040", "delayed October closing cash"),
    ("PROFIT_CHANGED: no", "PROFIT_CHANGED: yes", "profit unchanged by the delay"),
    # An answer buried mid-line, not given as the requested line, does not count.
    ("PROFIT_CHANGED: no", "So PROFIT_CHANGED: no", "profit unchanged by the delay"),
])
def test_a_wrong_answer_fails_its_grader(wrong: str, right: str, failed: str) -> None:
    reply = model_reply()
    assert wrong in reply
    results = dict(GRADER["grade"](CASE, reply.replace(wrong, right)))
    assert [name for name, passed in results.items() if not passed] == [failed]


def test_the_prompt_withholds_the_key() -> None:
    prompt = CASE["prompt"]
    assert CASE["independent"] is False
    assert "examples/lumbridge-services/REVIEWER-KEY.md" in CASE["withhold"]
    assert "Do not open REVIEWER-KEY.md or anything under evals/" in prompt
    for grader in CASE["graders"]:
        for answer in re.findall(r"\d{4}-\d{2}-\d{2}|\d{2},\?\d{3}", grader["pattern"]):
            assert answer.replace(",?", ",") not in prompt
            assert answer.replace(",?", "") not in prompt


def test_a_case_without_graders_is_refused() -> None:
    with pytest.raises(ValueError, match="no graders"):
        GRADER["grade"]({"graders": []}, "anything")


def test_main_prints_each_result_and_exits_on_the_outcome(tmp_path: Path,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    reply = tmp_path / "reply.txt"
    reply.write_text(model_reply(), encoding="utf-8")
    assert GRADER["main"]([str(CASE_PATH), str(reply)]) == 0
    assert capsys.readouterr().out.splitlines() == [f"PASS {g['name']}" for g in CASE["graders"]]
    reply.write_text(model_reply().replace("PROFIT_CHANGED: no", "PROFIT_CHANGED: yes"), encoding="utf-8")
    assert GRADER["main"]([str(CASE_PATH), str(reply)]) == 1
    assert "FAIL profit unchanged by the delay" in capsys.readouterr().out.splitlines()
    assert GRADER["main"]([]) == 2
    assert "usage" in capsys.readouterr().err
