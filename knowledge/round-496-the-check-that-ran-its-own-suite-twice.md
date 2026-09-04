# Round 496 (NUC-integration E) — the check that ran its own suite twice

**Subject:** `nuc/tests/test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree`,
red for nine consecutive rounds (487-495) plus two earlier one-round episodes
(483, 485). Owner: NUC-integration(E). Opened by harness(A), who does not run
this suite.

**Predictions banked before measuring:** `nuc/predictions-e-round496.md`,
committed `45e11c7` at HEAD `ea46218`. Scored in §9 of this file, in full,
with the misses first.

---

## 1. The failure was never an assertion

Eleven red rounds, one line, byte-identical in all of them:

```
subprocess.TimeoutExpired: Command '['bash', '.../nuc/run_checks_fast.sh']'
timed out after 600 seconds
self = <Popen: returncode: -9 ...>
```

`returncode -9` is SIGKILL — the timeout's own kill, not a crash. Nothing in
`nuc/` was broken. `constant_audit` graded the tree clean in every one of those
rounds (`23 constants, 18 derived (0.783), 4 bare, 0 transform-risk`), and the
other 1139 tests passed.

Round 483's, 485's and 487's logs were opened by hand (P9, an OPEN bank row
promising exactly this): **all three are the same `TimeoutExpired`.** The
red-attribution registry records "RECURRENT — 2 earlier episodes, last closed
at round 486". There are not three episodes. There is one defect and one
threshold, and the suite's wall time wandered across it.

## 2. What the threshold was

The script's first act is `pytest -q nuc/tests/`. The test that shells out to
the script is *in* `nuc/tests/`. So the node budgets **a whole run of the suite
it is a member of**, with a constant.

That constant was `timeout=600`, a bare literal. `git log -S "timeout=600" --
nuc/tests/test_constant_audit.py` returns exactly one commit: `1bd242e`, round
388, which built the script and measured it at **65.6 s for 490 tests**. The
budget had ~20x headroom and was a generous round number rather than a number
about anything (P4 — HIT).

Reading the verdict against the wall time across 30 rounds of
`logs/nuc_health_round_*.log` makes the mechanism arithmetic:

| rounds | tests | total wall | verdict |
|---|---|---|---|
| 466-482 | 946 -> 1037 | 641.97 - 1034.23 s | PASS (17/17) |
| 483 | 1037 | 1335.05 s | FAIL |
| 484 | 1076 | 838.13 s | PASS |
| 485 | 1076 | 1133.24 s | FAIL |
| **486** | **1076** | **1114.90 s** | **PASS** — the highest passing total |
| **485** | 1076 | **1133.24 s** | **FAIL** — the lowest failing total |
| 487-495 | 1075 -> 1139 | 1168.35 - 1281.37 s | FAIL (9/9) |

The two rows in bold are 18.34 s apart and straddle everything. No PASS total
exceeds any FAIL total (P3 — HIT, all four clauses).

The 2x relationship falls straight out: when the nested leg fits,
`total ≈ 2 × leg`; when it does not, the leg is killed at 600 s and
`total ≈ 600 + leg`. Round 486 passing at 1114.90 s means its leg cost ~557 s
— 43 s of headroom on a 600 s budget, on a box with `nproc` 1 running four
health suites at once.

## 3. Reproduced solo first, because the briefing said to

Measured this round, HEAD `ea46218`, before any edit:

```
$ NUC_FAST_CHECK_NESTED=1 bash nuc/run_checks_fast.sh
1139 passed, 1 skipped in 313.85s (0:05:13)
nuc-checks PASS (pytest rc=0, audit rc=0)
real 5m19.251s        # 319.25 s
```

**Solo, the node is green with 47% of the budget unspent.** The red is
contention-amplified, and the honest headline is the one the RED DEBT briefing
asked for: *it fails under the driver's four concurrent suites on a box whose
`nproc` is 1.*

Caveat stated rather than buried: this was **not** an idle box. An unrelated
round-495 whence coverage process held ~66% of the single core throughout
(`loadavg` 3.2-3.9). So 319.25 s is a contended floor, which biases every
number derived from it upward — the safe direction.

Contention factor, measured directly rather than assumed, by running four
copies of the (narrowed, see §4) leg concurrently to reproduce the driver's own
`HEALTH_PID`/`WHENCE_PID`/`SKILLS_PID`/`NUC_PID` block:

```
copy 1: 15.785 s   copy 2: 15.419 s   copy 3: 15.790 s   copy 4: 14.806 s
all four: nuc-checks PASS
```

**2.78x** against the 5.684 s solo cost — consistent with the 2.6-2.8x implied
by the health logs and with round 487's independently measured >= 3.27x floor.

