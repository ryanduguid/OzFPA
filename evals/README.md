# Plugin eval cases

Each case is a prompt for an agent running this plugin, with regular-expression graders
for the answer block the prompt asks for. Grading needs no model or API key.

These cases are written by the author against the author's own answer key. A pass shows
that an agent reproduced the worked example's figures; it is not an independent
evaluation and says nothing about time saved.

| Case | Source | Checks |
| --- | --- | --- |
| [`lumbridge-cash-trough.json`](lumbridge-cash-trough.json) | [Lumbridge trial](../examples/lumbridge-services/TRIAL.md), steps 2 and 4 | Base and delayed-receipt cash troughs, first negative day, October closing cash, profit unchanged |

## Run a case

1. Copy the repository and delete every path in the case's `withhold` list from the copy,
   so the agent cannot read the answer key or the graders.
2. Install the plugin in the agent, open the copy, and give it the case's `prompt`
   exactly. Record the agent, model and date.
3. Save the agent's final reply as `reply.txt` and grade it from this repository:

```bash
python evals/grade.py evals/lumbridge-cash-trough.json reply.txt
```

The grader prints `PASS` or `FAIL` for each check and exits 0 only when all pass.
`tests/test_plugin_eval.py` checks that the graders accept the answers the generated
model computes and refuse each wrong answer it names.
