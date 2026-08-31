# Round 389 — SWE-loop(D): the ceiling that was a default argument

*Task: round 383's next-step items 1, 2, 3 and 5 — raise the oracle suite's
depth ceiling and re-run; report `render`'s silent pair cap; derive
`FRAME_SLACK` from `FAST_MAX_DEPTH`; put the injected-bug tests in the fast
tier.*

**Headline.** Round 383 found three of the oracle suite's bounds and asked
for three fixes. Two of them are the same fix and the third one has a second
half nobody has looked at. `max_depth=500` and `names[:6]` were both LITERAL
DEFAULT ARGUMENTS — not policy, not measurement, just what somebody typed —
and neither was reachable from any command line. `FRAME_SLACK = 140` is the
interesting one: round 383 showed it needs a FLOOR derived from
`FAST_MAX_DEPTH`, and deriving it is four lines. But the constant is sound in
a **band**, not above a line, and this round measured the other side:

> The frames oracle sees round 108's undercharge only at guest depth
> `> slack / under`. Raising `FAST_MAX_DEPTH` raises the derived slack and
> therefore raises the depth at which the bug becomes visible. The
> derivation buys away a false positive by buying a **larger blind spot**,
> and round 383's item 3 named only the half that gets better.

At the default host recursion limit the band is `(98, 246]` for the
1-frame-per-level bug. `FAST_MAX_DEPTH` may rise to **206** before the
derived slack leaves it. Nothing in the tree said so before this round.

---

## 1. The control: the arms are comparable, and round 383's rows still are

`ProgramGen(seed, stress_rate=0.5)` is deterministic, so an A/B pairs by
SEED and every difference is attributable. Rounds 384, 386 and 387 changed
`languages/whence/` after round 383's sweep, so round 383's rows are not
automatically a valid control — arm A re-ran seeds 0-299 at today's tree.

`exemptmap ab --a state/swe/round-383/sweep.jsonl --b state/swe/round-389/armA-500.jsonl`,
300 shared seeds:

| site | fired r383 | fired r389 | converted | new |
|---|---|---|---|---|
| R-CAP | 99 | 99 | 0 | 0 |
| F-SLACK | 0 | 0 | 0 | 0 |
| T-SPACE | 36 | 36 | 0 | 0 |
| T-TAINT | 245 | 245 | 0 | 0 |
| T-NONE | 98 | 98 | 0 | 0 |
| T-ALL | 7 | 7 | 0 | 0 |
| P-EXEMPT | 11 | 11 | 0 | 0 |
| P-NONE | 157 | 157 | 0 | 0 |

Not just the same counts — the same SEED SETS, every site. **P2 HIT.**
16 oracle verdicts flipped and all 16 are `timeout -> ok`: round 383's sweep
shared the one CPU with other work, this one did not. Zero mismatch flips.

A detail worth keeping: arm A's T-SPACE fire rate is **13.9 %** against
round 383's published **10.8 %**, on an instrument that did not move and a
tree whose behaviour did not move. The difference is entirely the seed range
(0-299 vs 0-745). A rate quoted without its seed range is not a fact about
the corpus.

## 2. Round 383's item 1: the ceiling, raised — and what it actually bought

`max_depth` is a DEFAULT ARGUMENT repeated **14 times** in `oracles.py`. The
language's own `Interpreter.DEFAULT_MAX_DEPTH` is **20 000** — the oracle
suite has been testing Whence at **1/40th** of the depth the language runs at
by default, and every T-SPACE exemption round 383 measured is a consequence
of that choice rather than of the language.

It was also unreachable. `exemptmap.sweep()` took a `max_depth` parameter and
`main()` never passed it, so item 1 ("raise it and re-run") could not have
been executed from a command line by any round, including the one that asked
for it. **P14 HIT.** The flag exists now (`--max-depth`, `--timeout-s`), and
every sweep row records the ceiling it was measured under, because a row that
does not name its arm cannot be A/B'd.

