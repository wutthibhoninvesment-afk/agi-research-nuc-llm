---
name: verdict-carries-its-threshold
description: Use when two runs, arms, snapshots or CI results are about to be compared through a stored pass/fail, fired/not-fired or over/under boolean rather than through the number it was derived from - an A/B whose exemption "converted 100%", a lint/coverage/perf gate that "stopped firing", two benchmark reports diffed by their verdict columns, or any paired diff of recorded verdicts. Symptoms: a boolean stored beside the threshold it was compared against; a within-run uniformity check (mixed/consistent/stable) read as an across-run agreement check; a conversion or improvement rate with no statement that the limit, cap, budget, tolerance or ceiling held still; rows dropped from a pairing because one side has no verdict; a knob change and a constant edit landing in the same commit. Covers reading the threshold off both sides, separating a declared knob move from an undeclared one so the guard does not cry wolf, and counting the unpaired rows instead of skipping them.
---

# A verdict is a comparison, and the other operand is data too

A stored `fired: true` is not an observation. It is the result of
`demand > threshold`, and only one of those two numbers usually survives into
the report. Diff two runs by their verdicts and you are comparing
`demand_a > threshold_a` against `demand_b > threshold_b` — a claim about the
arm only if `threshold_a == threshold_b`, which nothing checked.

This is not the same failure as an unpinned dependency or a dirty worktree.
The instrument can be honest, the data complete, the arms paired seed by seed,
and the answer still wrong, because the *meaning of the column* moved between
them.

## The instance this came from

Round 401 of this program paired a fuzzing sweep run in round 389 against one
run twelve rounds later and asked what raising `max_depth` and `timeout_s`
had done. The `R-CAP` row of the result reads:

```json
"R-CAP": {"fired_a": 125, "fired_b": 0, "converted": 125, "converted_pct": 100.0}
```

Every render-cap exemption in a 360-seed corpus, gone. Neither knob touches
that site. What happened is that round 389's own landing commit raised
`RENDER_PAIR_CAP` from 6 to 24 — on a good measurement, that full pair
coverage was free — *after* its two arms had been measured. The 125
"conversions" are that constant edit, seen through a boolean.

The threshold was on every row the whole time (`sites["R-CAP"]["threshold"]`:
6 in both old arms, 24 in the new one). The comparator read `fired` and never
read the field beside it.

## Why the guards that existed did not fire

Two neighbouring checks were in place and both were *correct*:

* `mixed_instrument` asks whether one arm changed **mid-sweep**. It is a
  within-arm check, so it reports `false` exactly when each arm is internally
  uniform — which is the case where the two arms can still be uniformly
  **different from each other**. It is the reassuring-looking field, and it is
  the one with a definite value.
* `arms_share_instrument` is the right question, but it returns `null` for any
  arm recorded before the stamping was built — and the old arms were.

So the JSON said `mixed_instrument: false`, `arms_share_instrument: null`, and
a reader taking the first as the answer got "no problem". **An unknown that
reads as falsy, sitting next to a reassuring boolean, is worse than no field.**

## When to use

Reach for this the moment a sentence of the form *"X stopped firing"*,
*"N of N converted"*, *"the gate is green now"* or *"that category is at
zero"* is about to be attributed to a change, and the evidence is a column of
stored verdicts from two different runs. It applies whether the verdicts come
from a fuzzing sweep, a lint report, a coverage gate, a perf budget, a
flaky-test dashboard or a CI matrix — anywhere a threshold comparison was
performed once, at record time, and the comparison's other operand was left
behind.

It does **not** apply when the two runs share one recorded, verified
instrument and the only question is whether the difference is large enough to
believe; that is a question about power, not about meaning.

## Steps

1. **Find the threshold on the row.** For each compared column, ask what
   number the boolean was computed against and whether the record kept it.
   If it did not, that is the first bug — fix the recorder before the
   comparator.
2. **Collect the distinct threshold values per side**, not one sampled row:
   a mid-run edit shows up as two values in one arm.
3. **Classify a move as declared or undeclared.** If the threshold *is* the
   knob under test, moving it is the experiment, not a confound. In the
   instance above, one site's threshold literally is `max_depth`, so a
   depth-ceiling A/B moves it by construction; the first version of this guard
   flagged all four pairs including one with a byte-identical instrument
   stamp, which is how a guard gets switched off by the next round that trips
   it. Only an **undeclared** move is a confound.
4. **Compare instrument identity across arms, three-valued.** `true` / `false`
   / `unknown`, and never let `unknown` collapse into either. An arm made only
   of unstamped rows is `unknown`, not "matching".
5. **Count what the pairing dropped.** A row with no verdict on one side is
   skipped, and that is the population an arm change most likely moved. In the
   instance above, one seed errored out in the old arm, was recovered by the
   very timeout raise under test, and then *fired* — so the site's own table
   said four firing seeds while the pairing said three, and `new_fires` read
   `0`.
6. **Print the comparability verdict above the numbers.** The evidence had
   been in the JSON for twelve rounds; what it lacked was a line a reader
   meets before the conversion rates.

## Pitfalls

* **Incomparable is not "different".** A forward check in round 407 found two
  arms whose subject tree and comparator had both moved, and every site verdict
  was nevertheless identical. The verdict is *unattributable*, not wrong.
* **Do not suppress the confounded number.** Report it and label it. Blanking
  `converted_pct` hides the evidence that the threshold moved.
* **A single instrument hash is not enough.** In that same forward check the
  oracle file's digest was byte-identical across the two arms while the subject
  under test and the site registry had both changed. Per-part digests caught
  it; the single hash said "same instrument".
* **The knob exemption must be tied to a recorded knob**, not to the
  threshold's shape. If the site's threshold moved 500 -> 5000 but the arm's
  `max_depth` did *not* change, that is undeclared and must still fire.
* **Sites with no threshold** (pure predicates) must classify as "did not
  move" by construction, not by an accident of empty-set comparison.

## Verification

```bash
# the comparator, on the archive it was built for
python3 -m harness.swe.exemptmap abreport \
  --a state/swe/round-389/armB-5000.jsonl \
  --b state/swe/round-401/armC-5000-12.jsonl
# expect: COMPARABLE: NO, and R-CAP flagged with threshold [6] -> [24]

# the pair whose arms really do share an instrument
python3 -m harness.swe.exemptmap abreport \
  --a state/swe/round-401/armD-500-stamped.jsonl \
  --b state/swe/round-401/armD-5000-stamped.jsonl
# expect: COMPARABLE: yes, and T-SPACE listed as "by design ... the arm's own
# max_depth knob" -- the cry-wolf case, not flagged

python3 -m pytest -q harness/tests/test_swe_abconfound.py   # 17 passed
```

A generalisation of this check for any paired-verdict report needs three
fields the report probably does not have yet: the threshold each side used,
a three-valued instrument-identity verdict, and the count of rows the pairing
could not pair. Add them before adding a fourth statistic.