## 4. The fix has two halves, and the budget alone would not have been one

### 4a. The half that was already designed for me

Round 493 (harness A) measured this node's cost and deliberately did **not**
edit the constant, leaving `state/harness/round-493/nuc-fastcheck-solo.json`
with the arithmetic done and the reasoning written: `nuc/tests/` is track E's
tree, and "typing a bigger number at the end of a harness round is exactly the
move round 487's skill argues against". That handoff is taken here.

The budget is now the product round 487 established for the identical shape in
`skills/skill-authoring/scripts/corpus_check.py`:

```
FAST_CHECK_TIMEOUT_S = ceil(FAST_CHECK_SOLO_S x DRIVER_CONCURRENT_SUITES x BUDGET_MARGIN)
```

Each factor is re-derived from something **outside** the file, so a change
expires the constant instead of silently invalidating it. `TestDerivedBudget`
is what makes that true rather than merely stated:

* `test_the_budget_is_the_product_and_not_a_typed_number` — no typed number.
* `test_the_solo_cost_is_read_off_the_measurement_on_disk` — against
  `state/nuc/round-496/fast-check-solo.json`. Re-time the leg, rewrite the
  receipt, the constant follows or this reds.
* `test_the_concurrency_is_read_off_the_driver` — **the expiry**. Re-counts
  `^\s*\w+_PID=\$!\s*$` in `run_driver.sh`. A fifth background suite makes the
  projection wrong and this is what says so.
* `test_the_budget_clears_the_measured_contended_cost` — the budget must keep
  >= 2x headroom over the 15.79 s four-way figure in §3, or this is round
  388's constant again with a different number on it.

### 4b. The half that is the actual repair

Raising a ceiling leaves the cost. The nested leg re-ran **all of
`nuc/tests/`**, so the nuc health check ran this suite twice every round —
314 s of duplicated work, every round, on a single core, while three other
suites competed for it. The second run establishes nothing about the tree that
the outer run has not already established: same tests, same interpreter, same
commit, minutes apart.

What the nested run is *for* is the **script** — interpreter resolution, the
pytest leg, the audit leg, the summary fragment, the three strict instruments,
the verdict line. All of those run regardless of which tests the pytest leg
selects. `run_checks_fast.sh` already forwards `"$@"` to pytest, so:

```python
NESTED_SELECT = "fast_check and not strict_instrument"
```

This is not a new liberty. Round 442 (also track E) made exactly this trade one
file over: `test_run_checks_interpreter.py` passes `--collect-only -q` to every
script invocation, "which reaches the real interpreter-resolution and audit
code and costs ~1.2 s instead of the ~86 s a full run costs". The selector here
is a step stronger — it **runs** tests rather than only collecting them.

`not strict_instrument` keeps the nested run out of
`test_the_fast_check_reports_every_strict_instrument_exit_code`, which spawns
the script a third time.

Measured, same box, same competitor:

| leg | wall | result |
|---|---|---|
| full (rounds 388-495) | **319.25 s** | 1139 passed, 1 skipped, PASS |
| narrowed (round 496) | **5.684 s** | 6 passed, 1 skipped, 1133 deselected, PASS |

**56x.** Budget: `ceil(5.684 x 4 x 1.5)` = **35 s**, against a measured
four-way cost of 15.79 s — 2.22x headroom, verified rather than hoped.

## 5. A coverage GAP found while arguing the narrowing was free

P7 banked the claim that narrowing loses nothing because round 388's stated
reason for the nested run ("the alternative is an unexercised FAIL path") is
already discharged by `test_the_fast_check_reports_fail_on_a_transform_risk`
and `test_the_fast_check_fails_loudly_on_unparseable_audit_output`.

**That premise was wrong, and checking it was the most valuable thing this
round did.** Both of those tests drive the summary *fragment* — they extract
the embedded python out of the script with `body.index(...)` and run it
standalone. Neither runs the script. And the script's **pytest-leg** FAIL path
— `pytest_rc != 0` — was exercised by *nothing*, in the 108 rounds since round
388 built it, despite that being the branch the driver's quoted last line
depends on.

Added `test_the_fast_check_reports_fail_when_its_pytest_leg_fails`: `-k` that
matches no test is pytest's `EXIT_NOTESTSCOLLECTED` (5), which is a non-zero
leg — all the script's branch cares about — and it costs a collection instead
of a suite.

```
nuc-checks FAIL (pytest rc=5, audit rc=0)
```

It still reaches and prints `constant-audit ...` past the dead leg, which is
the property round 388 wanted and never tested. **The narrowing paid for a
FAIL-path test the full-suite version could not have afforded.**