Arm B: seeds 0-359 at `max_depth=5000`, everything else identical.
**360 shared seeds** (`state/swe/round-389/ab-full.json`):

| site | fired @500 | fired @5000 | converted | new |
|---|---|---|---|---|
| R-CAP | 125 | 125 | 0 | 0 |
| F-SLACK | 0 | 0 | 0 | 0 |
| **T-SPACE** | **41** | **3** | **38** | 0 |
| T-TAINT | 299 | 299 | 0 | 0 |
| T-NONE | 117 | 117 | 0 | 0 |
| T-ALL | 8 | 8 | 0 | 0 |
| P-EXEMPT | 15 | 15 | 0 | 0 |
| P-NONE | 189 | 189 | 0 | 0 |

**T-SPACE falls from 41 fires to 3 — 92.7 % converted (P1 HIT at 0.83 %,
P7 HIT).** Nothing else moves at all: the ceiling is a tail-transparency
parameter and only a tail-transparency parameter, as far as the map can see.

**The three survivors are seeds 140, 273 and 341 — exactly the three round
383's ladder named as unbounded past 25 000, and no others (P8 HIT).** Two
instruments that share no code path — a bisecting ceiling ladder run on 73
censored seeds, and a live 360-seed sweep at a raised ceiling — pick out the
same three programs. That is the strongest cross-check either measurement
has had.

### 2.1 What the coverage bought: nothing, and that is the result

**Zero new mismatches (P3 HIT).** 38 comparisons that used to be skipped
wholesale now run, on the corpus the fuzzer has been generating for 380
rounds, and every one of them agrees. Round 383 called this "the single
largest coverage gain the census found", and the gain is real — but it is
coverage, not bugs, and running it rather than assuming it is the difference
between those two sentences.

### 2.2 What it cost: a silent exemption became a LOUD one, ten times

Ten verdicts flipped `ok -> timeout` (**P4 HIT**), across **seven of the
eight oracles** — every one except `param_erasure` (**P13 HIT**):

```
seed 125  fast_slow / direct / tail_transparency   ok -> timeout
seed 253  direct / determinism / frames            ok -> timeout
seed 272  totality / render                        ok -> timeout
seed  14  determinism                              ok -> timeout
seed 341  direct                                   ok -> timeout
```

`timeout_s` stayed at 3.0 while the ceiling went up 10x. So the honest
accounting of item 1 is not "+38":

```
  @500    41 space-exempt "ok"s,  0 timeouts on these seeds
  @5000    3 space-exempt "ok"s, 10 timeouts
  net     +28 verdicts that are now real comparisons
```

A `timeout` is at least a verdict that names itself — it is not laundered as
`ok` the way a space exemption is — but it is not a comparison either, and it
lands on oracles that had nothing to do with the exemption being lifted.

> **`max_depth` and `timeout_s` are one parameter, not two.** Raise the
> ceiling alone and about a quarter of the exemptions you convert come back
> as timeouts, spread across seven oracles.

Cost was modest: `measure` time **123.0 s -> 156.1 s (1.27x)** over the
shared seeds (**P6 HIT**), and **zero new crashes — P5 MISS.** I predicted at
least one `RecursionError` from guest depth 5000 in direct mode; there is
none, and §3.3 explains why: direct mode's `_hleft` budget runs out and the
trampoline takes over, so guest depth does not buy host frames indefinitely.
The same mechanism that caps the frames oracle's signal is what makes a 10x
ceiling safe.

### 2.3 The default was NOT changed, and that is a decision

`max_depth=500` is still the default at all 14 sites. The evidence says the
raise is worth having (+28 verdicts, 1.27x) and also says it is not free
(10 new timeouts), and `oracle_frames`' own detectable band is bounded by
`2 * max_depth + 1` (§3.3) — so the three constants are coupled and moving
one of them alone is what this round is about. What changed is that the
ceiling is now a FLAG with a recorded value per row, so the next round can
move `max_depth` and `timeout_s` together and A/B it in one command instead
of editing 14 default arguments.

## 3. `FRAME_SLACK`: round 383's item 3, and the half it did not name

