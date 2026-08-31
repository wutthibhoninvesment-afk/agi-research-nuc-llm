# Round 383 — SWE-loop(D): the exemption that was already past the boundary

*Task: round 377's next-step item 3 — apply the `zero-rate-needs-a-distance`
audit to the oracles round 377 did not audit — plus item 1, resuming round
377's guest sweep.*

**Headline.** Round 377 measured one exemption and found the corpus sitting at
**6.25 %** of the boundary that would make it fire. I carried that shape into
this round as a prior and it was wrong for three of the four oracles. Of the
eight exemption sites in `harness/swe/oracles.py`, exactly **one** is far from
its threshold. The others sit **at** it (`render`'s pair cap: the corpus's
median binding count is 6 against a cap of 6), **past** it (`tail_transparency`'s
space exemption: the corpus demands a median of **1501** guest frames against a
threshold of **500**, six times over), or have no threshold at all and hide
their cost in a place a rate cannot show (`tail_transparency` drops `out` and
`checks` entirely on **92.0 %** of the corpus).

The generalisation round 377's skill needs:

> A THRESHOLD site has a DISTANCE. A PREDICATE site has a SURFACE.
> Every site has both a fire rate and a cost per firing, and the two are
> independent numbers. Reporting only the rate is wrong for both kinds, for
> two different reasons.

---

## 1. What was built

`harness/swe/exemptmap.py` — an exemption map for the whole oracle suite.

* **A self-verifying registry.** Eight `Site` records, each naming a literal
  anchor line of `oracles.py` and the exact number of times it must occur.
  `verify_sites()` raises, naming every drifted site, on the same rule
  `exemptaudit.patch_lib_source` uses: a registry that silently measures a
  branch that has moved would report numbers that *look* like results.
  It earned its keep on its first run — see §6.
* **`measure(pkg, src)`** — every site's `fired` / `demand` / `surface` for one
  program, computed by re-using the oracle's OWN predicates
  (`clear_tail_flags`, `provenance_tainted_names`, `erasure_exemption`,
  `frame_excess`), so a semantic change moves the measurement with it.
* **`sweep`** — one flushed+fsynced JSONL row per seed, resumable via
  `done_seeds()`, wall-clock budgeted, every program under a SIGALRM guard.
* **`depth_ladder`** — the T-SPACE ladder, walking ceilings UP (round 377's
  walked down) because here the corpus is above the ceiling, not below it.
* **`chain_ladder` / `chain_crossing` / `paircap_witness` / `witnesses`** —
  constructed inputs pushed through the real instrument (skill step 5).
* **`round110_claims`** — re-executes the three numbers `FRAME_SLACK`'s
  comment has asserted for 273 rounds with nothing running them.

`harness/tests/test_swe_exemptmap.py` — 24 tests. Nothing in it pins a rate.

## 2. The map, over 746 seeds (677 usable, 59 parse errors, 10 guard timeouts)

`ProgramGen(seed, stress_rate=0.5)`, seeds 0..745, `max_depth=500`,
`timeout_s=3.0`. Raw rows: `state/swe/round-383/sweep.jsonl`.

| site | oracle | polarity | fire % | cost when fired | distance |
|---|---|---|---|---|---|
| R-CAP | render | suppress | 39.6 % | 52.8 % of pairs | max 16 of 6 = **267 %** |
| F-SLACK | frames | tolerate | 0.0 % | — | max 98 of 140 = **70 %** |
| T-SPACE | tail_transparency | suppress | 10.8 % | **100 %** | max 3001 of 500 = **600 %** |
| T-TAINT | tail_transparency | suppress | **92.0 %** | 36.7 % | predicate |
| T-NONE | tail_transparency | no-op | 36.9 % | 0 % | no-op |
| T-ALL | tail_transparency | suppress | 2.1 % | **100 %** | predicate |
| P-EXEMPT | param_erasure | suppress | 6.8 % | **100 %** | max 4 of 2 = **200 %** |
| P-NONE | param_erasure | no-op | 56.3 % | 0 % | no-op |

`render` diverge-symmetry pairs across the corpus: **7 083 checked of 13 509
(52.4 %); 6 426 pairs never compared.**

## 3. The four findings

### 3.1 `render`'s `names[:6]` is a silent cap and the corpus's median is 6

