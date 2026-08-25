#!/bin/zsh
# Round 110 sequential campaign chain (one CPU-bound job at a time; every
# step prints its own exit code — rule 17). Logs: state/whence/round-110/.
W=/Users/jaby/agi-research/languages/whence
H=/Users/jaby/agi-research/harness
S=/Users/jaby/agi-research/state/whence/round-110
export PYTHONPATH=$H
step() { echo "== $1"; }
step "whence suite"; perl -e 'alarm 500; exec @ARGV' python3 -m pytest -q $W/tests -p no:cacheprovider --no-header > $S/whence-tests.log 2>&1; echo "exit=$?"; tail -1 $S/whence-tests.log
step "reserve probe (limit 6000, examples + 10 deep templates + 30 fuzz)"; python3 $W/bench/reserve_probe.py --examples -n 30 > $S/reserve-probe.log 2>&1; echo "exit=$?"; tail -1 $S/reserve-probe.log
for seed in 123 124; do step "host fuzz seed $seed n=400 (default limit)"; python3 -m swe.fuzz --seed $seed -n 400; echo "exit=$?"; done
for seed in 125 126; do step "host fuzz seed $seed n=400 --limit 6000"; python3 -m swe.fuzz --seed $seed -n 400 --limit 6000; echo "exit=$?"; done
step "oracle fuzz seed 127 n=300 (6 oracles)"; python3 -m swe.oracles --seed 127 -n 300 --json $S/oracles-127.json; echo "exit=$?"
step "oracle fuzz seed 128 n=300 --limit 6000"; python3 -m swe.oracles --seed 128 -n 300 --limit 6000 --json $S/oracles-128.json; echo "exit=$?"
for seed in 129 130; do step "guest seed $seed n=200"; python3 -m swe.guest --seed $seed -n 200 --json $S/guest-$seed.json; echo "exit=$?"; done
for seed in 4 5; do step "ref_diff fuzz seed $seed n=300 limit 6000"; python3 $W/bench/ref_diff.py --fuzz $seed -n 300 > $S/ref-fuzz-$seed.log 2>&1; echo "exit=$?"; tail -1 $S/ref-fuzz-$seed.log; done
step "harness suite"; perl -e 'alarm 1200; exec @ARGV' python3 -m pytest -q $H/tests -p no:cacheprovider --no-header > $S/harness-tests.log 2>&1; echo "exit=$?"; tail -1 $S/harness-tests.log
echo "campaigns done"
