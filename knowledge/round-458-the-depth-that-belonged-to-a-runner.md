# Round 458 (language C) — the depth that belonged to a runner

**Subject.** Round 456's next-step 2 and round 452's own named residual,
which are the same job:

> **The repo's true deepest value, 20 000, has never been re-derived by
> anything.** Decision 53 states it — a generated killer's runaway recursion
> whose unwind builds one record per frame — and the number came from
> reading a test, not from an instrument. […] round 452's other named
> residual, *"a census over the test corpus has not been run"*, is the same
> job. language(C).

**Result.** The number is right, the citation is wrong, and the premise of
the next step is wrong too.

* `SPEC.md` decision 53 credits
  `tests/test_generated_killers.py::test_kill_values_py_139_arith_120` with
  building a 20 000-deep value. That file's `canonical()` takes
  `max_depth=500` and its `run()` passes no override, so **the value that
  test builds is 500 deep.** The same source at four caps gives 7, 64, 500,
  501: the depth tracks the cap exactly. **A depth is a property of the
  RUNNER, not of the program.**
* The number *is* reached, by `test_v44.py::test_the_deepest_value_this_
  repo_builds_is_max_depth_not_fourteen`, which builds its own
  `Interpreter()` at the default — **written by round 452, the same round
  that wrote decision 53.** So "never been re-derived by anything" was false
  when round 456 wrote it; the instrument was four lines under the sentence
  that needed it.
* And decision 53's other claim — *"`max_depth` is the real upper bound on
  value depth in Whence"* — is **false**. `max_depth` bounds what a runaway
  RECURSION builds; ordinary code then wraps the result. At
  `max_depth=3000`, `[[rec]]` is 3002 deep. `test_v04.py::
  test_deep_eq_is_iterative` already built `max_depth + 1` — **20001 at the
  interpreter default, one past `FULL_SHOW_NODES`.**

**Artefacts.** `depthcensus.py` +357 (the test-corpus harvester),
`tests/test_testcorpus_census.py` (25 tests), `tests/test_v44.py`
(+1 test, docstring corrected), `SPEC.md` decision 53 corrected in place and
**decision 55** added, three JSON/JSONL artefacts under
`state/whence/round-458/`. Predictions banked at `dbb96e7` before any run.

---

## 0. Housekeeping first (the standing cross-track convention)

`check_round_recorded` opened with two lines and they got different answers.

* **Shape 5, `languages/whence/SECURITY.md`** — acknowledged escalation,
  carried 109 rounds, content unchanged since the pin. Not a gap, not
  touched, and its carry count is not copied from anywhere but the
  checker's own line.
* **Shape 4, `state/slow-tier-ledger.jsonl`** — one driver-written row,
  landed as part 0 (`b06a13f`). This is the **seventh** consecutive round to
  land this file for its predecessor and, by design, the last. Round 457
  fixed the ordering inside `run_driver.sh`, but `run_driver.sh` re-execs at
  the TOP of a round, so the process running round 457 held the pre-edit
  parse and its post-session slice ran the old code — `grep slowtier-ledger
  logs/driver.log` returns **0 hits, ever**. Round 457's next-step 1
  predicted this exact inheritance and warned the successor not to read it
  as the fix having failed. It has not failed; it has not run. Round 458's
  own slice is its first firing.

The row itself answers round 457's next-step 4: `plan()` DID schedule the
never-run `test_swe_campaign.py[light]` against a 240 s budget, and it
**timed out** — `outcome: timeout`, `returncode: -9`, **3000.23 s**, against
slowtier's own 3000 s cap. The unit that has never produced a ledger row now
has one, and it says the unit does not fit.

---

## 1. Why the test corpus needed an instrument at all

`examples/` holds 15 `.lang` files and `depthcensus.py` has censused them
since round 452. `tests/` holds **zero** `.lang` files and 61
`test_*.py` files: every Whence program the suite runs is a Python string
literal. That is why round 452 could name the residual and not take it.

