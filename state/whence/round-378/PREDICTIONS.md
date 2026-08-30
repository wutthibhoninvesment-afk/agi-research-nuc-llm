# Round 378 (language C) — predictions, banked BEFORE measuring

Banked 2026-08-30, before running any host/guest comparison, any test, or
any count. Task: **E4** — `self_eval.lang` answers `steps`/`at`/`blame`
from the HOST provenance of the guest's payload (i.e. from the evaluator's
own execution) instead of from the guest box graph it already builds.
Round 374 item 1 / round 375 item 5 / round 377 item 4's neighbourhood.

Plan under test: implement `steps`/`at`/`blame` at GUEST level over the
`@{v, op, ins}` box graph; leave `diverge`/`contrast` delegating (they are
identity- and layout-bound at the host: `diverge` memoises on `(id(na),
id(nb))` and short-circuits on `na is nb`; `render_contrast` column-aligns
with box-drawing characters).

## Computed-by-me (narrow bands)

- **P1 — the two E4 pins become EXACT.** `let x = 1 + 2 / len(steps(x))`
  is 4 on the host and 284 in the guest today. After the fix the guest
  says **exactly 4**, and `len(blame(1 / 0))` says **exactly 1** (host: 1).
  Band: 4 and 1, no tolerance. Mechanism if it misses: the guest's box
  graph has a node the host's DAG does not (or vice versa) even for a
  two-literal program.

- **P2 — `Prov.label()` is invertible by splitting at the FIRST space for
  the ops the guest actually builds.** Over the guest's own label
  vocabulary (`let x`, `call f`, `arg n`, `if took then-branch`, `+`,
  `literal`, `field .x`, …) I predict **0** labels where splitting at the
  first space yields an `op` the host would not have used, EXCLUDING miss
  nodes. For MISS nodes I predict the split is WRONG, because
  `mk_miss` stores the whole reason sentence as `detail` and the guest
  box's label carries only the op (`"/"`, not `"/ division by zero"`) —
  so guest `detail` will be `""` where the host has a sentence. Band:
  ≥1 miss-node case where host `detail` is non-empty and guest `detail`
  is empty.

- **P3 — the guest walk over-reports where the host shares.** The host
  `walk_steps` dedups by `id`; Whence has only structural `==`, so the
  guest cannot. I predict I will find **at least one** program in the
  existing example/test corpus where guest `len(steps(x))` >
  host `len(steps(x))` purely from re-visiting a shared node, and
  **zero** programs where the guest count is LOWER for that reason.

- **P4 — no new host-side code is needed.** The fix lands entirely in
  `examples/self_eval.lang` plus tests; `whence/interp.py`,
  `whence/values.py`, `whence/parser.py`, `whence/lexer.py` unchanged.
  Band: 0 lines changed in those four files.

- **P5 — `show` (v0.29's 37th builtin, round 374) is load-bearing here.**
  The guest step record's `show` field is `show_payload(node.value)` at
  the host. Before v0.29 no Whence expression could produce it. I predict
  the guest `show` field is byte-identical to the host's for the two pin
  programs, and that this is the first non-`self_eval.lang`-internal use
  of the `show` builtin (round 375 item 7: "`show` has exactly one
  caller").

- **P6 — E4's corpus count in `tests/test_v29.py` goes from 3 to 0 for
  `steps`/`at`/`blame` and stays > 0 only if `diverge`/`contrast` cases
  are in the 3.** I predict the 3 cases are `steps`/`at`/`blame`-shaped
  and the count goes to **0**, which makes
  `test_the_exemption_classes_are_the_measured_sizes`'s `>= 3` assertion
  RED — the same "each exemption is load-bearing" mechanism that retired
  E3 in v0.28 and the two rendering exemptions in v0.29. Band: that
  assertion fails on first run after the fix.

## Machine-state (both branches)

- **P7 — cost.** `self_eval.lang` grows by 90–160 lines. The guest fast
  tier (`test_self_eval.py`) is dominated by re-parsing the library once
  per program (0.11 s/build, measured by round 377), so a 4–6 % source
  growth costs 4–6 % of that, i.e. under 0.01 s per guest program. I
  predict the fast-tier wall clock (`run_tests_fast.sh`) moves by
  **less than 15 %** on this `nproc`=1 box, warm; cold (first run,
  no `__pycache__`) I predict under 25 %.

- **P8 — the exponential.** A guest box graph with sharing walked without
  dedup is exponential in depth. I predict **no** program in the existing
  corpus hits the budget I add (5 000 nodes), and that I can write a
  4-line program that does.

## Base rates on my own process

- **P9** — at least one of my new tests is wrong on its first run.
- **P10** — the full slow tier will NOT be run this round (round cap
  3 300 s, `nproc`=1, and `test_v29.py`'s sweep alone is 11 326 cases ×
  2 engines). It will be labelled NOT RUN, not implied green.
- **P11** — I will pay at least part of the owed D-013 debt (banks 132 /
  362 / 368, owner language(C), deferred by three consecutive rounds) —
  specifically I predict I score **368 and 362** from committed artifacts
  and leave **132** unscorable-as-posed against a v0.30 tree.
- **P12** — the round's edit will make at least one EXISTING test red for
  a reason that is correct (an exemption retiring), and at least one red
  for a reason that is my bug.

## Amendments

(none yet — anything added here must be timestamped and must precede the
relevant measurement)
