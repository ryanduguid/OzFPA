#!/usr/bin/env bash
# Runs the 4 public joined fixture workflows from the checkouts under sources/,
# or appends their summaries to the job summary. Called by joined-fixtures.yml
# (pinned companions) and joined-fixtures-heads.yml (companions at main).
#
#   joined-fixtures.sh run      run every workflow; fail if any failed
#   joined-fixtures.sh summary  append each workflow's summary.md
set -uo pipefail

workflows=(close-forecast quarter job-cash grant-cash)
results="$RUNNER_TEMP/public-fixtures"

case "${1:-}" in
  run)
    fixture_status=0
    for workflow in "${workflows[@]}"; do
      # Only the grant route reads the grant workpapers, which the pipeline checkout holds.
      grants=()
      if [ "$workflow" = grant-cash ]; then
        grants=(--grants "$GITHUB_WORKSPACE/sources/accounting-review-pipeline/apps/grant-acquittal-workpapers")
      fi
      python sources/accounting-review-pipeline/packages/monthly-close-control-plane/examples/utility_workflows.py \
        --workflow "$workflow" \
        --fpa "$GITHUB_WORKSPACE/sources/au-fpa-pack" \
        --accounting "$GITHUB_WORKSPACE/sources/australian-accounting" \
        "${grants[@]}" \
        --output "$results/$workflow/results" \
        --environment-root "$results/$workflow/environments" || fixture_status=1
    done
    exit "$fixture_status"
    ;;
  summary)
    for workflow in "${workflows[@]}"; do
      summary="$results/$workflow/results/summary.md"
      if [ -f "$summary" ]; then
        cat "$summary" >> "$GITHUB_STEP_SUMMARY"
      fi
    done
    ;;
  *)
    echo "usage: joined-fixtures.sh run|summary" >&2
    exit 2
    ;;
esac
