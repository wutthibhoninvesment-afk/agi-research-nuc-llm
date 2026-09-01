# Round 431 (SWE-loop D) — the checker that was clean and the engine that was dead

**Track:** SWE-loop(D). **Subject:** `mutation.baseline_check`, the gate every
mutation campaign in this program passes through, and `swe/copyparity.py
escapes`, the static checker round 425 built so that the defect class which
has killed that gate three times would be caught at authoring time.

**One sentence.** Round 427 handed this round a small job — give the mutation
sandbox the acknowledged-skip mechanism `pristine_check` has — and doing it
required first running the differential, which reported that the mutation
engine has been **dead at the door** (`baseline_check` exit 1, 17 red tests,
no campaign able to start) underneath a static checker that has been printing
`copy_safe — 0 escaping expressions` the whole time, because that checker
tested the **final** level of a path expression and every actual recurrence
of the class ends at a **positive** one.

---

## 0. What round 427 asked for, and why it turned into something else

Round 427 item 1, verbatim: *"`mutation.baseline_check` needs the same
mechanism pointed at its own tree; the registry format and the four buckets
are there to copy."* Round 425 had found the instance:

```
REGRESSED  tests.test_v37::test_the_host_is_byte_unchanged_by_this_decision
           passed -> skipped     "not a git checkout, or 768954b is not present"
in_place  rc=0        copied  rc=0
```

`_copy_project` excludes `.git`; the test shells out to `git show` and round
404 gave it a `pytest.skip` guard, so in the sandbox a real assertion becomes
a no-op with both sides exiting 0.

Rule: run the differential before building on top of somebody's description
of it. The differential is 327 s. It did not say what the record said.

---

## 1. The measurement (predictions banked first, `state/round-431-predictions.md`)

`live` = `languages/whence` in place, `sandbox` = a `_copy_project` copy,
same command through `proc.run_capped` so the copy gets the same environment
(`AGI_RESEARCH_ROOT` included), junit written **outside both trees**:

```
cmd: python3 -m pytest -p no:cacheprovider -q -m "not whence_slow" tests
live     rc=0  191.5s   2157 nodes   3 skipped
sandbox  rc=1  135.5s   2157 nodes   4 skipped     <-- rc ONE
vanished 0   appeared 0   xfail 0/0
changed  18:  1 passed->skipped        (round 425's instance, still there)
              17 passed->failed        (NEW)
```

All 17 are `tests/test_polarity.py`, all `FileNotFoundError`:

```
/tmp/r431-s83g0vzx/proj/../../state/whence/round-422/host-pins-plus.json
/tmp/r431-s83g0vzx/proj/../../state/whence/round-416/eval-pins.json
```

`languages/whence/tests/test_polarity.py:327`:

```python
REG_422 = os.path.join(HERE, "..", "..", "state", "whence", "round-422")
REG_416 = os.path.join(HERE, "..", "..", "state", "whence", "round-416")
```

Round 413's defect class, for the **fourth** time (149, 413, 419, this).
`_copy_project` copies `languages/whence` alone, so in the sandbox `../..`
is the tempdir. **`mutation.baseline_check` exits 1 and no mutation campaign
against this tree could start.** Nobody noticed, for the same reason nobody
noticed in round 419: nobody ran one.

Banked: `state/swe/round-431/live-vs-sandbox-diff.json`,
`live-vs-sandbox-runs.json`.

---

## 2. The finding: the checker for this class was running, and was asked the wrong question

Round 425's response to the third recurrence was the right one — it built a
STATIC check (`copyparity escapes`) so the class fires at authoring time
rather than after a campaign refuses — and wired it into the fast tier
(`test_swe_copyparity_real_subject.py`, 10 tests, 8.6 s, promoted). It ran
every round. On this tree, on 2026-09-01, before anything was changed:

```
copyparity(escapes): copy_safe — 84 file(s) scanned, 0 escaping
expression(s) (0 import-time, 0 runtime), 7 env-guarded
  no expression resolves above the subtree root
```

Banked verbatim: `state/swe/round-431/escapes-old-rule-copy-safe.json`.

It was not lying. Its rule was **final level < 0**:

```python
if name == "join":
    base = self.level_of(node.args[0])
    for extra in node.args[1:]:
        base += self._arg_delta(extra)
    return base
...
if lvl is not None and lvl < 0:
    self._record(node, lvl)
```

and the shape of the defect is

