#!/bin/sh
# Round 405: the owed probe batch, as 4 SEPARATE invocations.
# Design: runs A,B,C at --repeats 1 and run D at --repeats 2 (5 probes/case).
# Why not round 393's 3 x --repeats 2: see knowledge/round-405-*.md. At the
# ICC that round measured (0.333), 3x1+1x2 buys the SAME 4.50 effective
# draws per case as 3x2 for 205 probes instead of 246. The one --repeats 2
# run is what keeps the within-run term (and therefore ICC) estimable at
# all: trigger_eval.run_variance drops any case whose every run gave one
# probe (`N == len(d)`).
cd /home/pgain/agi-research-nuc-llm || exit 1
CASES=$(cat state/round-405/batch-cases.txt)
# wait for run A (already launched) to finish
while pgrep -f "round-405-runA.json" >/dev/null 2>&1; do sleep 5; done
for spec in "B 1" "C 1" "D 2"; do
  set -- $spec
  T=$1; R=$2
  echo "=== run $T --repeats $R  $(date -u +%FT%TZ) ==="
  timeout 1500 python3 skills/skill-authoring/scripts/trigger_eval.py \
    skills/trigger-cases.json --skills skills \
    --mode native --model sonnet --protocol strict \
    --repeats "$R" --concurrency 3 --only "$CASES" \
    --json "state/trigger-eval/round-405-run$T.json" \
    > "state/round-405/logs/run$T.log" 2>&1
  echo "run $T exit=$? $(date -u +%FT%TZ)"
done
echo "BATCH DONE $(date -u +%FT%TZ)"