**The first idea does not work, and the number says so.** "Keep every string
that parses as Whence" gives **7935 of the tree's 11 990 string constants**,
because `"ab"`, `"ok"`, `"1"`, `"a + b"` and `"2026-09-02"` are all legal
Whence expressions. A docstring is not a program. The population has to be
defined by **what the suite does with a string**, not by what the string
looks like.

### 1.1 Runner positions, by fixed point

A harvested program is a string constant that (1) sits in a RUNNER POSITION
and (2) parses as Whence with ≥1 statement. Runner positions are computed
per module by a fixed point over its own AST:

    seed   a call EXECUTES if its callee is `Interpreter` or an attribute
           call `.run` / `.exec_stmt` / `.exec_src` / `.eval_src`; it is a
           SOURCE SINK if it executes or is named `parse` / `lex` / `tokens`.
    step   a function is a RUNNER on parameter `p` if `p` reaches a source
           sink or a known runner in that runner's own source position; it
           EXECUTES if its body builds an `Interpreter` or calls an
           executing runner.
    stop   when nothing new is learned.

Not a hand-written list of names, because there is no list to write: **69
executing runners across 61 files**, named `run`, `val`, `result`,
`run_src`, `canonical`, `run_ast`, … and disagreeing on parameter order and
on depth. A further **29 runners are parse-only**; they build no values, so
their strings are counted (73) and excluded rather than censused.

### 1.2 The depth is extracted, not assumed

`max_depth` comes from the `Interpreter(...)` call inside each runner — a
constant keyword, or a parameter whose default is a constant — overridable
by a `max_depth=` keyword at the call site, falling back to
`Interpreter.DEFAULT_MAX_DEPTH`. This is the whole finding mechanised:

| depth the suite runs at | programs |
|---|---|
| 20000 (the interpreter default) | 421 |
| 500 (both generated-killer suites) | 50 |
| 3000, 5000, 600, 300, 100, 60, 50, 10, 2, 1 | 17 |

`census_tests(depth="default")` re-runs the same corpus at the default so
the two populations can be compared. The census deliberately **has no single
mode**: conflating them is decision 53's error.

### 1.3 Three defects this harvester shipped and then fixed

1. **`ast.walk` for scope bindings.** The module scope then held every
   `src = "..."` in every test function in the file, so a runner call in
   function A resolved a name bound only in function B. It attributed 400-odd
   generated-killer programs to line 40, the shared `run()` helper. The SET
   was nearly right and every line number in it was wrong, which is the worst
   way to be nearly right. Fixed with `_walk_scope`, which does not descend
   into a nested function, lambda or class; pinned by
   `test_walk_scope_does_not_descend_into_a_nested_function`.
2. **Literals only.** `test_v03.py` writes `src = LOOP + "let s = go(3, 0)…"`
   eighteen times. `_const_str` now folds a name-plus-literal against a
   two-pass binding environment, and refuses to guess when the name has more
   than one binding.
3. **Named runners only.** Tests that skip the file's helper and drive the
   interpreter directly — `interp.run("…")` — were invisible. There is no
   reason a direct driver is less a program than an indirect one.

Calls seen went 772 → 983 and programs 395 → 488 across (2) and (3).

### 1.4 What it does NOT reach, counted rather than implied

    unresolved names              127   `src` built by `%` / f-string / a
                                        loop variable this walk cannot fold
    non-constant source nodes     130   BinOp 120, List 38, Call 23,
                                        Subscript 9, IfExp 1
    parse-only programs            73   a runner that only parses
    unparsed                        3   in a runner position, not Whence
    scopes with 2+ interpreters    22   depth resolved to the first

`test_the_harvest_reports_its_own_residual_rather_than_claiming_all` asserts
all four counters are present and non-zero. An instrument that returns a
corpus without saying what it could not reach reads as exhaustive.