```python
os.path.join(HERE, "..", "..", "state", "whence", "round-422")
#              0    -1    -2     -1       0        +1        <- ends at +1
```

Net **+1**. Not negative. Not a finding. Twenty-seven expressions of that
shape in one file, seventeen red tests, a dead engine.

**The rule is the running minimum, not the endpoint.** `os.path.join` does
not normalise; the `..` is resolved lexically by the OS at open time,
against the copy's parent. A path that steps above the subtree root has left
the tree whatever it does afterwards. And the final level is not merely
insufficient — after the boundary it is **meaningless**: "+1" claims *one
level under the whence root*, and `<repo>/state/whence/round-422` is not
under the whence root at all.

Two facts that make this a class and not a slip:

* **Round 425's own two findings both ended negative** (`REPO =
  dirname(dirname(ROOT))`, `sys.path.insert(0, dirname(dirname(ROOT)))`).
  That is exactly why the endpoint rule looked adequate: its validating
  sample shared the property that makes the weak rule work.
* **Round 419's defect — the one the checker was built for — did not.** It
  was `join(ROOT, "..", "..", "state", "whence", "round-414",
  "check-pins.json")`. The static checker built in round 425 to prevent
  round 419's defect **could not have caught round 419's defect.**

### The fix

`_component_delta` returns `(net, floor)`; `_Escapes.evaluate` returns
`(level, floor)` and threads the floor through `dirname`, `parent`,
`parents[n]`, `join`, `/`, and — importantly — through variable BINDINGS, so
`REG` bound to an outside path does not come back inside on its next use.
`generic_visit` records on `floor < 0`. `level` is still reported, because it
is what tells a reader where the expression landed; the printed line is now
`floor -2 (ends at level 1)`.

The guard that keeps the checker installable survives unchanged and for a
better reason than before: an unknown component counts +1, and +1 can only
RAISE a running minimum, so "guess away from findings" holds for the floor
too.

The rule is **exact, not merely stricter**:
`join(HERE, "tests", "..", "examples")` floors at 0, resolves inside the
copy, and is not a finding. Pinned by
`test_a_dip_that_stays_inside_the_tree_is_not_a_finding`.

### What the new rule found, classified in full

```
copyparity(escapes): copy_breaks — 84 file(s) scanned, 29 escaping
expression(s) (2 import-time, 27 runtime), 7 env-guarded
  tests/test_polarity.py   27   floor -2
  tests/test_v22.py         2   floor -2
```

`state/swe/round-431/escapes-floor-rule-before-fix.json`. Going from 0 to 29
is the expected outcome of a rule change, not a bug in it; all 29 are true
positives, the 7 env-guarded exemptions are unchanged and still exempt, and
after the fix the scan is back to
`copy_safe — 0 escaping expressions, 7 env-guarded`
(`escapes-floor-rule-after-fix.json`).

---

## 3. `tests/test_v22.py` — a fifth class, which nothing dynamic can see

The two `test_v22.py` findings did **not** appear in the 17 red tests. Line
609:

```python
state_path = os.path.normpath(
    os.path.join(ROOT, "..", "..", "state", "research-state.md"))
if not os.path.exists(state_path):          # a whence-only checkout
    return