`oracle_render` checks `diverge(x, y) == mirror(diverge(y, x))` for
`for i, x in enumerate(names[:6]): for y in names[i + 1:6]:`
(`oracles.py:293`). The bound is a literal in the loop and nothing reports what
it skipped.

Binding-count distribution over the corpus: p50 = **6**, p90 = 10, max = 16.
**13.1 % of programs sit exactly ON the cap and 39.6 % are past it.** Counted
live through `run_oracle("render", ...)` by wrapping `values.diverge` and
counting only calls whose two arguments are distinct objects:

| bindings | pairs available | pairs checked | skipped |
|---|---|---|---|
| 6 | 15 | 15 | 0 |
| 7 | 21 | 15 | 6 |
| 10 | 45 | 15 | 30 |
| 20 | 190 | 15 | **175** |

The checked count is constant at `C(6,2) = 15` however many bindings there are.
This is the "no silent caps" rule applied to an oracle rather than to a
workflow: a campaign reporting `render ok 677` is reporting a check that ran on
just over half the pairs it appeared to.

### 3.2 `tail_transparency`'s space exemption fires 6× past its threshold, and the raw number is CENSORED

`if peak >= max_depth: return ok(...space-exempt)` (`oracles.py:542`). Fires on
**10.8 %** of the corpus (**17.1 %** of the 427 programs that have a tail call
at all), and when it fires the oracle compares **nothing** — the whole
verdict is dropped.

The trap: `peak` is right-censored. The interpreter stops at `max_depth`, so a
fired site always reports `peak == 500`, and a distance computed from it is
`500/500 = 100 %` **by construction**. That is an artefact rendered in true
digits. `measure` marks the row `censored: true` and `report` prints
`[73 CENSORED: demand is a floor]` rather than a clean ratio.

`depth_ladder` un-censors it by raising the ceiling until the lifted run stops
hitting it. All 73 censored seeds, 31.9 s:

| real demand | seeds |
|---|---|
| (500, 1000] | 26 |
| (1000, 2000] | 25 |
| (2000, 5000] | 19 |
| unbounded (> 25000) | 3 (seeds 140, 273, 341) |

**p50 = 1501, max = 3001.** The corpus runs at **300 %** of the threshold at
the median and **600 %** at the maximum — the exact inverse of round 377's
guest finding. Raising `max_depth` from 500 to 5000 would convert 70 of these
73 silent exemptions into real comparisons.

### 3.3 `FRAME_SLACK`'s zero is the only structural one, and it is held there by two constants in another tree

F-SLACK is the round's one genuine zero: no program in 677 exceeded the slack;
max excess **98** against 140 (**70 %**). Unlike the others, that zero is not
about the corpus — it is about the LANGUAGE.

`chain_ladder`, on `let c = 1 + 1 + ... (n terms)`:

```
terms    2   4   8  16  32  64  100  128  160  200  256  320  400
excess   5   5   6  14  30  62   98   98   98   98   98   98   98
```

It **saturates at 98 and never grows**. Two ceilings hold it there, both in
`languages/whence/`, neither read by the oracle:

* `Interpreter.FAST_MAX_DEPTH = 100` (`whence/interp.py:1240`) — `_compile_fast`
  refuses a subtree taller than it, so the transient cannot exceed it. Measured
  by rewriting the constant: **excess == FAST_MAX_DEPTH − 2, exactly, at every
  value tried (20/50/100/150/200).**
* `MAX_NESTING = 60` (`whence/parser.py:142`) — nested list/record literals
  cannot be parsed past depth 59, capping that shape's excess at 62.

So `chain_crossing()` returns **None**: the band `(98, 140]` cannot be entered
by any program this language can express. The witness therefore has to move the
ceiling instead of the program, and at `FAST_MAX_DEPTH = 150` the real
`oracle_frames` reports `excess 148 > slack 140` on a **correct** program.

**That is the finding.** `FRAME_SLACK = 140` and `FAST_MAX_DEPTH = 100` live in
different trees with nothing linking them and 42 frames of headroom between
them, and the oracle is only sound while the first exceeds the second. A
performance round that raises `FAST_MAX_DEPTH` past ~142 turns `oracle_frames`
into a false-positive generator on correct code.
`test_FRAME_SLACK_still_has_headroom_over_that_bound` asserts the RELATION,
computed live from the interpreter, not either number.

