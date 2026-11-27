# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: Apache-2.0

"""Grade an agent's reply to an eval case with the case's regular expressions.

Usage: python evals/grade.py <case.json> <reply.txt>

Prints PASS or FAIL for each grader and exits 0 only when every grader matches.
Grading needs no model or API key.
"""

import json
import re
import sys
from pathlib import Path


def grade(case: dict[str, object], reply: str) -> list[tuple[str, bool]]:
    """Return each grader's name and whether its pattern matches the reply."""
    graders = case["graders"]
    if not isinstance(graders, list) or not graders:
        raise ValueError("the case has no graders")
    return [(str(grader["name"]), re.search(str(grader["pattern"]), reply) is not None)
            for grader in graders]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: grade.py <case.json> <reply.txt>", file=sys.stderr)
        return 2
    case = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    results = grade(case, Path(argv[1]).read_text(encoding="utf-8"))
    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 0 if all(passed for _, passed in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
