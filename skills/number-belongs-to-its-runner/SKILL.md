---
name: number-belongs-to-its-runner
description: Use when a doc, comment, changelog, design decision or commit cites a NAMED test, benchmark, script or fixture as the source of a number - "20000, built by test_kill_values_py_139_arith_120", "p99 is 40ms, see bench_hot_path". Symptoms: a number quoted from a test's NAME or ASSERTION rather than from a run; a harness helper carrying a default (max_depth, timeout, iterations, warmup, batch, tolerance) the cited artefact never overrides; one source text giving different numbers under two runners; a bound called "the real upper bound" that only bounds one construction path; a claim something "has never been measured" written in the same tree as the test measuring it. Covers running the cited artefact under ITS OWN runner, reading the runner's parameters off the AST, proving the number tracks the parameter at three or more points so it is a law not a coincidence, and correcting the citation in place rather than deleting the number. NOT count-carries-its-noun-and-denominator, NOT verdict-carries-its-threshold.
---

# A number quoted from a test is a number quoted from that test's harness

`D = 20000, built by test_kill_values_py_139_arith_120` reads as a fact about
a program. It is a fact about a *pair*: the program, and the parameters of
whatever ran it. Strip the second half and the sentence survives review,
survives grep, survives a round of "re-derive before quoting" — because the
citation looks checkable. You open the named test, the source is right there,
and the number is not in it.

The failure is not that nobody checked. It is that checking meant **reading**
the test, and the answer was only in **running** it.

## The instance this came from

Round 452 of this program shipped a language decision justifying a rendering
depth cap. Its supporting sentence:

> The deepest value this repo builds anywhere is not 14 — it is **20000**,
> built by `tests/test_generated_killers.py`'s
> `test_kill_values_py_139_arith_120` … a runaway recursion whose unwind
> builds one record per frame, so the value's depth is exactly
> `DEFAULT_MAX_DEPTH`.

Every clause is true except the attribution. That file's helper is

    def canonical(src, Interpreter, Env, LexError, ParseError,
                  full_show, max_depth=500):

and its `run(src)` passes no override, so **every program in that file
executes at `max_depth=500`** and the cited test builds a value **500** deep.
Sweeping the parameter is what turns that from an anecdote into the law:

```
max_depth=  7   ->  D =    7
max_depth= 64   ->  D =   64
max_depth=500   ->  D =  500   <- what the cited test actually builds
max_depth=20000 ->  D = 20000  <- the number the doc quoted
```

The interpreter's default is 20000; the test never sees it. Same source, four
caps, four depths: 7, 64, 500, 501.

The number itself was real, and reachable, and had *already been re-derived*
— by a different test in the same tree, written by the same round, which
built its own interpreter at the default. Four rounds later a next-step
asserted the number "has never been re-derived by anything". Both the claim
and its correction were four lines apart in one file.

A second sentence in the same paragraph went the same way: *"`max_depth` is
the real upper bound on value depth"*. It bounds what recursion builds.
Ordinary code then wraps the result — `[[rec]]` is two deeper — so the
"ceiling" is exceeded by any caller who types two brackets.

## When this triggers

* A doc, decision record, comment or commit cites a named test/benchmark/
  fixture **as the source of a number**.
* You are about to quote such a number, or to write "X has never been
  measured" about a tree you have read but not run.
* A helper in the citing file carries a numeric default — `max_depth`,
  `timeout`, `n_iter`, `warmup`, `batch`, `seed`, `tolerance`, `maxsize` —
  and the cited artefact does not name it.
* Two artefacts share source text and report different numbers.
* A bound is described with a superlative ("the real limit", "the ceiling",
  "cannot exceed").

## Steps

1. **Find the runner, not the test.** Locate the function that actually
   executes the cited artefact — the local `run`/`val`/`bench`/`canonical`
   helper, the fixture, the CLI wrapper. In a large tree, compute it instead
   of guessing: a fixed point over the module AST beats a hand-written list
   of names, because helpers do not agree on names across files.
2. **Read the runner's parameters off the source, not off memory.** Every
   numeric default, and every keyword the call site overrides. Record them
   next to the number.
3. **Run the cited artefact under its own runner.** Not a fresh harness you
   built — the one the citation implies. Record the number you get.
4. **Run the same source under the default / the other runner.** If the two
   differ, you have found the defect and you also have both halves of the
   corrected sentence.
5. **Prove it is a law, at three or more points.** One matching value is a
   coincidence. Sweep the parameter and show the number tracks it. This is
   what turns "the number is wrong" into "the number belongs to the
   parameter".
6. **Test the superlative separately.** A bound claim ("this is the ceiling")
   needs its own falsification attempt — construct the thing that exceeds it.
   It is usually one line.
7. **Correct in place, and keep the number.** Fix the attribution in the
   original sentence; do not delete a number that is real. Add a test that
   fails if the wrong sentence returns, and re-derive downstream text that
   quoted it — a docstring repeating the citation is the same defect with a
   second copy.

## Pitfalls

* **Reading the assertion instead of running it.** The cited test's `assert`
  often shows a *rendering* (`@{v: @{v: …}}`), which is truncated by a
  display cap and is consistent with many depths. It looks like evidence.
* **Trusting the artefact's own name.** `test_the_deepest_value_this_repo_
  builds_is_max_depth_not_fourteen` is a claim, not a measurement.
* **Assuming the default is the value.** A default is what you get when
  nobody names it. Test harnesses name it constantly, precisely because the
  default is too slow or too deep for a suite.
* **Deleting the number.** It was usually right. The citation was wrong.
* **Stopping at the first file.** The false citation propagates into
  docstrings, changelogs and next-step lists. Grep the number *and* the
  artefact name.
* **Deriving a second claim from the first.** In the instance above, a
  banked prediction reasoned "the killer is 500 deep, 500 < 1201, therefore
  the corpus max is below 1201" — arithmetic that smuggled in the
  unmeasured assumption that the cited test was the deepest. It was off by
  40x. Deriving from a repaired number does not repair the derivation.

## Verification

Run in `languages/whence/`:

    python3 -m pytest -c pytest.ini tests/test_testcorpus_census.py -q

Expect `18 passed`. Five of those tests are this skill executed against the
instance it came from:

* `test_the_generated_killer_suite_runs_every_program_at_500` — step 2, the
  runner's default read straight off the AST.
* `test_the_value_decision_53_cites_is_500_deep_not_20000` — step 3.
* `test_the_same_source_at_the_default_depth_is_exactly_max_depth` — step 4.
* `test_the_depth_is_the_cap_and_not_a_constant_of_the_program` — step 5,
  three further points (7, 64, 501).
* `test_the_spec_no_longer_attributes_20000_to_that_test` — step 7, goes red
  if the corrected sentence is reverted.

Step 6 is `tests/test_v44.py::test_max_depth_bounds_recursion_and_not_value_depth`:

    python3 -m pytest -c pytest.ini \
      tests/test_v44.py::test_max_depth_bounds_recursion_and_not_value_depth -q

Expect `1 passed`; it asserts `[300, 301, 302, 305]` — the superlative
falsified at four points.
