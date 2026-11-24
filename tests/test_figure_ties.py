# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Tying the figures in generated prose to their sources. The text is invented."""

from __future__ import annotations

from decimal import Decimal

from pyfpa.analysis.figures import FigureTie, figure_problems

TEXT = "Cash is ($1,250.50) on 6 November.\nRevenue is $60,000 from 12 jobs. See P10.\n"


def ties() -> list[FigureTie]:
    return [
        FigureTie("trough", r"Cash is (\(?\$[\d,.]+\)?) on (\d+ \w+)", (-1250.5, "6 November")),
        FigureTie("revenue", r"Revenue is (\$[\d,]+) from (\d+) jobs", (Decimal("60000"), 12)),
        FigureTie("label", r"See (P10)\.", ("P10",)),
    ]


def test_every_figure_tied_gives_no_problems():
    assert figure_problems(TEXT, ties()) == []


def test_a_changed_figure_is_reported():
    assert figure_problems(TEXT.replace("$60,000", "$60,001"), ties()) == ["revenue: text $60,001, source 60000"]
    assert figure_problems(TEXT.replace("12 jobs", "13 jobs"), ties()) == ["revenue: text 13, source 12"]
    assert figure_problems(TEXT.replace("6 November", "7 November"), ties()) == ["trough: text 7 November, source 6 November"]
    assert figure_problems(TEXT.replace("($1,250.50)", "$1,250.50"), ties()) == ["trough: text $1,250.50, source -1250.5"]


def test_money_ties_to_the_cent_from_the_source_as_written():
    tie = [FigureTie("fee", r"fee (\$[\d,.]+)", (1.005,))]
    assert figure_problems("fee $1.01", tie) == []
    assert figure_problems("fee $1.00", tie) == ["fee: text $1.00, source 1.005"]
    assert figure_problems("fee $1", [FigureTie("fee", r"fee (\$[\d,.]+)", (1.004,))]) == []


def test_a_figure_no_tie_covers_is_reported_with_its_line():
    text = TEXT + "Margin rose to $9,999.\n"
    assert figure_problems(text, ties()) == ["untied figure '9,999' on line 3"]


def test_digits_a_pattern_matches_outside_its_groups_are_untied():
    tie = [FigureTie("revenue", r"FY\d+ revenue (\$[\d,]+)", (60000,))]
    assert figure_problems("FY2027 revenue $60,000", tie) == ["untied figure '2027' on line 1"]
    literal = [FigureTie("revenue", r"FY2026 revenue (\$[\d,]+)", (60000,))]
    assert figure_problems("FY2026 revenue $60,000", literal) == ["untied figure '2026' on line 1"]


def test_an_optional_group_that_did_not_match_is_reported():
    assert figure_problems("jobs", [FigureTie("jobs", r"jobs(?: (\d+))?", (12,))]) == ["jobs: text None, source 12"]


def test_a_missing_or_repeated_tie_is_reported():
    assert figure_problems(TEXT.replace("See P10.", "See below."), ties()) == ["label: pattern matched 0 times"]
    problems = figure_problems(TEXT + "See P10.\n", ties())
    assert problems == ["label: pattern matched 2 times", "untied figure '10' on line 2", "untied figure '10' on line 3"]


def test_a_tie_with_the_wrong_number_of_sources_is_reported():
    assert figure_problems("12 jobs", [FigureTie("jobs", r"(\d+) jobs", (12, 13))]) == ["jobs: 1 figures, 2 sources"]


def test_text_that_is_not_a_number_never_ties_a_numeric_source():
    assert figure_problems("about jobs", [FigureTie("jobs", r"(\w+) jobs", (12,))]) == ["jobs: text about, source 12"]