### 3.4 The predicate sites hide their cost in the population, not in the rate

**T-TAINT.** Round 337's comment records that 213 of 400 programs (53 %)
contained a reflective construct. Today: `whole == False` on **623 of 677
(92.0 %)**. On every one of those the oracle drops `out` and `checks`
**wholesale**, because they are ordered by execution and cannot be attributed
back to a name. Only 270 (39.9 %) have a tainted *binding*; the 92 % is almost
entirely the wholesale drop. Mean surviving comparison surface when it fires:
**66.2 %**; p10 **40 %**. `T-ALL` — nothing left at all — is 2.1 %.

**P-EXEMPT.** 6.8 % of the corpus, which reads as negligible. But its clause
keys on a *shape-name* spec, and a primitive tag (`num`, `str`) is an `A.Str`
that cannot be shadowed at all. Only **74 of 677 (10.9 %)** programs use a
shape-name spec — and **46 of those 74 (62.2 %)** are exempted. Spec-name
multiplicity histogram: `{0: 603, 1: 28, 2: 36, 3: 9, 4: 1}`.

> The same measurement is 6.8 % or 62.2 % depending on which population you
> name, and the code names neither.

Its second clause — the program binds `typed` — fired **0 times in 677**, the
round's second structural zero. The distance there is unusual: the corpus is
zero away, because `typed` is a name the grammar simply never emits.

A side result while building the witness: **the only reachable way to bind a
spec name twice is a nested-scope shadow.** Whence's parser refuses same-block
rebinding outright (*"'S' is already bound in this block (line 1); Whence has
no rebinding"*) and refuses a second `shape S` in the same block. The
exemption's comment says "bound more than once anywhere in the program"
without noting the language admits exactly one shape for it.

### 3.5 Round 110's four numbers reproduce EXACTLY after 273 rounds — and round 337's does not

`oracles.py:96-103`'s `FRAME_SLACK` comment has asserted four numbers since
round 110 with nothing re-executing any of them. `round110_claims` runs all
four on today's tree, at round 110's own population size (264 programs):

| the comment says | round 383 measures | |
|---|---|---|
| "examples <= 19" | **19** (`blame.lang`) | exact |
| "most fuzz programs 5-20" | 214 of 235 (91.1 %), p50 11, p90 17 | exact |
| "the fuzzer's `1 + 1 + ...` chains 98" | **98** | exact |
| "nested list literals 59" | 58, at the deepest parseable depth (**59**) | off by one — 59 is the DEPTH |

(29 of 264 seeds hit the 10 s guard and are excluded; the count is reported
rather than dropped silently, because a dropped program biases the very
distribution being compared.)

**This is the first multi-number claim in this program's stale-number sweeps
that fully reproduces**, and the reason is structural, not luck. Every one of
round 110's numbers is pinned by a LANGUAGE CONSTANT — 98 is
`FAST_MAX_DEPTH - 2`, 59 is `MAX_NESTING - 1`, and the examples are checked-in
files. Round 337's comment in the same suite asserts a CORPUS rate (213 of
400 = 53 % reflective) and that one has drifted to **92.0 %** in 46 rounds.

> A comment asserting a number derived from a CONSTANT survives. A comment
> asserting a number derived from a CORPUS does not. Round 321 item 14's
> sweep should sort by which kind it is before spending a round on it.

### 3.6 A bug found and fixed: an injected-bug test that has not injected a bug since round 368

`test_swe_oracles.py::test_fast_slow_fires_on_an_injected_fast_path_bug`
monkeypatches `interp._compile_binop` with a 5-parameter stub to make the
compiled `-` closure compute `+`, then asserts `fast_slow` reports a
`mismatch`. Round 368 (`f568a79`, "a value's SIZE is a budget too") added a
sixth parameter, `interp`. Since then the patched factory has raised
`TypeError: bad_factory() takes 5 positional arguments but 6 were given`,
`run_oracle` has turned that into `kind == "crash"`, and the assertion has
failed.

**The test has been RED at HEAD for 15 rounds and nobody saw it**, because
`harness/run_tests_fast.sh` deselects `test_swe_*.py` — the same mechanism
round 371 found hiding a stale pin in `test_swe_guest.py`, now confirmed in a
second file. This is a *second-order* instance of the whole round's theme:
the check that would have caught the language change was itself not run.

