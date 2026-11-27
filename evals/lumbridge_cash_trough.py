# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Plugin eval case: the Lumbridge cash trough (TRIAL.md, First run steps 2 and 4).

    python evals/lumbridge_cash_trough.py --prompt     print the prompt for the agent
    python evals/lumbridge_cash_trough.py < reply.txt  grade the agent's final reply

Grading prints PASS or FAIL for each grader and exits 0 only when every grader matches.
It needs no model or API key. The graders encode the author's own answer key: this is
an author-built check, not an independent evaluation.
"""

import re
import sys
from typing import TextIO

# Delete these from the agent's copy of the repository so it cannot read the answers.
WITHHOLD = ("examples/lumbridge-services/REVIEWER-KEY.md", "evals/")

PROMPT = (
    "Work in examples/lumbridge-services, a fabricated NSW services business, using its data, "
    "its workbook or the model that generates the workbook. Do not open REVIEWER-KEY.md or "
    "anything under evals/. (1) Find the lowest daily closing cash balance in the base "
    "forecast and the first date it occurs. (2) Delay the receipt of invoice OPEN-V by 45 "
    "calendar days, the workbook's receipt-delay control. Find the first date daily closing "
    "cash is negative, the lowest daily closing cash and the first date it occurs, and "
    "October closing cash. (3) Say whether the delay changes profit before income tax. "
    "Explain your reasoning, then end your reply with exactly these 5 lines, amounts in "
    "dollars with a leading minus sign for a negative amount and dates as YYYY-MM-DD:\n"
    "LOWEST_BASE: <amount> on <date>\n"
    "FIRST_NEGATIVE_DELAYED: <date>\n"
    "LOWEST_DELAYED: <amount> on <date>\n"
    "OCTOBER_CLOSE_DELAYED: <amount>\n"
    "PROFIT_CHANGED: <yes or no>"
)

_NEGATIVE = r"(?:-\$?{0}(?:\.00)?|\(\$?{0}(?:\.00)?\))"
GRADERS = (
    ("base trough and its date",
     re.compile(r"(?mi)^LOWEST_BASE:[ \t]*\$?16,?800(?:\.00)?[ \t]+on[ \t]+2026-10-07[ \t]*$")),
    ("first negative day after the delay",
     re.compile(r"(?mi)^FIRST_NEGATIVE_DELAYED:[ \t]*2026-10-28[ \t]*$")),
    ("delayed trough and its date",
     re.compile(r"(?mi)^LOWEST_DELAYED:[ \t]*" + _NEGATIVE.format("25,?160") + r"[ \t]+on[ \t]+2026-11-06[ \t]*$")),
    ("delayed October closing cash",
     re.compile(r"(?mi)^OCTOBER_CLOSE_DELAYED:[ \t]*" + _NEGATIVE.format("11,?960") + r"[ \t]*$")),
    ("profit unchanged by the delay",
     re.compile(r"(?mi)^PROFIT_CHANGED:[ \t]*no[ \t]*$")),
)


def grade(reply: str) -> list[tuple[str, bool]]:
    """Return each grader's name and whether its pattern matches the reply."""
    return [(name, pattern.search(reply) is not None) for name, pattern in GRADERS]


def main(argv: list[str], stdin: TextIO) -> int:
    if argv == ["--prompt"]:
        print(PROMPT)
        return 0
    if argv:
        print("usage: lumbridge_cash_trough.py [--prompt] < reply.txt", file=sys.stderr)
        return 2
    results = grade(stdin.read())
    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(passed for _, passed in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin))