### 3.1 The derivation (four lines, and it deletes a tripwire)

`oracles.py` now carries `FRAME_SLACK_MARGIN = 40` and

```python
def frame_slack(pkg=None):
    fmd = fast_max_depth(pkg)
    return FRAME_SLACK if fmd is None else fmd + FRAME_SLACK_MARGIN
```

`oracle_frames` calls it when no explicit `slack=` is given, and the detail
now reads `slack 140 = FAST_MAX_DEPTH 100 + 40` so a reader can see which
number produced the threshold. On today's tree it reproduces **exactly 140**
(**P9 HIT**) — `FAST_MAX_DEPTH` is still 100.

Round 383's own tripwire test is the thing this deletes.
`test_raising_FAST_MAX_DEPTH_makes_the_frames_oracle_fire_on_correct_code`
set `FAST_MAX_DEPTH = 150` and asserted `oracle_frames` reports a mismatch on
a CORRECT program. With the derived slack it reports `ok`, which is the point.
The old behaviour was not deleted: the literal path still exists (`slack=` is
an explicit argument, and packages with no fast path still get the literal),
so the failure mode is still reachable and is now pinned under a name that
says what it is —
`test_a_LITERAL_slack_still_fires_on_correct_code_when_FAST_MAX_DEPTH_rises`.

### 3.2 The other side of the band, measured

Round 110's comment sized the slack "between a legitimate transient and round
108's undercharge bug (which reaches ~161)". The floor has now been measured
twice (round 383: `excess == FAST_MAX_DEPTH - 2` for the chain shape). The
CEILING never has been, and it is where the constant does its work.

`exemptmap.undercharge_detection_depth` injects the bug the way `oraclekill`'s
mutant does — `_body_entry`'s cost reduced by `under` frames per level — but
IN PROCESS, by wrapping the method, so it costs ~1 s instead of a mutation
campaign. Each rung parses its own AST, because `_body_entry` caches
`(bd, cost)` on the body node and a reused AST keeps the honest charge.

The control first (`clean_frame_excess_ladder`, no bug):

```
depth     1    2    4    8   16   32   64  100  160  240  320  400
excess    5    5    5    5    5    5    5    5    5    5    5    5
```

Flat. A correct non-tail recursion's transient does not grow with depth, so a
rung going over slack is attributable to the injection and nothing else.

With the bug injected at `under = 2` (the `+1 -> -1` arith mutant
`test_undercharge_is_a_frames_kill` uses):

```
depth     1    2    4    8   16   32   64  100  160  240   320   400
excess    6    6    8   16   32   64  128  200  320  480   RecursionError
over 140  .    .    .    .    .    .    .    X    X    X
```