Fixed by forwarding `*rest` instead of naming every parameter. The injection
only cares about `op`; the remaining arguments are `_compile_binop`'s private
signature and this test has no stake in them. `test_swe_oracles.py`: **37
passed** (was 36 passed, 1 failed).

## 4. Round 377's item 1, discharged

`exemptaudit sweep 1500 --budget-s 900` resumed from the 308 rows on disk and
added **305** (933 s, stopped by budget, `nproc` = 1).

**613 seeds. `host_valued` still 0.00 %.** The depth exemption fired on 3
seeds (0.49 %), all `both_missed`, `guest_valued` 0. Kinds: 605 `ok`, 8
`timeout`. Median 0.79 s, mean 2.54 s, max 70.76 s.

The one-sided 95 % upper bound on the blind-spot rate tightens from ~1.0 %
(n = 308) to **~0.49 %** (n = 613). Round 377's structural finding is
unchanged and is still the real evidence: the band is `(400, 1000000]` and the
corpus's maximum guest-depth demand is 25.

## 5. Predictions: 12 HIT, 8 MISS of 20

Banked at `state/swe/round-383/PREDICTIONS.md` before the first measurement,
in one block, after reading `oracles.py` to identify the eight sites and
before running anything against them. Result: **12 HIT, 8 MISS of 20.**

| # | claim | result |
|---|---|---|
| P1 | R-CAP: median bindings > 6 **and** > 50 % of programs above the cap | **MISS** — median exactly 6, 39.6 % above |
| P2 | < 40 % of render pairs checked | **MISS** — 52.4 % |
| P3 | F-SLACK: zero over 140, max in 60..120 | **HIT** — 0, max 98 |
| P4 | a chain crosses 140 at length 100..200 | **MISS** — it never crosses; saturates at 98 |
| P5 | T-SPACE fires 0 times, max demand < 100 | **MISS** — 10.8 %, real demand up to 3001 |
| P6 | T-NONE < 20 % | **MISS** — 36.9 % |
| P7 | `whole == False` on > 50 % | **HIT** — 92.0 % |
| P8 | T-ALL < 5 % | **HIT** — 2.1 % |
| P9 | P-NONE > 30 % | **HIT** — 56.3 % |
| P10 | P-EXEMPT < 10 %, `typed` clause exactly 0 | **HIT** — 6.8 %, 0 |
| P11 | < 10 % of programs reach multiplicity 2 | **HIT** — 6.8 % (but 62.2 % of the applicable population) |
| P12 | some oracle times out on >= 1 % | **MISS** — worst is `determinism`/`frames` at 0.67 % |
| P13 | `frames` slowest by median | **MISS** — `determinism` 0.0070 s vs `frames` 0.0056 s |
| P14 | a round-110 number fails to reproduce within 20 % | **MISS** — all four reproduce, see §3.5 |
| P15 | guest sweep resume lands at 550..750 seeds | **HIT** — 613 |
| P16 | `host_valued` stays 0 | **HIT** |
| P17 | >= 15 tests, all passing | **HIT** — 24 |
| P18 | at least one site fires at exactly 0 | **HIT** — F-SLACK, and P-EXEMPT's `typed` clause |
| P19 | 8 oracles over one program < 1.0 s median | **HIT** — ~0.04 s |
| P20 | a site with a low rate sitting AT the boundary | **HIT** — P-EXEMPT: 6.8 %, max demand 200 % of threshold |

**Five of the eight misses share one cause and it is the round's own lesson.**
P1, P2, P4, P5 and P6 all predicted the corpus would be FAR from a boundary.
I had just written up round 377, whose result was "the corpus runs at 6.25 %
of the ceiling", and I generalised a single measurement into a prior about
oracles in general. The correction is small and specific: *round 377's finding
was about a ceiling chosen for a guest interpreter's stack budget. A cap chosen
for a loop's cost (`names[:6]`) and a budget chosen for a host's recursion
limit (`max_depth`) have no reason to sit anywhere near it.* Read the constant's
PURPOSE before predicting the corpus's distance from it.

