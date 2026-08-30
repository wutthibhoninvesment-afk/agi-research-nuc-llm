# Round 380 (language C) — predictions, banked BEFORE measuring

Banked 2026-08-30, before running any host/guest comparison, any test, any
count, any sweep. Nothing below has been measured; the reading done first
was of SOURCE only (`whence/values.py::diverge`/`render_contrast`,
`whence/interp.py::b_diverge`/`b_contrast`, `examples/self_eval.lang`'s
v0.30 block, `harness/swe/fuzz.py::BUILTIN_ARITY`).

Task: round 379's next-steps item 5 — the four language(C) items round 378
left open.

  1. `diverge`/`contrast` are the whole of what exemption **E4** still is.
     Decide: leave them permanently exempt with the decision written down,
     or give the guest a structural approximation honest about what it
     approximates.
  2. `GUEST_STEPS_BUDGET = 5000` is a guessed number — the one quantity
     round 378 did not measure.
  3. Round 210's justification comment beside `GUEST_MAX_DEPTH` ("no
     example … comes close to 400 real guest-level call frames") is false,
     and the tail ceiling is missing from the module's "Known, deliberate
     divergences" list.
  4. `show` (v0.29's 37th builtin) is not in the fuzz grammar and has no
     example.

Plan under test: option (b) for item 1 — implement `guest_diverge` /
`guest_contrast` over the `@{v, op, ins}` box graph, on the same terms
v0.30 shipped `steps`/`at`/`blame` (structural sameness, no identity, a
budget instead of a memo, an upper bound that is never a lower one).

## Computed-by-me (narrow bands)

- **P1 — `na is nb` is a pure optimisation, not a rule.** I predict that
  for every node pair reachable in these DAGs, the structural comparison
  the guest can state returns the SAME verdict the host's identity
  short-circuit returns, so removing identity costs work and not
  correctness. Falsifier: a program where host `len(diverge(a, b))`
  differs from a host run with the `na is nb` line deleted. Band: **0**
  such programs across the example corpus and my own hand-built set.

- **P2 — the memo is where identity is actually load-bearing, and only
  for MULTIPLICITY.** The guest, memo-less, will report each origin once
  per lockstep PATH that reaches it. Band: ≥1 hand-built program where
  guest origin count > host origin count with the identical origin
  repeated, and **0** programs where the guest count is lower *for that
  reason*.

- **P3 — the guest can never report a `count`-kind origin.** The host's
  `na.count != nb.count` clause fires only on MERGED nodes and the guest
  never merges (v0.30 divergence 3). Band: I predict **0** cases in the
  existing example corpus where this clause is the sole cause of a host
  origin (so it is not a regression anyone would see), and that I can
  build one by hand in **≤ 6 lines** of Whence.

- **P4 — `contrast` is expressible after the line/count suffixes are
  removed.** `_step_line` is `show ← label[ ×count][  (line N)]`; the
  guest has `show(strip(b))` and `b.op` and neither of the two suffixes.
  Prediction, exact: for `let x = 1 + 2` vs `let y = 1 + 3`, applying
  `re.sub(r"  \(line \d+\)", "", host_text)` makes the host and guest
  contrast strings **byte-identical**, including the `│` column rule and
  the `▶` origin marker. Band: equality, no tolerance.

- **P5 — the path shown will diverge from the host's on a sharing
  program only.** The host's `_pair_path` is BFS = shortest lockstep
  path; the guest's is the path its descent took. Band: identical for
  every program with no shared subgraph; ≥1 hand-built sharing program
  where they differ in length.

- **P6 — the measured corpus max of `guest_walk_steps` is far under
  5000.** Over every `examples/*.lang` this evaluator can run plus the
  guest fuzz corpus, band: **max in [1, 500]**, i.e. the guessed budget
  is ≥ 10x the measured maximum. If it lands above 500 the guess was
  closer to right than the skill's procedure assumes.

- **P7 — `show` is the ONLY host builtin missing from
  `harness/swe/fuzz.py::BUILTIN_ARITY`.** Band: exactly **1** name in
  `interp._make_builtin_table()` (37 names) and not in the table, and it
  is `show`. Round 335 diffed these two sets and closed the gap at 36; a
  38th builtin has not appeared since.

- **P8 — the max real guest-level call depth over the example corpus
  exceeds 400.** Round 377 called round 210's comment "false four times
  over" without publishing the number. Band: the max `st.gd` reached by
  any `examples/*.lang` run under `self_eval.lang` is **> 400**, and at
  least **4** examples exceed it.

- **P9 — no host-side code is needed, again.** Band: **0** lines changed
  in `whence/interp.py`, `whence/values.py`, `whence/parser.py`,
  `whence/lexer.py`. The whole of item 1 lands in
  `examples/self_eval.lang` + tests.

- **P10 — size.** `examples/self_eval.lang` grows by **170–320** lines
  (guest diverge, guest contrast, the n-way forms, the padding/indent
  helpers, and the comment block stating the divergences). Round 378's
  own miss was pricing the code and forgetting the prose, so this band
  is deliberately wide and deliberately includes the comment block.

- **P11 — the atlas number does not move.** Round 378 measured that all
  104 `diverge`/`contrast` cases in `test_v29.py`'s 11 326-case atlas are
  argument-SHAPE cases and all 104 already agree. Band: whole-atlas
  agreement stays **exactly 6 861** and E4's class count stays **0**.
  This change is therefore invisible to the atlas, which is the point of
  round 378's finding that the atlas cannot reach E4's remainder.

- **P12 — at least one of my own new tests will be wrong on first run.**
  Four were in round 378. Band: **≥ 1**, and I will name each in the
  knowledge file rather than quietly fixing it.

- **P13 — E4 retires completely and `test_v30.py::test_diverge_and_
  contrast_are_still_exempt` goes RED.** That is the third mechanism
  round 378 named ("the third time that mechanism has fired") firing a
  fourth time: a pin that asserts an exemption still exists is the thing
  that breaks when it stops existing. Band: exactly **2** existing tests
  in `test_v30.py` go red (`..._are_still_exempt` and
  `..._still_answer_from_the_wrong_history`) and **0** other existing
  tests in the repo go red for that reason.

- **P14 — the fast suite stays green and grows.** Band:
  `languages/whence/run_tests_fast.sh` ends **≥ 1630 passed, 0 failed**
  (it was 1 612 at round 379), and `python3 run.py
  examples/self_eval.lang` reports **0 failed** with ≥ 150 checks (142 at
  round 378).

## What would make this round a failure

Shipping a `guest_diverge` that silently returns a SHORT list — the exact
failure mode v0.30's budget exists to prevent — or writing a fourth
exemption's worth of prose instead of a decision. If option (b) turns out
not to be reachable, the round must say so and ship option (a) with the
reason, not leave E4 undecided for a third round.