```

In the sandbox that path does not exist, so the function **returns**, and
junit records the node as **PASSED**.

| how the evidence disappears | exit code | per-node verdict diff | signed skip list | static scan |
|---|---|---|---|---|
| `passed -> failed` | **yes** | yes | no | yes |
| `passed -> skipped` | no | **yes** | **yes** | no |
| `passed -> vacuous PASS` (`return`) | no | **no** | **no** | **yes** |
| silently fewer collected nodes | no | yes | node floor | no |

A bare `return` is strictly worse than `pytest.skip`: the verdict does not
move, so `copyparity run` cannot see it; there is no skip, so a skip registry
cannot see it; the exit code is 0. **Only the static scan can see it, because
only the static scan does not need the defect to fire.** It has been silently
not-asserting inside every mutation sandbox since it was written.

Fixed both halves: `_C.AGI_ROOT` for the path, and `pytest.skip` instead of
`return` so that if the guard ever fires again it leaves a mark.

---

## 4. Round 425's sentence has its sign backwards, and its magnitude is zero

Round 425, about the evaporating test, quoted since:

> Every mutant this test would have killed now survives silently, and the
> mutation score is **inflated** by exactly the amount nobody can see. That
> is the same *shape* as round 349's `pyproject.toml` inversion.

Both halves are wrong.

**Direction.** `MutationReport.score` is `killed / total`
(`harness/swe/mutation.py:326`) and `valid_score` is
`killed / (killed + survived)`. A test that stops running moves the mutants
it would have killed from `killed` to `survived`. Both numbers go **DOWN**.
It is not round 349's flattering inversion; it is the unflattering one, and
the harm is a different harm: **phantom test gaps**, each of which is then
paid for a second time by `killers.py` and `repair.py` hunting for a killer
that already exists in the tree.

**Magnitude.** "Every mutant this test would have killed" was never counted.
Two measurements:

* `swe.coverage.collect` over `languages/whence/whence/*.py`, running that
  node ALONE: **0 covered lines in `whence/interp.py`** — the file every
  campaign in this program has actually mutated (`campaign.Campaign`'s
  default `files`) — and 315 elsewhere, all of them module-import lines
  executed by importing the test module rather than by the test body, which
  asserts only on `git show` stdout.
* The counterfactual directly. The test cannot be asked "would you have
  killed this mutant?" in a sandbox, because there it skips; so: `git
  worktree add --detach`, where it does run (unmutated baseline rc 0),
  then 60 mutants of the two most-covered files written into that worktree
  one at a time. **Killed 0 of 60.**
  `state/swe/round-431/evaporating-test-kills-nothing.json`.

So: the class is real, this instance's cost is **zero**, and the honest
statement is *the gate cannot see the class*, not *the score was wrong*.
That distinction is what the registry's `kills_mutants` field exists to
record — see §5.

---

## 5. The capability: grading the sandbox's own report, at zero extra suite runs

`harness/swe/sandboxevidence.py` (new, 265 lines).

`pristine_check` answers the same question for the GIT tree by running the
suite twice and differencing. That is the right shape when you have two trees
and no history. It is the wrong shape here, because **the baseline is a run
this repo already pays for**: add `--junitxml` to it and compare the skip
list against a signed registry, and the second tree is only needed to
ESTABLISH the registry, not to re-check it every campaign.

```python
b = baseline_check(WHENCE_ROOT, CMD, suite="whence-fast-sandbox")
# returncode 0  seconds 247.68   junit_ok True   n_nodes 2157
# evidence_verdict ok
#   sandbox evidence: OK -- 2157 node(s), 4 skipped, floor 2157
#     skipped, acknowledged (round 431, both): tests/test_parse_error_differential.py::test_acceptance_agrees[deep-nesting]
#     skipped, acknowledged (round 431, both): ...[effect-not-permitted]
#     skipped, acknowledged (round 431, both): ...[effect-arg-not-permitted]
#     skipped, acknowledged (round 431, sandbox_only): tests/test_v37.py::test_the_host_is_byte_unchanged_by_this_decision
```

That is the real subject, after the fix, banked at
`state/swe/round-431/baseline-check-after-fix.{log,json}` — **the engine is
alive again**: `2153 passed, 4 skipped, 91 deselected`, exit 0.

Design decisions, each with the reason it is not the obvious one:

* **Deliberately ONE-SIDED, and it says so.** A single run cannot tell "the
  copy caused this skip" from "this is skipped everywhere". It does not
  pretend to: it signs BOTH, and the question it asks — *is every test the
  sandbox did not run signed off by a round that looked at it* — is
  STRONGER than "nothing changed", because it also covers the three skips
  that were already there. `class: sandbox_only | both` carries what the
  two-run differential established.
* **The reason is pinned, not just the node.** A node signed forever is a
  mute button. A changed message is `pin_expired` and goes red.
* **Acknowledged rows print every run.** An acknowledgement that suppresses
  invisibly reads as coverage.
* **`kills_mutants` is a field, and `true` prints LOUDLY forever**
  (`acknowledged_costly`). This is the field `pristine_check`'s registry has
  no analogue of, and it exists because of §4: a signed skip that covers none
  of the mutated files is bookkeeping, and one that covers them is a standing
  debt against every score the engine publishes. `false` requires evidence;
  the round-431 entry carries the coverage figure and the 0/60.
* **`node_floor` — the third hole.** A suite that silently collects fewer
  nodes exits 0, reports no failure and no skip. Nothing in this repo could
  see that before. A floor only fires when the count DROPS, so adding tests
  makes it stale-low and never false-positive. `V_NODE_LOSS` outranks
  `V_SKIP_EVAPORATION`: a run that lost tests it cannot name has an
  untrustworthy skip list too.
* **Rule 3.** No junit ⇒ `evidence: unavailable` ⇒ no verdict in either
  direction. A non-pytest `test_cmd` gets no flag and no verdict rather than
  a broken command.
* **Report by default, refuse on request.** `mutation_test(require_evidence=
  True)` / `Campaign(require_baseline_evidence=True)` raise
  `BaselineEvidenceLost`; the default is OFF. A gate whose false-positive
  cost is "no campaign runs at all" needs the registry populated in front of
  it, and this engine has now been stopped at the door **four** times.
  `BaselineNotGreen` still takes precedence: it means the suite spoke and
  said no, which is the stronger statement.

**One junit parser instead of three.** `copyparity.parse_junit` read the XML
itself and counted `<skipped type="pytest.xfail">` as `skipped`;
`pristine_check.parse_junit`, written for the same job one tree over, excludes
it. Two readers of the same file that disagree about the same node is a
phantom regression waiting for the first tree with an xfail in it. Measured
this round: **0 xfail nodes on either side**, which is the only reason it
never fired. `copyparity.parse_junit` is now a four-line adapter;
`pristine_check.parse_junit` grew `details` (the message that decided each
status) so nothing was lost.

**The severity split.** `copyparity`'s `regressions` bucket merged
`passed -> failed` (which the exit code already catches) with
`passed -> skipped` (which it cannot). At HEAD that bucket held 18 rows, 17
of them gate-visible; the one that no other check in this repo could see was
row 18. `evaporated` / `broken` are now separate views over the same list
(`regressions` unchanged for existing readers), and `summary()` prints
EVAPORATED first with the line *(both sides exit 0; no exit-code gate sees
this)*.

---

## 6. Prediction bank, scored (D-013)

`state/round-431-predictions.md`, written after reading the modules and
round 425's banked JSON, before any suite ran this round.

| # | verdict | note |
|---|---|---|
| A1 | **MISS** | "exactly one regression". There were **18**: 1 evaporation + 17 `passed -> failed` nobody had seen. The evaporation half was right; the prediction named a total, so it is a miss. |
| A2 | HIT | vanished / appeared / improvements all empty. |
| A3 | HIT | 2157 nodes, equal both sides, inside the 2086–2400 range. |
| A4 | HIT | live 3 skips, sandbox 4. |
| A5 | HIT | 3 skipped in both. |
| A6 | **MISS** | "both sides exit 0". Sandbox **rc=1**. This miss is the round. |
| B1 | HIT | sign is backwards; `score = killed/total` and `valid_score` both fall. No reading inflates. |
| B2 | HIT | the round-349 analogy fails — 349 is the flattering direction. |
| B3 | **PARTIAL** | predicted ZERO covered lines of `languages/whence/whence/`; measured **315**, all module-import lines. The operative claim held exactly: **0** in `whence/interp.py`, and 0/60 mutants killed. Coverage measures execution, not detection, and I wrote the stronger claim when the narrower one was the one that mattered. |
| B4 | **PARTIAL** | "the headline is the gate cannot see the class". The gate DID see this one (rc=1); the blind instrument was the STATIC checker, and the headline was bigger than predicted. |
| C1 | HIT | 4 keys, none names a test. |
| C2 | HIT | campaign adds `green`, `test_cmd`, `allow_red`, `checked`; still names no test. |
| C3 | HIT | the tail carries the count line and has never been compared to anything. |
| D1 | HIT (bounded) | zero extra suite runs, yes. Flag cost: 191.5 s with `--junitxml` vs **200.3 s** without, on the same tree minutes apart. The delta is negative, so the flag's cost is below this box's run-to-run variance (~9 s) rather than resolved at "< 3 s". Reported as a bound, not a figure. |
| D2 | **MISS** | predicted at least one whence test enumerates the tree such that a stray report would change its outcome. Checked: every enumerator in `languages/whence/tests/` filters by extension (`*.py`, `*.lang`), so a `baseline.xml` at the root changes nothing. The write-outside rule is kept — it is right for `pristine_check`'s reason (a report inside a tree is dirt handed to `git worktree remove`) and is defensive here — but it prevented nothing on this subject and I will not claim it did. |
| D3 | HIT | and the 17-vs-1 split at HEAD is the demonstration. |
| D4 | HIT | new file. |
| D5 | HIT | copyparity did count xfail as a skip; 0 xfail nodes on either side, so the phantom had never fired. |
| E1 | HIT | 191.5 + 135.5 = **327.0 s**, inside 270–330. |
| E2 | see §7 | |
| E3 | **MISS** | predicted no file under `languages/whence/` would be edited. Two were — `tests/test_polarity.py` and `tests/test_v22.py` — because the measurement found a dead engine and leaving it dead to protect a prediction is not a trade this program makes. No file under `languages/whence/whence/` was touched; Whence stays at its current spec level. |
| E4 | HIT | nothing was created under `state/` or `languages/whence/` while the differential ran. |

**16 HIT (one bounded), 4 MISS, 2 PARTIAL of 22.** The two that matter are
A6 and E3, and they are the same event.

---

## 7. Results

```
harness fast tier      209 passed in 58.24s   (round 432; the five files below,
                       tier-budget 31.6s of a 56.6s budget)
test_swe_sandbox_evidence.py    30 passed in 6.02s   (new file)
test_swe_copyparity.py          23 passed            (was 18: +5)
test_swe_copyparity_real_subject.py  12 passed in 8.6s  (was 10: +2)
test_pristine_check.py         128 passed in 2.73s   (was 127: +1)
test_swe_campaign.py + test_swe_mutation.py   NOT COMPLETED -- see below
skill_lint --house --strict skills/   73 skill(s), 0 error(s), 0 warning(s)
```

`CAMPAIGN_RESULT` was filled by ROUND 432, which inherited this round's
uncommitted diff, and it is filled with what was measured rather than with a
pass. This round died at `max_turns` waiting for that run; its pytest was
still alive 38 minutes later, orphaned, and its stdout was a deleted tmpfile
that had flushed **0 bytes**, so nothing was recoverable from it.

Round 432 re-ran the two files and measured why they are slow:

* **This box has `nproc` = 1.** Every suite serialises, so a health-check and
  a round's own suite contend for one core. That is the whole explanation for
  the 38-minute orphan.
* `test_cli_runs_offline_stages_and_stops` runs a **real, full, unfiltered**
  whence suite as its baseline pre-flight and then a **tracer-instrumented**
  full suite for the coverage stage. The baseline child alone ran 19+ minutes.
* Checked against a pristine `git worktree` at HEAD: the same test spawns the
  same unfiltered `pytest -q -x ... tests` child **without** `--junitxml`.
  **The cost is pre-existing and is NOT this round's flag** -- this diff only
  appends a flag to a command that was already the expensive thing. §8's
  "a campaign running `DEFAULT_TEST_CMD` (unfiltered) is a DIFFERENT suite"
  predicted exactly this.

**8 of 36 tests passed before round 432 stopped the run** to free the single
core for the rest of its own work. The file is a multi-hour proposition on
this box. It is left unfilled rather than green on purpose.

```

languages/whence  tests/test_polarity.py + tests/test_v22.py  171 passed in 53.08s
copyparity escapes, before: copy_safe    0 findings   (endpoint rule)
copyparity escapes, with floor rule:     29 findings  (2 files)
copyparity escapes, after the fix:       0 findings, 7 env-guarded
baseline_check on the real tree:  rc 0, 2157 nodes, evidence_verdict ok
```

No SPEC bump: nothing under `languages/whence/whence/` was touched.

## 8. What this does NOT establish

* **The `whence_slow` tier was never run in the sandbox.** Every number here
  is `-m "not whence_slow"`, 2157 of 2248 nodes. The registry's suite entry
  names that command, and a campaign running `DEFAULT_TEST_CMD` (unfiltered)
  is a DIFFERENT suite with a different skip set and no entry.
* **`node_floor` is a floor for one suite on one day.** It cannot see a test
  that was deleted and another added in the same round.
* **The static scan is still a hypothesis generator.** It cannot know a path
  it reconstructs is ever opened, cannot follow a level through a function
  call or a format string, and an unknown component still counts +1. The
  floor rule made it sound about a shape it was unsound about; it did not
  make it complete.
* **`escapes` scans `languages/whence` only.** Nothing has ever pointed it at
  `harness/` or `nuc/`, and `_copy_project`'s callers have grown (round 413:
  `guardpin.py` passes the REPO ROOT).
* **Nothing runs `copyparity run`.** The 327-s mode is still unwired, and it
  is the only one that sees a runtime escape that the static scan's
  arithmetic cannot follow. The affordable checks now cover more of the
  table than they did, which is not the same as covering it.