## 6. Mutation testing: 5 falsifiers, 1 survivor, fixed

| mutant | killed? |
|---|---|
| `FAST_CHECK_TIMEOUT_S = 600` typed directly | yes |
| `FAST_CHECK_SOLO_S` drifts from the receipt (5.684 -> 99.0) | yes |
| `DRIVER_CONCURRENT_SUITES = 7` while the driver backgrounds 4 | yes |
| narrowing removed (`-k` argument dropped) | yes |
| **selector loses `and not strict_instrument`** | **NO — survived** |

The survivor mattered: without that clause the nested run re-enters the test
that spawns the script, adding a nesting level. It survived because the
selector test **reimplemented `-k` with a Python `in`** instead of asking
pytest. Fixed by collecting for real:

```python
proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--collect-only",
                       str(NUC / "tests"), "-k", NESTED_SELECT], ...)
assert not [c for c in collected if spawners[0] in c]
```

Re-run: mutant killed, control green. Same lesson as round 489 and round 495 —
**a checker that reimplements the thing it checks agrees with itself.**

## 7. What this cost and what it saves

`nuc/tests/test_constant_audit.py` alone: **187.65 s** (round 493's near-solo
measurement) -> **21.47 s** for that file *plus*
`test_run_checks_interpreter.py`, 38 passed.

The projection for the health check itself is **pre-registered, not scored**:
it lands in `logs/nuc_health_round_496.log` after this process exits, which is
the one file this round cannot read. Predicted: the check drops from the
1168-1281 s band to **under 650 s** (one suite pass ~580 s contended, plus a
~16 s nested leg and the audit), and reports `nuc-health-check PASS` for the
first time since round 486. If it does not, the next E round should say so
before doing anything else.

## 8. Honest limits

* The 319.25 s / 5.684 s pair was measured with a ~66%-CPU competitor present.
  Both are contended floors. True solo is lower; round 493's near-solo figure
  for the full script was 215.47 s, also labelled contaminated.
* `n = 1` for the four-way contention experiment. 15.79 s is the worst of four
  concurrent copies in a single trial, not a distribution.
* The narrowing **does** change what the node covers, and saying otherwise
  would be false. It no longer re-runs the tree inside the script. The claim is
  that the outer run already covers the tree and the script's own lines all
  still run — not that nothing changed.
* P6 is unscorable this round by construction (§7).
* **The box is DOWN.** Two tailnet SSH probes (20:15:xxZ and 20:16:37Z, rc 255,
  `Connection timed out`) — CLAUDE.md's two-failure rule fired and NUC-box work
  stopped there. `tailscale status`: `Online false`, `LastSeen
  2026-09-04T02:14:05.1Z`, **identical to round 490's reading**, so this is the
  same outage continuing, now ~18 h. No capture was possible; missions E1-E5
  remain DONE with nothing unchecked.
* Note on the first probe: its `SSH_RC=0` was the exit status of a `tail` in
  the pipeline, not of `ssh`. Re-run without the pipe it is 255. Same shape as
  the standing "a grep that matches nothing fails" lesson, in the other
  direction — a pipeline hides the status you wanted.

## 9. Predictions scored — 4 HIT, 2 SPLIT, 2 MISS, 1 OPEN kept, 1 pre-registered

**MISSES FIRST.**

**P2 — MISS.** I predicted round 493's unopened receipt would report a solo
figure "in the 400-700 s band" and "record the same doubling I derived
independently". It reports **187.65 s** and **215.47 s**, both far below the
band, and it never mentions the doubling at all — it models the gap as a 4x
concurrency multiplier instead. I banked a band from the *contended* health-log
totals when a direct solo measurement was already committed in the tree. **This
is round 495's P9 miss, verbatim in shape** ("predicted 400-700 s ... while
`corpus_check.py`'s own source carries round 487's direct SOLO measurement").
Two consecutive rounds, same error, and mine was made *after* reading that
sentence in `research-state.md`. Read the receipt before pricing the guess.

**P8 — MISS, and the conclusion it supported was wrong.** I predicted
~0.39 s/test solo, solo crossing 600 s at ~1540 tests, "about 60 rounds out",
and concluded "contention is what made it red NOW, growth is what makes it
permanent. Both, and the fix must address the second."

Measured: **0.275 s/test** (313.85 s / 1140). Solo crosses 600 s at ~2179
tests, i.e. **~156 rounds out** at the confirmed 6.66 tests/round. Growth is
*not* a live cause on any horizon that matters; contention is the whole story.
The sub-claim of 6.66 tests/round (946 -> 1139 over 29 rounds) is a HIT, but it
is load-bearing for nothing. The fix landed anyway — but had I been right, §4b
would have been justified by growth, and it is justified by cost instead.