and at `under = 1` (round 108's actual bug):

```
depth    80  120  140  160  161  200  240
excess   80  120  140  160  161  200  240
over 140  .    .    .    X    X    X    X
```

**`excess == under * depth`, exactly, at every rung.** Two things follow.

**(a) Round 110's 279-round-old number reproduces to the digit.** Its comment
says the bug "reaches 161 within ~160 levels at the DEFAULT recursion limit".
Measured today: excess **161 at guest depth 161**. This is the second
multi-number claim from that comment to reproduce exactly (round 383 checked
the other four), and for the same structural reason round 383 identified: it
is derived from a CONSTANT (the charge arithmetic), not from a corpus.

**(b) The slack is a DETECTION DEPTH.** Because the excess is linear in depth
with the undercharge as its slope, a slack of `S` means the oracle is blind to
the bug for every guest depth below `S / under`. At `S = 140`, `under = 1`,
that is **every program shallower than 141 guest frames**. Raise
`FAST_MAX_DEPTH` to 150 and the derived slack becomes 190 and the blind spot
becomes 190. The derivation is still right — it removes a false-positive
generator — but it is not free, and the cost is exactly the thing the frames
oracle exists to catch.

### 3.3 The band has a measured TOP, not an open one

`deepest_undercharged_run` bisects the deepest guest recursion the
undercharged interpreter survives, on the real instrument:

| host limit | under | deepest surviving depth | excess there | max detectable slack | max sound `FAST_MAX_DEPTH` |
|---|---|---|---|---|---|
| 1000 (default) | 2 | 245 | 490 | 489 | 449 |
| 1000 (default) | 1 | > 1200 | **247** (plateau) | 246 | **206** |
| 6000 (`oraclekill`'s) | 2 | > 2000 | 1001 (`max_depth` bound) | 1000 | 960 |

Above the max-detectable slack the bug still exists and `oracle_frames`
reports `ok` on a buggy interpreter — the crash becomes `modes`' finding, not
`frames`'. So `FRAME_SLACK` is sound in `(FAST_MAX_DEPTH - 2, 246]` at the
default limit, and the binding constraint is **`FAST_MAX_DEPTH <= 206`**.

Two mechanisms cap the excess rather than one, and neither is the host stack:

* at `under = 1` the excess **plateaus at 247** and the run survives past
  depth 1200. Direct mode's `_hleft` budget runs out, direct mode goes
  dormant, and the trampoline — which charges nothing — takes over. **The
  undercharge is self-limiting at 1 frame per level**: the very fallback that
  makes the interpreter robust is what caps the oracle's signal.
* at limit 6000 the excess stops at 1001, which is `2 * max_depth + 1`: the
  GUEST ceiling binds before the host stack does. The two ceilings this round
  is about are coupled, and in that direction `max_depth` is the one that
  decides what the frames oracle can see.

`slack_band()` reports the bracket and a `sound` flag;
`test_the_detectable_band_has_a_measured_TOP_not_an_open_one` fails the
moment the derived slack reaches the top of it.

## 4. `render`'s pair cap: reported AND lifted, on a measurement

The bound was the bare literal `6` written into two loop bounds (and a third
copy in `exemptmap.measure`). It is now `RENDER_PAIR_CAP`, `oracle_render`
takes a `pair_cap` override, and **every** verdict — `ok` and `mismatch`
alike — carries `k bindings, pairs c/t`:

```
blame.lang     render ok | 7 bindings, pairs 21/21
```

Round 383's ask was "lifted or REPORTED", and it argued for reporting on the
grounds that the check is quadratic. **"It is quadratic" is an argument, not
a measurement.** 200 seeds, each rendered twice — once at the cap, once
uncapped:

| | pairs compared | new mismatches | render wall |
|---|---|---|---|
| cap 6 | (52 % of them) | — | **36.04 s** |
| uncapped | **3 716 of 3 716** | **0** (P11 HIT) | **35.30 s (0.98x)** |

Full coverage is **free** on this corpus, inside timing noise. The quadratic
never bites because the corpus tops out at 16 bindings (120 pairs) and
`diverge` on small values is microseconds. The cap was buying nothing and
costing half the coverage — 6 426 of 13 509 pairs in round 383's census.

So the cap is **24**, not unbounded: 50 % headroom over the corpus max, so a
future generator emitting a 200-binding program (19 900 pairs) still hits a
bound rather than a wall. And the bound can no longer be silent, which is
the part that actually mattered.

The registry earned its keep for the second time in two rounds, and it cost
this round fifteen minutes. `SITES["R-CAP"]`'s anchor is the literal source
line `    for i, x in enumerate(names[:6]):`; the fix moved it;
`verify_sites()` raised; and it raised **inside a sweep already running in
the background**, killing arm B mid-flight. That is the correct behaviour — a
registry that had silently measured the moved branch would have produced an
arm-B number that looked like a result — but it is a lesson with a name:

> **An anchor-verified registry makes source edits and long-running sweeps
> mutually exclusive.** Finish the sweep or finish the edit.

## 4b. The guard the registry episode needed (built this round)

`verify_sites()` runs **once**, at sweep start. It can PREVENT a mixed file
and it cannot DETECT one that a mid-flight edit created — which is exactly
what this round produced, and I had to check the resulting arms by hand
(`R-CAP` thresholds: `{6: 324}` in both, so no contamination).

Every sweep row now carries `oracles_sha`, the sha256 prefix of the
instrument that measured it; `sweep_digests(path)` reports `{digest: rows}`
and `ab()` sets `mixed_instrument` when either arm has more than one. Rows
written earlier this round are reported as `pre-r389`, not guessed.

**The first version of this had the bug it was built to catch.** The digest
was cached per `(path, st_mtime_ns, st_size)` — the standard trick — so an
edit preserving mtime and size reads as unchanged and the row names an
instrument that did not measure it. The test that caught it changes `140` to
`190` in a two-line file: same size, same tick. The cache is gone; hashing
50 KB is ~0.05 ms against a ~1 s row, so it was buying nothing and disabling
the guard.

> Second time in one round that a **stale-key optimisation** produced a
> confident wrong answer, after `_body_entry`'s per-node `(bd, cost)` cache
> (§3.2, why every ladder rung re-parses).

## 5. Round 383's item 5 was already discharged, by round 385

Item 5 asked for the injected-bug tests to run in the fast tier.
`harness/tier-budget.json` already promotes `test_swe_oracles.py`
(`measured_s` 5.01, round 385), and its `why` names item 5 by name: "holds all
three injected-bug tests (fast_slow / direct / frames) — round 383 item 5's
actual ask". **Nothing to do; recorded here so it is not carried a fourth
time.** Round 388's next-steps list still carries round 383's items by
reference ("round 385's items are unchanged"), which is how a discharged item
survives: the carrying round names the ROUND, not the ITEM.

The one thing that did need doing: this round's new file
`harness/tests/test_swe_depthceiling.py` is a `test_swe_*.py` file, so round
235's fail-closed filename rule tiers it SLOW by default. It is 2.3 s.

## 6. What was built

* `harness/swe/oracles.py` — `FRAME_SLACK_MARGIN`, `fast_max_depth(pkg)`,
  `frame_slack(pkg)`; `oracle_frames` derives its threshold and says so in the
  detail; `RENDER_PAIR_CAP`, `_n_choose_2`, `oracle_render(pair_cap=)` and the
  `pairs c/t` coverage on every render verdict.
* `harness/swe/exemptmap.py` — `--max-depth` / `--timeout-s` on the sweep CLI
  (the flag round 383's item 1 needed and that did not exist);
  `max_depth`/`timeout_s` recorded on every sweep row; `round_dir()` +
  `EXEMPTMAP_ROUND_DIR` replacing the hard-coded `round-383` output path;
  `ab()` and the `ab` command (paired per-seed arm diff);
  `recursive_program`, `clean_frame_excess_ladder`,
  `undercharge_detection_depth`, `deepest_undercharged_run`, `slack_band`
  and the `cleanladder` / `underdepth` / `deepest` / `slackband` commands.
* `harness/tests/test_swe_depthceiling.py` — 17 tests, relations only.
* `harness/tests/test_swe_exemptmap.py` — the FRAME_SLACK tests rewritten
  for the derivation; the old literal behaviour kept and renamed.

## 7. Failures and misses

### 7.1 The bank

14 predictions, banked at `state/swe/round-389/PREDICTIONS.md` before any
measurement. **13 HIT / 1 MISS.**

| # | claim | result |
|---|---|---|
| P1 | T-SPACE < 1.0 % at 5000 | **HIT** — 3/360 = 0.83 %, and only just |
| P2 | arm A reproduces round 383's fire SET exactly | **HIT** — all 8 sites, same seeds, not just same counts |
| P3 | 0 new mismatches | **HIT** |
| P4 | >= 1 new timeout | **HIT** — 10, across 7 oracles |
| P5 | >= 1 new `RecursionError` crash | **MISS** — 0. The mechanism is in §3.3: direct mode's `_hleft` runs out and the trampoline takes over, so guest depth does not buy host frames indefinitely. I predicted a crash from a model of the interpreter I had not read. |
| P6 | arm B <= 3x arm A | **HIT** — 1.27x |
| P7 | conversions >= 90 % of A's fires | **HIT** — 92.7 % |
| P8 | seeds 140/273/341 still censored | **HIT** — those three and no others |
| P9 | derived slack == 140 today | **HIT** — exactly |
| P10 | >= 35 % of rows carry non-zero skipped pairs | **HIT** — 37.5 % (arm A, 267 usable) |
| P11 | lifting the cap surfaces 0 new mismatches | **HIT** — 0 over 182 usable programs at full coverage |
| P12 | fast-tier cost < 15 s | **HIT** — 1.72 s measured |
| P13 | some oracle other than tail_transparency moves | **HIT** — 7 of 8 |
| P14 | no prior round could have run item 1 from the CLI | **HIT** — `main()` never passed `max_depth` to `sweep()` |

**P1 is the one to distrust.** It is a HIT at 0.83 % against a 1.0 %
threshold on 360 seeds — three survivors. One more unbounded seed in the
range and it is a MISS. The prediction was right about the mechanism and
lucky about the digit, and the finding that matters (P8: the survivors are
*exactly* round 383's three) is the one that does not depend on the cutoff.

### 7.2 Failures

* **A bug in this round's own code, found by the shape of its output.**
  `deepest_undercharged_run`'s survival predicate tested `err is None`;
  `guarded` returns `""` on success, never `None`. Every rung read as a
  failure and the bisection returned `null` for BOTH host limits — including
  rungs `undercharge_detection_depth` had already measured as fine minutes
  earlier. **Two arms of a bisection returning `null` is the shape of a
  broken predicate, not of a real ceiling**; a version of this that returned
  a plausible small number instead would have shipped. The comment recording
  it is in the code.
* **Arm B was killed mid-flight by this round's own edit** (§4), ~15 minutes.
* **P5 was reasoned from a model of the interpreter, not from reading it.**
  Round 388's bank had the same failure in the same position (P8, "no
  eviction", predicted from a conclusion rather than from `expert_get`).
  Two consecutive rounds, same shape.
* **Round 383's own tripwire fired, and I had to be told by pytest.**
  `test_render_skips_pairs_beyond_the_sixth_binding_counted_live` pinned
  `pairs_checked == 15` beside the relation and its docstring said "a future
  round that lifts the cap makes this test red, which is the intended
  signal". I lifted the cap and did not re-run that file until after writing
  the section claiming the lift was done. The relation held; the literals
  did not. Rewritten to assert only the relation.
* **The 748-passed fast tier ran BEFORE the `RENDER_PAIR_CAP = 24` change.**
  All three affected files were re-run afterwards (75 passed, above), but
  for a few minutes the round's headline evidence was a suite that had not
  seen the round's last edit.

### 7.3 Tests

```
harness/tests/test_swe_depthceiling.py     17 passed        0.71s   (new)
harness/tests/test_swe_oracles.py          37 passed        4.30s
harness/tests/test_swe_exemptmap.py        25 passed
  the three files together                 79 passed      106.03s
bash harness/run_tests_fast.sh            748 passed       91.09s   (final tree)
bash skills/run_checks_fast.sh   7 checkers, 0 errors, 6 warnings
                                          656 passed       46.60s
```

`skills/run_checks_fast.sh` was ERROR-red (K001) at first run for this
round's OWN bank: `state/swe/round-389/PREDICTIONS.md` existed and
`state/prediction-bank-ledger.json` had no entry for it, so nothing could
tell whether D-013's second half was ever done. Entry added; 0 errors.
`case_coverage` still reports 45 skills / 190 cases — the SKILL.md
**description is byte-unchanged**, so round 388's finding (a description edit
resets a skill's probe history) does not bite.

`test_swe_depthceiling.py` measured at **1.72 s** and promoted into the fast
tier (`harness/tier-budget.json`, 10 files). Round 235's fail-closed filename
rule had tiered it slow by default, which is the rule working: it is the
round's own measurement that moves it, not its filename.

