# Round 452 (language C) — the cap that was two promises and one number

**Subject.** Round 450's next-step 1: *"`SHOW_NEST` is now the only thing
between a reader and a deep miss, and nothing measures how often that bites.
… The open question is whether the FULL rendering should carry a
depth-bounded-but-deeper cap of its own … and it needs a number: the deepest
value any corpus program actually builds. Nobody has measured that."*

**Result.** The number is **14**, and the value is an AST — the one
`examples/self_host.lang`'s Whence-in-Whence parser builds. Against a full
rendering that showed **4** levels. The language's own self-hosting program
built values three and a half times deeper than the language could print, and
nothing had ever noticed because max PRINTED depth across the whole corpus is
**2**. Whence v0.44, decision 53, splits `SHOW_NEST` into two constants and
adds the one bound the split required.

---

## 1. Housekeeping first (the standing cross-track convention)

`check_round_recorded` reported one uncommitted unattributed path,
`state/slow-tier-ledger.jsonl`. Inspected before landing: one appended entry,
`test_swe_toolliveness.py`, `passed`, 4.02 s, `finished_at` 1788344982.56 =
2026-09-02 10:29:42 UTC — after round 451's last commit and matching
`driver.log`'s own `10:29:46 round 451: slowtier-slice OK` line. Its
`checkout_digest` (`8dfc591bc54e7f19`) matches the previous entry's. A
driver-written ledger append, the same shape rounds 449 and 450 landed for
their predecessors, committed as part 0 with that attribution. **Third
consecutive round to land a predecessor's orphan; second time it is this exact
file.** That is a pattern, not three coincidences — see §9.

`languages/whence/SECURITY.md` is untouched: escalated, the operator's, and
the checker's own line is the only source for its carry count.

---

## 2. `depthcensus.py` — the instrument, not the script

The bank (§8) fixed this before any measurement: the census lands as an
**artefact with its own suite**, so the next round to ask re-derives the
number instead of quoting round 452's. `languages/whence/depthcensus.py`,
`tests/test_depthcensus.py` (29 tests).

**The metric, defined before it was taken.** `D(p) = 0` for every
non-container payload; `1 + max(children)` for `WList` and `Record` (1 when
empty); `1 + D(node)` for `Guess`, because `_show`'s `Guess` branch descends
with `nest + 1` exactly as a container branch does. Lined up with the
renderer's own `nest` counter on purpose, so the two compare with no
conversion — **a printed value is rendered in full iff `D <= FULL_LEVELS`**,
and `FULL_LEVELS` is *derived from the constant*, not written down, which is
what lets a later round move the cap and keep the instrument.
`test_full_rendering_is_complete_exactly_when_depth_is_within_the_cap` holds
that as a differential at nine depths rather than as a sentence.