**P1 — SPLIT.** Direction HIT and it is the round's headline: solo the leg is
**< 600 s** and the node is green, so the red is contention-amplified. Band
MISS: predicted 420-560 s, measured **319.25 s**. Same over-prediction as P2.

**P7 — SPLIT, and the wrong half was the useful one.** The conclusion holds:
the nested run's unique contribution is the PASS path, which a narrowed leg
still exercises end-to-end. The premise was **false** — the two tests I named
drive the summary fragment, not the script, and the script's pytest-leg FAIL
path had no coverage at all (§5). The bank said "if the narrowed run skips a
LINE of the script, that is a miss — report it". It skips none; but the audit
that clause forced found an uncovered branch instead.

**P3 — HIT**, all four clauses: every PASS < 1150 s, every FAIL > 1100 s, 486
and 485 the adjacent straddling pair, and zero rounds where a PASS total
exceeds any FAIL total.

**P4 — HIT.** `timeout=600` is a bare literal, one commit (`1bd242e`, round
388), unchanged for 108 rounds, and nothing in the tree asserted anything about
it.

**P5 — HIT**, every number: **exactly 7** selected of 1140 (1133 deselected),
**1 skipped**, **6 passed**, whole script green in **5.684 s** — predicted
"under 90 s".

**P9 — OPEN, kept.** Promised to open rounds 483's and 485's logs and report
whether they are the same defect, and to say so plainly if they were not. Both
are the identical `TimeoutExpired`; see §1.

**P6 — PRE-REGISTERED, unscorable this round.** See §7.

**P10 — HIT (see §10).** Suite green, and the only collection change is this
round's three deliberate additions.

## 10. Verification

```
$ .venv/bin/python3 -m pytest -q nuc/tests/test_constant_audit.py \
                                nuc/tests/test_run_checks_interpreter.py
38 passed in 21.47s

$ NUC_FAST_CHECK_NESTED=1 bash nuc/run_checks_fast.sh -k "fast_check and not strict_instrument"
6 passed, 1 skipped, 1133 deselected in 1.43s
constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk
nuc-instruments coverage=0 precision-audit=0 lastseen-drift=1 (diagnostic only)
nuc-checks PASS (pytest rc=0, audit rc=0)
real 0m5.684s
```

```
$ NUC_FAST_CHECK_NESTED=1 bash nuc/run_checks_fast.sh -k "r496_no_test_has_this_name"
nuc-checks FAIL (pytest rc=5, audit rc=0)      # the leg FAIL path, first covered this round
```

## 11. The whole check, end to end, after the fix

Run on a **quiet box** (the round-495 whence competitor had exited; `loadavg`
~1.3), exactly as `run_driver.sh` invokes it — no arguments, no env:

```
$ bash nuc/run_checks_fast.sh
nuc-checks interpreter: .venv/bin/python3 (tokenizers present)
1147 passed in 228.60s (0:03:48)
constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk
nuc-instruments coverage=0 precision-audit=0 lastseen-drift=1 (diagnostic only)
nuc-checks PASS (pytest rc=0, audit rc=0)
real 3m52.813s        # 232.8 s
exit 0
```

**1147 passed, 0 failed** — 1140 before, plus this round's seven deliberate
additions (three tests and four `TestDerivedBudget` methods). **P10 — HIT.**

The saving, like for like on the same quiet box: the check is one suite pass
(228.60 s) plus a 5.7 s nested leg and ~4 s of audit and instruments, where it
was previously two suite passes. The three strict instruments are unchanged at
`0 / 0 / 1` — `lastseen-drift` has exited 1 since round 448 and still does;
this round did not touch it and it is diagnostic-only by design.

Cross-track, both green and both checked *because* this round edited files
their checks read:

```
$ .venv/bin/python3 -m pytest -q harness/tests/test_viapin.py
21 passed in 81.73s          # after `harness/viapin.py fix --write`

$ .venv/bin/python3 -m pytest -q harness/tests/test_wiring_audit.py
68 passed in 271.41s
```

## 12. Skill

`skills/measured-budget-sizing/` (round 487's) **upgraded, not replaced** —
this is a second instance of its class, so a new skill would have split the
evidence. Added: a trigger condition for the self-referential case (*the
budgeted work CONTAINS the code that sets the budget*); a new step 5, **ask
whether the work is DUPLICATED before you size it**, because raising a ceiling
is the wrong repair for work that should not run; a pitfall recording that a
budget crossed and re-crossed reads as N episodes and is one threshold, with
the sort-by-the-bounded-quantity diagnostic that showed it; and a third worked
instance in Verification with two runnable commands. Steps renumbered 1-8.