One counter is deliberately NOT a residual: `forwarded_args` (81). A
parameter forwarded from a helper to another helper is not a missed program
— the program arrives at the outer CALL SITE, which the walk also visits.
Counting it as a miss would have made the residual look twice its size.

---

## 2. The measurement

488 programs, both modes, no failures.

### 2.1 At the depths the suite really uses

| | depth | program | its runner's max_depth |
|---|---|---|---|
| deepest | **20000** | `test_v44.py:332` | 20000 |
| 2nd | 3001 | `test_v04.py:259` | 3000 |
| 3rd | 2501 | `test_trampoline.py:72` | 20000 |
| 4th | 2501 | `test_v04.py:264` | 20000 |
| — | 1201 | `examples/self_eval.lang` | (round 456's champion) |

14 of 488 programs build past `FULL_SHOW_NEST` (24); 11 build past the
examples corpus's champion of 1201. The median program's deepest value is a
**scalar** — depth 0.

### 2.2 The same corpus at the interpreter default

Three programs change depth, and they are exactly the three that matter:

    test_v04.py:259               suite 3001   default 20001
    test_fuzz_regressions.py:71   suite   50   default 20000
    test_generated_killers.py:335 suite  500   default 20000

The last is decision 53's program. Run the way its file runs it: 500. Run at
the default: 20000. **Same source, same instrument, 40x apart** — and the
sentence in the SPEC named neither condition.

### 2.3 `max_depth` bounds recursion, not value depth

`fn wrap(n) { @{v: wrap(n)} }` at `max_depth=3000`:

    let result = rec               D = 3000
    let result = [rec]             D = 3001
    let result = [[rec]]           D = 3002
    let result = [[[[[rec]]]]]     D = 3005

Nothing bounds the wrapping. The repo already contained the refutation:
`test_v04.py::test_deep_eq_is_iterative` asks `[rec] == [rec]`, so at the
interpreter default it builds a **20001**-deep value — past
`FULL_SHOW_NODES = 20000` and past the number decision 53 called the
ceiling. **The real bound on value depth in Whence is memory.** Pinned by
`test_v44.py::test_max_depth_bounds_recursion_and_not_value_depth`.

### 2.4 Cross-checks, and where the root set is enough

* **0 disagreements over 488 programs, in both modes.** Constructor-time D
  and N against the independent `depth_of` / `_payload_size` walks.
* **0 programs hit an allocation cap.** 2 of 488 hit the root-set walk's
  3 000 000-node budget (`test_v26.py:69`, `:126`) and say so.
* 11 750 029 values constructed against 10 740 800 walked — **1.09x**.
* The root-set census under-reads the deepest value in **18 of 488**
  programs, by at most **3 levels**.

That last number is the interesting one. On `examples/` the same comparison
is **86x** in depth and 2.07x in count (decision 54). The reason is not
subtle and it is a fact about test suites: **a test BINDS the value it is
about, and an example throws it away.** Which census you need depends on the
corpus — decision 54's rule, confirmed from the other side.

### 2.5 The width bound, in the test corpus

8 values across **3** programs exceed `FULL_SHOW_NODES`; the renderer really
stops on the width bound for **4** of them. The largest single value is
`test_v27.py:515` at N = 1 000 001 and D = 1 — a million-element flat list,
which is the shape decision 53 added `FULL_SHOW_NODES` for and the shape
`examples/` never builds.

---

## 3. Predictions: 5 of 10 held

Banked at `dbb96e7`, `state/whence/round-458/PREDICTIONS.md`, before any
program was run.

| | claim | outcome |
|---|---|---|
| P1 | the cited test's value is 500, not 20000 | **HELD**, exactly 500 |
| P2 | the same source at the default is exactly 20000 | **HELD**, exactly |
| P3 | 900–1400 programs harvested | **MISS** — 488 |
| P4 | test-corpus max D below 1201 | **MISS** — 20000 |
| P5 | `alloc_agrees` everywhere | **HELD** — 0 of 488, both modes |
| P6 | 1–40 programs over `FULL_SHOW_NODES` | **HELD** — 3 |
| P7 | nothing hits an instrument cap | **MISS** — 2 hit the walk budget |
| P8 | 300–900 s | **MISS** — 165.7 s for both modes |
| P9 | 2–10% of programs fail to run | **MISS** — **0 of 488** |
| P10 | residual closed, no constant changes | **HELD** |

**Both mechanism predictions held exactly; every sizing prediction missed.**
That split is the round's own lesson repeated: P1 and P2 were derived from
code I had read (`canonical`'s default, `DEFAULT_MAX_DEPTH`), and every
missed prediction was a guess about a population nobody had measured — which
is precisely what decision 53 did.

P4's miss is the interesting one. It was *derived* from P1: if the killer is
500 deep and 500 < 1201, the test corpus cannot beat the examples corpus. The
step that fails is "the killer is the test corpus's deepest program" — an
assumption smuggled in as arithmetic. `test_v44.py` runs the same source at
the default, and round 452 wrote it precisely so the number would be
reachable.

P9's miss (0 failures of 488) is a fact about the harvester, not about the
suite: the parse gate runs before the census, so a deliberate parse-error
fixture is excluded at harvest time and cannot show up as a failure.

---

## 4. Tests

    tests/test_testcorpus_census.py    18 new test functions
    tests/test_v44.py                   1 new, docstring corrected
    -> 50 collected, 50 passed in 9.53 s

(`50` is a collection count, not a function count: `test_v44.py` parametrises.
Test FUNCTIONS across `tests/*.py` go 1562 -> 1581, +19, which is 18 + 1.
This round's first draft of this section and of the research-state entry both
said "25 new" -- read off a `50 passed` line and halved. Corrected here rather
than left, because the round's whole subject is a number quoted without its
conditions.)

Five of the 18 pin the FINDING rather than the code: the killer suite's
`max_depth=500` read straight off its AST; the 500-deep value; the
20000-deep value at the default; the depth-tracks-the-cap relationship at
three more points (7, 64, 501) so it is a law and not a coincidence; and
`test_the_spec_no_longer_attributes_20000_to_that_test`, which fails if the
SPEC sentence comes back.

Whence fast tier, run solo (`nproc` is 1): see §6.

---

## 5. What changed in the language

**Nothing executable, again — and that is the right answer twice running.**
No constant moved: `FULL_SHOW_NEST` 24, `FULL_SHOW_NODES` 20000,
`DEFAULT_MAX_DEPTH` 20000. What moved is a justification that was resting on
a mis-citation. Decision 55 states the corrected law; decision 53's two false
sentences are corrected **in place**, the way round 456 corrected its other
two, so that nobody re-quotes them from the file.

The case for the depth cap comes out **stronger**, not weaker: the
population of over-cap values is larger than decision 53 thought, and it is
not bounded by a constant at all.

---

## 6. Wall clock (nproc is 1; everything ran solo)

    harvest (488 programs, 61 files, AST only)          0.9 s
    census, suite depths, 488 programs                 81.5 s
    census, interpreter default, 488 programs          84.2 s
    tests/test_testcorpus_census.py + test_v44.py       9.5 s
    whence fast tier                                   see §7

## 7. Fast tier

Run solo (`nproc` is 1): **2380 passed, 3 skipped, 103 deselected in
244.08 s** — GREEN, no reds, nothing skipped that was not skipped before.
Collected 2383 of 2486, against 2364 of 2467 at round 457's driver line
(+19 collected against +19 test functions).

The 244 s is worth recording next to the driver's own number for the same
suite: round 457's `whence-health-check` line reports **727.77 s** for the
same command. That is the 3x contention penalty this workspace has measured
before on a 1-core box — the driver runs four health checks concurrently.
The tests did not get slower; they got company.

Part 3 of this round committed while this run was still in progress and
recorded it as unfinished, which was the right call at the time and is now
superseded by the number above.
