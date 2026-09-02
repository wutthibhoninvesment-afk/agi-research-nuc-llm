# Round 458 (language C) — predictions, banked BEFORE measuring (D-013)

**Subject.** Round 456's next-step 2, verbatim:

> **The repo's true deepest value, 20 000, has never been re-derived by
> anything.** Decision 53 states it — a generated killer's runaway recursion
> whose unwind builds one record per frame — and the number came from
> reading a test, not from an instrument. The allocation census could take
> it directly now (it needs no root set and no corpus), and round 452's
> other named residual, *"a census over the test corpus has not been run"*,
> is the same job. language(C).

**Basis, read before predicting (all constants, no measurement):**

* `whence/interp.py:442` — `Interpreter.DEFAULT_MAX_DEPTH = 20000`, and
  `interp.py:619` `def __init__(self, out=None, max_depth=DEFAULT_MAX_DEPTH, ...)`.
* `SPEC.md` decision 53, "Why a deeper cap and not no cap": *"The deepest
  value this repo builds anywhere is not 14 — it is **20000**, built by
  `tests/test_generated_killers.py`'s `test_kill_values_py_139_arith_120`
  ... a runaway recursion whose unwind builds one record per frame, so the
  value's depth is exactly `DEFAULT_MAX_DEPTH`."*
* `tests/test_generated_killers.py:14` and
  `tests/test_generated_killers_r29.py:14` — both suites' `canonical()`
  takes `max_depth=500` as its DEFAULT and `run(src)` passes no override,
  so every generated killer executes at `max_depth=500`.
* `depthcensus.py` — the allocation census measures D and N in the `Prov`
  constructor, has no root set, and both cross-check walks (`depth_of`,
  `_payload_size`) are iterative, so a 20 000-deep value is measurable
  without a host-stack limit.
* `languages/whence/tests/` holds 62 `test_*.py` files. Whence source is
  embedded in them as Python string literals; there is no `.lang` file in
  the test tree.

---

## P1 — the cited test's value is 500 deep, not 20 000

`test_kill_values_py_139_arith_120` runs `wrap(1)` under `max_depth=500`.
D of the resulting `rec` payload will be **500**, and I will accept 499-501
as "held" only if the off-by-one has a named cause. It will NOT be 20 000.
Decision 53's sentence is therefore about a program the repo never runs at
that depth.

## P2 — at the DEFAULT depth the number is right

The same source run through a plain `Interpreter()` (i.e. `max_depth =
DEFAULT_MAX_DEPTH = 20000`) builds a value of depth **20 000** exactly.
So decision 53's number is reachable by the language and is not reached by
the corpus that decision 53 cites for it.

## P3 — the test corpus, sized

An AST harvest over `tests/*.py` that keeps every string literal handed to a
program runner and that lexes+parses as Whence will find between **900 and
1400** distinct programs. (The two generated-killer files alone are large.)

## P4 — the test corpus does NOT beat the examples corpus on depth

Max ALLOC depth over the harvested test corpus will be **below 1201**, so
the repo's deepest actually-built value stays `self_eval.lang`'s 1201 and
the champion the test corpus contributes is the `wrap` killer at ~500.
(Drafted first as the opposite claim — "the test corpus beats 1201" — and
corrected here before any measurement, because P1 already fixes the killer
at 500 and 500 < 1201. The draft is left named rather than deleted: a
prediction file that hides its own reversal is not a bank.)

## P5 — no disagreement

`alloc_agrees` will be true for every harvested program that runs, i.e. the
constructor arithmetic and the independent re-walks agree on every champion,
as they did on the examples corpus.

## P6 — the width bound is reached in the test corpus too

At least one harvested program will build a value whose tree unfolding N
exceeds `FULL_SHOW_NODES = 20000`. Predict between 1 and 40 such programs.

## P7 — nothing hits an instrument cap

No harvested program will set `alloc_capped` (the 4 000 000-cell /
200 000-buffer caps) or `built_truncated` (the 3 000 000-node walk budget).

## P8 — cost

Censusing the whole harvested test corpus, allocation census on, takes
between **300 and 900 s** of wall clock on this 1-core box.

## P9 — programs that do not run

Between **2% and 10%** of harvested programs will fail to complete (parse
error at Whence level after passing the harvester's own parse gate, a host
exception, or a `RecursionError`). Predict the dominant failure is a
deliberate parse-error fixture.

## P10 — the second residual

Round 452's residual sentence *"a census over the test corpus has not been
run"* is closed by this round and the answer changes no constant:
`FULL_SHOW_NEST` stays 24 and `FULL_SHOW_NODES` stays 20000.

---

Scoring goes in `knowledge/round-458-*.md` and in the round's
research-state entry. Misses are reported as misses.