**Two populations, kept apart.** BUILT (every payload reachable in a finished
program's provenance graph) and PRINTED (what actually reaches `full_show`).
Conflating them is the error the whole round is about: a cap justified by
"nothing has hit it" was being justified by the wrong population.

**The root set, and why it hooks `_note_drop`.** Whence retains history, so a
walk over `Prov._ins` from a small root set reaches every value that
*contributed* to a root. The roots are (a) every binding in the top-level
`Env`, (b) every value handed to `Interpreter._note_drop` — whose own
docstring says it is called from "the three places a statement value is thrown
away", i.e. `run`'s top level **and the two block evaluators**, so it reaches
statements discarded inside a function body — and (c) every payload that
reached the renderer. (b) is the one that matters, and it costs nothing: the
interpreter already calls it at every level for exactly the values a root set
built from surviving bindings would miss. `--roots env` measures the naive set
for comparison, and `test_a_value_nothing_keeps_is_still_measured` pins the
difference: `map(fn(i) { [[i]] }, [1, 2])` as a bare statement reports **3**
under the real root set and **0** under the naive one.

What it still does not reach is stated in the module docstring rather than
left for a reader to find: a value that is neither bound, nor a discarded
statement's value, nor printed, nor an input to any of those.

---

## 3. The reading

```
program                     built print    nodes prints  spine
self_host.lang                 14     1    14562    161  Record>WList>Record>Record>WList>…>str
self_eval.lang                 10     0     6615   1250  Record>WList>Record>WList>…
meta.lang                       6     0  2493635     13  Record>Record>Record>Record>Record>Record>str
diverge.lang                    3     1      330      9  WList>Record>Record>int
history.lang                    3     2      360      9  WList>Record>WList>float
…
deep.lang                       0     0   170061      5  Miss
```

* max **BUILT** 14 (`self_host.lang`, `let p7`, line 1288)
* max **PRINTED** 2 (`history.lang`)
* full rendering showed 4 levels; **3 of 33** programs build past it
* **0** printed values truncated; **0** printed lines carrying a nest marker
* 13 of the 22 programs that print build deeper than they print
* 10 of the 33 do not parse — all foreign (Hermes-gateway) programs, the
  known v0.19 strict-block population

`deep.lang` is the instructive row: 170061 nodes, depth **0**. It is deep
*recursion*, not deep *values*. A census that had counted nodes and called it
depth would have named it the deepest program in the corpus.

**The finding, re-derived not quoted** (`test_v44.py::
test_v043_truncated_that_value_and_v044_does_not`):

```
v0.43 full rendering of p7 (139 chars):
  @{kind: "program", stmts: [@{body: @{kind: "block", stmts: […]}, kind:
  "fndef", name: "go", param_types: [], params: ["n"], ret_type: ""}]}
v0.44 (589 chars): reaches the expression the function evaluates.
```

---

## 4. Decision 53 — two promises, two constants

`SHOW_NEST` was never one cap. It was two promises reading one number, and
decision 37 had already written both down: *"`str` is `full_show` — unbounded,
a miss lists its reasons"*; *"every MISS MESSAGE is built from `show_payload`
instead: one line, bounded"*. Sharing the constant is precisely why "lifting
the cap" reads as impossible in v0.43's own prose — **every argument for
keeping it low is an argument about the snapshot, and every argument for
raising it is an argument about the full rendering.**

```
SHOW_NEST       = 3      bounded snapshot: show(), miss messages, Prov.show,
                         parse diagnostics.  UNCHANGED.
FULL_SHOW_NEST  = 24     full rendering: print, str.
FULL_SHOW_NODES = 20000  new, and required by the change (§5).
```

**24 is derived from two measurements.**

*Host frames.* `HOST_RESERVE`'s own comment lists "rendering (depth-capped)"
among the three things its 250-frame reserve covers, so the cap spends that
reserve and had to be paid for before it could be raised. Measured by
recursion-limit bisection:

```
v0.43 path   4 + 3 frames/level      7, 10, 13   at depths 1, 2, 3
v0.44 path   3 + 1 frames/level      4, 8, 13, 23, 27  at 1, 5, 10, 20, 24
```

Three of v0.43's four frames per level were the trip out through
`show_payload` and a generator expression to get back into `_show`; the full
path now re-enters `_show` directly from an explicit loop. **27 frames at the
new cap against 13 at the old one — a +14 delta buys 20 extra levels.**

**A methodological correction worth keeping.** The first reading of this
number was 4 frames/level, taken by wrapping `_show` with a counting function.
The wrapper adds one frame per level and inflates the very number being
measured. Bisection says 3. *An instrument that sits inside the thing it
measures is part of the measurement* — and both numbers are in
`tests/test_v44.py`, one as the assertion and one as the comment saying why it
is not 4.

---

## 5. The job the cap was doing that nobody had named

Round 450's next step said *"`full_show` already pays O(n) in elements"*. It
does not. Whence values SHARE on purpose — `WList` is a length-bounded view
over an append-only buffer — so the value graph is a **DAG**, and a renderer
walks a DAG as a **TREE**, once per PATH. Sixteen levels of `[v, v]` over a
two-element list is 33 distinct nodes and 2^16 rendering paths:

```
cap  3 ->    108 chars      cap  9 ->   7164
cap  6 ->    892            cap 12 ->  57340
```

**2^n, not O(n).** So the depth cap was load-bearing for OUTPUT SIZE and only
ever documented as load-bearing for host frames, and that second job does not
survive being raised from 4 levels to 25. `FULL_SHOW_NODES` takes it over —
and takes over the WIDTH direction too, which v0.43 never bounded at all:
`full_show` of a million-element list rendered a million elements, in a
language that caps an integer at 4000 digits so the explanation path cannot
crash. 20000 is 666x the largest full rendering the corpus produces (30
rendered nodes, `show.lang`; widest text 1883 chars, `blame.lang`).

**Why a deeper cap and not no cap.** The tempting reading of "max BUILT 14" is
that the bound could go away. The refutation was already in this tree:

```
fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 0)} } }
let rec = wrap(1)
```

— `tests/test_generated_killers.py::test_kill_values_py_139_arith_120`. A
runaway recursion whose unwind builds one record per frame, so the value's
depth is exactly `DEFAULT_MAX_DEPTH` = **20000**, measured. At 1 host frame
per level an unbounded renderer needs 20000 frames, past CPython's default
1000 and past `run.py`'s raised 6000. **`max_depth` is the real upper bound on
value depth in Whence, and it is 800x the new cap.**

---

## 6. The mirror is gone

v0.43 computed "the miss nodes the rendering NAMED" with a *second walk*,
`values.named_misses`, written to mirror `_show` branch for branch and held to
it by a differential test. That is the shape
`skills/suppressor-shares-the-detector-shape/SKILL.md` exists to warn about —
and **moving the renderer's bound is exactly the edit that breaks a mirror.**

So v0.44 removes the mirror instead of re-synchronising it.
`full_show_named(node)` returns `(text, misses, depth_stopped, node_stopped)`
from ONE walk: the misses are collected in `_show`'s own container branches,
at the moment it emits the text that names them. `named_misses` is that
function's second return value; `b_print` reads both halves of one walk and no
longer renders the value twice.

*The suppressor has the renderer's bound* stopped being a property a test
keeps true and became a thing that cannot be otherwise. v0.43's differential
still passes and is now tautological — the intended end state. It is kept,
because it is what agreement looked like when there were two walks, and
because its falsification arm still works: restoring v0.42's unbounded claim
(now by wrapping `full_show_named` rather than by replacing `named_misses`)
still makes the deep case go silent.

`test_a_miss_the_budget_did_not_reach_is_still_reported_as_a_drop` is the new
bound's version of the v0.43 defect: a miss past the NODE budget is exactly as
unrendered as one past the depth cap, and the drop report still names it.

---

## 7. What moved

* **Corpus output: nothing.** Max printed depth 2, so all 33 programs produce
  byte-identical output at a cap of 4 and a cap of 25. Pinned per-program by
  `test_raising_the_cap_changed_no_corpus_output` — and that test was
  **vacuous when first written** (§9).
* **Two generated killers**, both quoting a deep record's rendering, re-pinned
  by `harness/swe/killerrepin.py --write`: `holds 62, repin 2, stale 0`. The
  tool proves the movement is attributable to this diff by re-running each
  pinned program against the baseline tree. **First use of round 450's tool,
  by the first deliberate language change after it** — which is exactly what
  round 450's next-step 3 asked for, and it took one command.
* **Three tests in `test_v43.py`** pinned the boundary at the literal 4/5
  rather than at the constant that decides it, and were re-pointed at
  `FULL_SHOW_NEST`. That was the entire cost of the split. The rule:
  **a test that pins a boundary should name the constant, not the number** —
  otherwise moving the constant looks like a regression in three places.

---

## 8. Predictions, scored

Banked at `state/whence/round-452/PREDICTIONS.md`, committed before any
command in the subject ran. 16 lines, each with a round-448 BASIS tag.

| # | basis | claim | verdict |
|---|---|---|---|
| P1 | MODEL | corpus max BUILT in 4–6, likely 5 | **MISS** — 14 |
| P2 | MODEL | corpus max PRINTED in 2–4, likely 3 | **HIT** (band) — 2; likeliest value wrong |
| P3 | MODEL | no corpus print truncated by the cap | **HIT** — 0 values, 0 marker lines |
| P4 | MODEL | ≥10 programs build deeper than they print | **HIT** — 13 of 22 that print |
| P5 | SENT | deepest is a self-hosting/meta program | **HIT** — `self_host.lang` |
| P6 | NONE | deepest is one of the 15 foreign programs | **MISS** — it is one of our 18 |
| P7 | MODEL | raising 4→8 changes zero corpus outputs | **HIT** — and 4→25 does too, per-program |
| P8 | MODEL | deepest spine is mixed Record+WList | **HIT** |
| P9 | MODEL | ≥1 graph over 1,000,000 nodes | **HIT** — `meta.lang` 2,493,635 |
| P10 | MODEL | ≤4 host frames per rendered level | **HIT** — 3, and now 1 |
| P11 | MODEL | ≥1 corpus program builds D > 4 | **HIT** — 3 of them |
| P12 | MODEL | 4–6 live `SHOW_NEST` uses change | **HIT** — 5 (2 parameterised, 3 deleted with the mirror) |
| P13 | CMD | whence tier 2298–2316 passed, 0 failed | **MISS (denominator)** — see below |
| P14 | MODEL | zero generated killers go red | **MISS** — 2 |
| P15 | NONE | declined: payload-object count, peak memory | **reported**: 3,587,551 nodes walked corpus-wide; distinct payload objects not separately counted, peak memory not taken |
| P16 | MODEL | an unbounded renderer would pass every test here | **MISS** — it would blow the stack in `test_generated_killers.py` |

**10 HIT, 5 MISS, 1 no-basis-reported of 16.**

**The misses are one family and it is the important part of this round.**
P1, P14 and P16 all took `examples/` as the population. It is not the
population: `tests/` builds a value of depth 20000 and prints it. P14 said
"no killer builds a value with D > 4" — two do; P16 said the corpus was too
shallow for an unbounded renderer to be caught here — the tree catches it
loudly. This is the direct descendant of round 451's *a prediction scoped to a
FILE measures the file*: **a prediction scoped to the CORPUS measures the
corpus.** The subject sentence said "corpus", I banked "corpus", and the
question was about the language.

P1 has a second defect worth more than the first: **the same bank contained
P5, which correctly said the deepest value would be a self-hosting program's
— i.e. an AST.** An AST of a program with functions, blocks, statements and
expressions is not 5 deep. P1 and P5 were inconsistent with each other and I
did not check the bank against itself. *A bank with two lines about the same
object should be read as a pair before it is committed.*

P13 is a MISS on the DENOMINATOR, not on the work: I banked 2298–2316 against
round 451's recorded "2286 passed, 3 skipped, 98 deselected", which is the
**fast** tier (`run_tests_fast.sh`, `-m "not whence_slow"`) and not the full
one. Predicting a total against a number whose collection scope you have not
checked is the count-band rule (round 449's step 12: *a count band names its
counter*) failing on the counter's SCOPE rather than on its unit.

P10 is the hit worth reading: it was right about a number I had measured
wrongly. The instrumented reading was 4, the bisection 3, and the fix made it
1 — so a HIT against a bound that was itself an artefact of the instrument.

---

## 9. Failures and residuals, honestly

**A test that patched a constant the code had captured at import time.**
`full_show_named` was first written as `def full_show_named(node,
cap=FULL_SHOW_NEST, budget=FULL_SHOW_NODES)`. A default argument is bound at
DEFINITION time, so every test that moved `V.FULL_SHOW_NEST` to compare old
and new behaviour compared new against new and passed. **Two tests went green
against an unchanged renderer.** It was caught only because a third asserted a
specific string rather than an equality between two runs — the assertion that
could not pass vacuously. The constants are now resolved inside the function
body, and a non-vacuity check is recorded: at cap 3 `print([[[[[1]]]]])` gives
`[[[[[…]]]]]`, at cap 24 `[[[[[1]]]]]`. **Rule: a constant a test cannot move
is a constant nothing measures, and an equality between two runs of the same
code is the assertion shape that hides it.**

**The census stopped measuring `print` and said nothing.** The instrument
hooked `full_show`; decision 53 moved `b_print` onto `full_show_named`; the
census kept running, kept reporting a printed-depth number, and the number was
one lower. Caught by a print count going 161 → 160 in a diff I happened to
read. The hook is now on the WALK, which every caller reaches, and
`test_the_print_hook_sees_print_and_str_and_counts_each_once` pins it.
**An instrument that hooks a FUNCTION measures whichever callers still go
through that name.**

**Three orphan-landing rounds in a row is a pattern.** 449 landed 448's, 450
landed 449's, 451 landed 450's, and 452 landed 451's — four, and twice the
same file. `check_round_recorded` is a REPORT that relies on the next round
reading it (round 451's next-step 7). The slow-tier ledger append specifically
is *deterministic*: the driver always appends after the round's last commit.
That one is not a race to be caught, it is a step in the wrong order.

**Not done, and named rather than quietly dropped:**

* The census does not reach a value that is neither bound, nor a discarded
  statement's value, nor printed, nor an input to any of those. `--roots env`
  sizes what the NAIVE set misses; nothing sizes this residual.
* `FULL_SHOW_NODES = 20000` narrows a contract v0.43 left unbounded (width).
  666x the corpus maximum, so nothing reaches it — which also means **nothing
  in this tree exercises it except the two tests written for it.**
* The corpus population question is now open in the other direction: the
  census reads `examples/` and the deepest value in the repo is in `tests/`.
  A census over the test corpus has not been run.
* `depthcensus.py` is not wired into any tier or health check. It is a
  runnable artefact with tests; it is not scheduled. Same shape as round 450's
  `killerrepin` — which sat unscheduled for exactly one round and was then
  needed.