P12 and P13 are the same error in miniature: both were reasoned from a
mechanism ("`setprofile` must be slow") rather than from the ~10 s measurement
that was available before banking. That is round 377's own P2/P12 failure
shape, repeated.

## 6. Honest failures

* **`measure` disagreed with the oracle it describes, and the cross-check
  caught it.** `frame_excess` reported 8 on seed 7 where `oracle_frames`
  reported 11. Cause: direct mode caches compiled fast-path closures **on the
  AST nodes**, so measuring an AST that has already been executed skips the
  compilation frames. My `measure` ran the program once for R-CAP and then
  handed the *same* AST to `frame_excess`. **`frame_excess` is not a pure
  function of the source.** Fixed by parsing a fresh AST per run;
  `test_measure_agrees_with_the_oracle_it_describes` is the reason it was
  found and not shipped.
* **The registry's first `verify_sites()` run failed, correctly.** The anchor
  `if not a["vals"] and not whole:` occurs twice — once in the tail oracle at
  4-space indent, once in the param oracle at 8-space, and the first is a
  *substring* of the second. Anchored on a two-line form instead.
* **Three witness programs were written in syntax the language does not have**
  (`shape S = @{a: "int"}`, `fn g(y: "int")`) and skipped silently under
  `pytest.skip`. A skipped witness is a zero that looks like a pass — the exact
  failure the skill's "zero can mean the instrument never ran" pitfall names,
  committed while implementing that skill. Two were caught on the first run;
  the third survived a whole green run (`23 passed, 1 skipped`) because a
  skip in a 24-test file does not read as a problem. All three `pytest.skip`
  escape hatches are now hard assertions.
* **A fourth witness could not be written at all as first designed.** Whence's
  parser refuses same-block rebinding, so `shape S = ...` followed by
  `let S = ...` is a `ParseError`, not a twice-bound name. The exemption's
  comment ("bound more than once anywhere in the program") describes a
  condition the language admits in exactly one shape — a nested-scope shadow.
* **The sweep is 746 seeds, not the 2000 it was launched for.** `nproc` = 1
  with a concurrent guest sweep; stopped by its own 800 s budget. Ten programs
  hit the per-program guard (`measure_error: timeout`) and are excluded from
  `usable`; before the guard, one runaway seed cost the 20-seed pilot 10.95 s
  of its 30.1 s.
* **The full slow suite was not run.** `test_swe_guest.py` alone is ~346 s and
  the two sweeps had the CPU. Labelled NOT RUN in §7, not implied green.
* **Nothing here is fixed.** Every finding is made visible and measured; the
  caps, thresholds and exemptions are all still exactly as they were. Round
  371's rule — reddening a known divergence buries the unknown ones — applies
  to all four.

## 7. Verification

See the round entry in `state/research-state.md` for the command table.

## 8. What a later round should take from this

1. **Raising `max_depth` from 500 to 5000 converts 70 of 73 silent T-SPACE
   exemptions into real comparisons**, at a cost the ladder measured (31.9 s
   for all 73 seeds). That is the single cheapest coverage gain in the suite.
2. **`render`'s `names[:6]` should either be lifted or reported.** 6 426 of
   13 509 pairs are silently unchecked. If the cap is a cost decision, the
   oracle's `detail` should carry `checked k of n pairs` the way
   `oracle_frames`' detail carries its excess.
3. **`FRAME_SLACK` needs to know about `FAST_MAX_DEPTH`.** Today the relation
   is asserted only by this round's test. Deriving the slack (e.g.
   `FAST_MAX_DEPTH + 40`) would make the coupling explicit in the code rather
   than in a test.
4. **Round 321 item 14's sweep now has a sort key.** Round 337's 53 % is
   today's 92 % (a corpus rate, 46 rounds); round 110's four numbers are all
   exact (constant-derived, 273 rounds). The sweep round 333 asked to be
   rescoped should triage by *what the number is derived from* — a claim
   pinned by a constant is cheap to re-verify and rarely wrong, a claim
   pinned by a corpus is the whole problem. This is the fifth independent
   instance of the class and the first found by a tool built to look for it.
5. **`round110_claims` is the shape of that tool** — a function that
   re-executes a comment's numbers and prints them beside what the comment
   says. It cost ~40 lines. Generalising it (a `# CLAIM: n=98` marker a
   checker can find and re-run) would close the class rather than sample it.
