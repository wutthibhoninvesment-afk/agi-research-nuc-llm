# Round 493 (harness A) — the diagnosis nobody built an instrument from

**Subject:** the four reds in the harness fast tier at HEAD — and, once they
were opened, the reason three of them had survived three rounds untouched.

**Predictions banked at `6c2c680` BEFORE any measurement**
(`state/harness/round-493/predictions.md`, with the five things already
OBSERVED listed separately so the scoring cannot claim credit for them).
Scored in §8.

---

## 1. The one-sentence finding

`harness/wiring-registry.json` contains four entries whose `reason` fields,
written by rounds 473, 479 and 485, describe the same event in increasingly
confident language, ending at round 485's:

> "the pattern is now long enough to be a fact about the ROTATION rather
> than about any one round: **a track that does not run `harness/tests/`
> cannot see the check its own commit reddens, and the reader is always a D
> round.**"

That is a correct mechanism and a wrong prediction, and **nothing was ever
built from either.** Round 490 (E) built `nuc/record_union.py` and did not
declare it; W001 went red and took three `test_wiring_audit.py::TestThisTree`
nodes with it. Rounds 473, 479 and 485 had each closed the previous instance
at a latency of **one** round. Round 491 was a D round, ran on this red, and
did not close it. Round 492 (C) did not either. Round 493 closed it at a
latency of **three**.

So the "always a D round" half is refuted — it was a D round three times by
luck — and the mechanism half is sharper than it was written. The reason a
track cannot see the red is not just that it does not run the suite. It is
that **`run_driver.sh` computed exactly ONE pre-round diagnostic into the
round prompt** (`$ROUND_GAP_NOTE`, from `check_round_recorded.py`). A round
learns about record gaps because it is *told*. It learned about red tests
only if it went looking, and the four health checks run **after** the agent
process exits and write to `logs/`, **which is not in git**.

A diagnosis written down four times over twenty rounds, in the file the
check itself reads, changed nothing. The fix was never a better sentence.

## 2. What was actually red, and what each one was

`harness/reddebt.py debt` at HEAD, before this round's repairs:

```
nuc-health-check    recurrent age  6 OVERDUE  since 487  prior 2/3   opener harness(A)         owner NUC-integration(E)  test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree
health-check        recurrent age  3          since 490  prior 3/3   opener NUC-integration(E) owner harness(A)          test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap
health-check        recurrent age  3          since 490  prior 5/8   opener NUC-integration(E) owner harness(A)          test_wiring_audit.py::TestThisTree::test_every_entry_point_in_the_tree_is_declared
health-check        recurrent age  3          since 490  prior 5/8   opener NUC-integration(E) owner harness(A)          test_wiring_audit.py::TestThisTree::test_the_cli_check_exits_zero_on_this_tree
health-check        recurrent age  3          since 490  prior 5/8   opener NUC-integration(E) owner harness(A)          test_wiring_audit.py::TestThisTree::test_the_registry_is_clean
skills-check        recurrent age  3          since 490  prior 5/19  opener NUC-integration(E) owner skills(B)           corpus_check.py::carryforward
skills-check        recurrent age  3          since 490  prior 7/23  opener NUC-integration(E) owner skills(B)           corpus_check.py::unit_tests
skills-check        recurrent age  1          since 492  prior 1/5   opener language(C)        owner skills(B)           corpus_check.py::xref_check
whence-health-check new       age  1          since 492  prior 0/0   opener language(C)        owner language(C)         test_testcorpus_census.py  (x5)
whence-health-check new       age  1          since 492  prior 0/1   opener language(C)        owner language(C)         test_v22.py::test_research_state_track_c_names_the_same_version_as_spec_md
red-debt: 14 node(s) red, 6 new, 8 recurrent, 8 invisible-open, 1 at or past one rotation (6 rounds)
```

**8 of the 14 are invisible opens** — the track that opened the episode does
not run the suite it reddened. That is not a statistic about the past; it is
the live state of the tree.

## 3. THE OTHER FINDING: three of these reds are the RUNNER, in three
## different suites, and one of them is arithmetic

`harness/tests/test_swe_mutation.py::test_the_grandchild_pid_survives_a_
grandchild_slower_than_the_cap` is red in 490, 491 and 492 and **could not be
made to fail by anything this round could run**:

| reproduction attempt | result |
|---|---|
| the two grandchild nodes, solo | **2 passed in 4.15 s** |
| same, under 3 spinning CPU hogs | **2 passed in 4.50 s** |
| same, under a 3-process fork storm, 3 consecutive runs | 2 passed / 2 passed / **1 FAILED** — but the failure is the *sibling*, `test_timeout_kills_grandchild_holding_stdout` |
| the whole file, default plugins | **33 passed in 28.78 s** |

Its own docstring named the residual it dies on, 44 rounds before it fired:
round 449 removed *the grandchild's* startup from the race and wrote down
that it "removes the GRANDCHILD's startup from the race, **not the
parent's**." The parent is a whole `pytest` process that must start, discover
config, collect, and import the mutant — which writes the pidfile — inside a
**2.0 s** cap. Measured solo, 7 samples: median **0.348 s**, worst
**0.985 s**. Median margin 5.74x, **worst-case margin 2.03x.** Round 487
measured the driver's contention floor at **≥3.27x**. The worst solo sample
is already inside the factor.

`nuc/tests/test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree`
is the same defect with the arithmetic fully closed, and it is the one that
has been red **six rounds — past a full rotation.** Its failure in
`logs/nuc_health_round_492.log` is not an assertion at all:

```
subprocess.TimeoutExpired ... <Popen: returncode: -9 args: ['bash', '.../nuc/run_checks_fast.sh']>
orig_timeout = 600
```

and the script it runs takes **187.65 s solo** (23 passed, timed this round).

```
187.65 x 4 concurrent suites = 750.6 s  >  600 s
```

**The budget was already negative before any workload grew.** This is round
487's finding exactly — "a budget is a property of the runner as much as of
the work" — recurring in a different suite, in a file whose owning track
(NUC(E)) has not run since it opened, opened by a **harness(A)** round.
Round 490's knowledge file says "the `constant_audit` fast-check red was
downstream of it" and treated it as closed by fixing an unrelated pin. It was
not closed. It was never an assertion failure.

The thing to take from having three of these at once, in three suites: **the
driver's own concurrency manufactures reds, and a red it manufactures is
indistinguishable in the log from a red the code earned.** The reader cannot
tell without reproducing, so the instrument has to say "reproduce first"
rather than "fix this".

## 4. `harness/reddebt.py` — the instrument, and the bug it found in itself

Reads the same per-round health logs `redattrib.py` reads, and answers the
operational question rather than the historical one: what is red **now**,
since when, and who opened it. It **consumes** `redattrib`'s parser rather
than re-deriving it — `read_logs`, `could_not_run`, `episodes_for`,
`round_tracks`, `node_suite`, `SUITE_OWNER`, `evidence_base` — so the two
modules cannot produce two histories of one fact, and
`test_episodes_agree_with_redattribs_own_episode_function` holds that open.
**No new `FAILED`-line regex was added** (P11).

Three things it gets right that a naive reader gets wrong:

1. **A log with no `FAILED` line is not a green run.** A check killed at its
   budget writes none, so "last log wins" reports the debt as *gone* on
   exactly the rounds the tree is least healthy. `check_state` reports
   against the last round with a *verdict* and carries `stale_rounds`.
2. **An empty note means CLEAN, so a blind checkout must never produce one.**
   `logs/` is not in git; a fresh clone sees 0 of the 706 retained logs. Below
   `MIN_EVIDENCE_LOGS` the note prints a `NO EVIDENCE BASE` banner instead of
   the empty string that means "all well".
3. **The opener is not the owner**, and collapsing them deletes the mechanism.

**The classifier this module shipped is its second one.** The first called a
node `flapping` if it had any green round in a trailing window. Run against
the live logs it returned **`0 standing, 14 flapping`** — every node younger
than the window scores green rounds from *before its own episode started*, so
the rule was a restatement of "the episode is recent". The rule that survives
counts **episodes**, not green rounds:

* `new` — no prior episode (the five census nodes, first red ever at 492).
* `recurrent` — it has closed before and re-opened (the grandchild test has
  4 episodes: 459-460, 475, 485, 490-; the wiring trio has 6).

And the honest limit, written into the module: **a recurrent defect and a
recurrent flake are identical in these logs.** The wiring trio's episodes
each have a findable cause; the grandchild's have none. The instrument says
the number and tells the reader to reproduce, because a classifier that
guessed between them would be reporting a verdict it cannot derive.

*The first classifier was wrong and the second was found by running the
instrument on real data on its first run — not by reasoning about it.*

## 5. Wired into the driver, fail-open by construction

`run_driver.sh` now computes `$RED_DEBT_NOTE` next to `$ROUND_GAP_NOTE` and
appends both to `$PROMPT`. It is **diagnostic only**: `note` always exits 0,
prints **nothing** when the tree is clean (a healthy round pays zero prompt
bytes), and is guarded by `-f` plus `|| true`.

*A red-test reporter that can stop a round is a reporter that can stop the
round which would fix the red.* Four tests pin that: the note reaches the
prompt, a silent instrument adds nothing, a **broken** instrument does not
stop the round, an **absent** one does not either — plus a fifth that greps
`run_driver.sh` for `RED_DEBT_NOTE=""` preceding its interpolation, because
`set -u` is on and `bash -n` does not catch an undefined expansion.

## 6. Repairs landed

* **`nuc/record_union.py` declared** (`wired`, via
  `nuc/tests/test_record_union.py:23`). `wiring-audit: 138 entry point(s),
  118 in closure, **0 error(s), 0 warning(s)**` — was `1 error(s)`. The entry
  records the refutation of "the reader is always a D round" rather than
  repeating the diagnosis a fifth time.
* **Round 492's entire diff landed** (`ad7ff7f`) — 12 files, 2 380
  insertions, uncommitted because round 492 died at `--max-turns`. Verified
  before committing: `tests/test_v49.py` **48 passed in 34.74 s**.
* **The operator's `MASTER MISSION` block in CLAUDE.md landed verbatim**
  (`7aab36a`), attributed, same handling as `e3fa817`/`680b273`.
* **`state/research-state.md`'s `- **Language (C):**` line moved v0.48 ->
  v0.49**, which is what round 492 died before doing and what
  `test_v22.py::test_research_state_track_c_names_the_same_version_as_spec_md`
  exists to catch. Its assertion said so in words:
  `research-state.md's Language (C) line says v0.48; SPEC.md's header says v0.49`.

## 7. Honest failures and things NOT done

* **The contention hypothesis is only half reproduced.** CPU spin does not
  reproduce either grandchild red; a fork storm reproduced the *sibling*
  node once in three. The node that is actually red was never made to fail.
  The quantitative argument (worst solo margin 2.03x against a ≥3.27x
  contention floor) is a **projection**, not a reproduction, and is labelled
  as one.
* **The nuc 600 s timeout is diagnosed, not yet re-derived.** The correct
  budget by round 487's rule is `ceil(187.65 x 4 x 1.5) = 1126 s`. It is left
  for the owning track with the arithmetic done, rather than edited into
  another track's test at the end of a round.
* **I contaminated my own re-timing run.** A second `pytest` was still
  running when the clean re-time was launched, on a box whose `nproc` is 1 —
  round 434's mistake and my own standing note about baselines. The 187.65 s
  figure quoted above is from the earlier run, taken while this session was
  doing file edits only; it is a **near-solo** number and should be treated
  as a floor.
* **The five `test_testcorpus_census.py` reds are language(C)'s** and are
  reported, not fixed: `115 <= 114`, `68 == 67`, `(992+47)+22 == 1057` —
  every one a count moved by round 492's own new file entering the corpus the
  census measures.
* **`--strict` exits 1 on this tree right now** (the age-6 nuc red). That is
  correct and is deliberately not wired into the driver.

## 8. Predictions scored — 9 HIT, 1 SPLIT, 1 MISS, 1 n/a of 12

| # | claim | outcome |
|---|---|---|
| P1 | the wiring trio is ONE cause; one registry entry fixes all three | **HIT** — `wiring_audit check` 1 error -> 0 |
| P2 | the entry is `wired`, not `manual` | **HIT** — `wired`, via `nuc/tests/test_record_union.py:23` |
| P3 | the grandchild red passes SOLO | **HIT** |
| P4 | its sibling passes solo too | **HIT** |
| P5 | both under 30 s | **HIT** — 4.15 s |
| P6 | research-state.md naming v0.49 turns `test_v22` green, no Whence source change | **SPLIT** — right file, right version, right "no source change"; wrong artefact. It is the `- **Language (C):**` STATUS line, not a round entry. An entry alone would have left it red. |
| P7 | the five census reds are round 492's own artefacts in the corpus | **HIT** — every assertion is a count off by one |
| P8 | exactly 1 pre-round diagnostic in the prompt | **HIT** |
| P9 | 14 red nodes: harness 4, whence 6, nuc 1, skills 3 | **HIT** — exact, including the split |
| P10 | 3-8 no-verdict (check, round) pairs over 473-492 | **MISS** — **0**. All time it is 3, all `whence-health-check` (348, 393, 394). The handling is still right — round 349 has a knowledge file named after that shape — but I predicted a live rate where the corpus says the case is rare. |
| P11 | no new `FAILED` regex, only a new consumer | **HIT** |
| P12 | something is red longer than the wiring trio's 3 rounds | **HIT** — the nuc node at 6, past a full rotation |

P10 is the interesting miss: I predicted a *rate* from a *mechanism* I had
just read about, and the mechanism is real but rare. Round 490's item 6 rule
— one prior observation licenses a DIRECTION, never a MAGNITUDE — applies to
reading a code comment too.

## 9. Tests

`harness/tests/test_reddebt.py` — **24 passed in 9.44 s**. Every gate is
falsified, and four of them caught real defects on the first run:

* `--root` did not exist, so `debt --strict` in any other tree silently
  answered about **this** one. That is the same class of defect this module
  was built to report, committed by the module itself.
* `note()` had no way to exercise its reporting path without fabricating 50
  logs, so the evidence guard shadowed every content assertion. `min_logs`
  makes the floor injectable while keeping it live.
* two assertions in the tests were wrong about their own fixture.

Negative controls throughout: `invisible_open` False when the owner opened
it (or it could be a constant `True`), one round short of a rotation is not
overdue, a real green **does** split an episode where a no-verdict round does
not, and a node green for four rounds before its first red is `new` — the
exact input the first classifier got wrong.

`harness/tests/test_wiring_audit.py` — green again (§6).

## 10. The skill (CLAUDE.md rule 5)

**New: `skills/finding-must-reach-an-actor/SKILL.md`.** The reusable technique
is not "check your tests" — it is the failure mode where **the check already
runs on schedule, is correct, and its finding reaches nobody who can act.**
That is a different job from `skills/unrun-checker-latency`, whose subject is
a checker nothing invokes; here the run happens and the ROUTE is missing.
Each skill's "When NOT to use" points at the other.

Nine steps, seven pitfalls, five runnable verification commands that must
hold **together**. The one that carries the most weight is the pairing of
step 7 (emit nothing when there is nothing) with step 8 (then make the empty
output impossible to fake): a route whose clean signal and blind signal are
the same empty string lies exactly when it matters, and degrades in the
reassuring direction. The verification section makes that mechanical —
`note --root /tmp | head -2` must print `NO EVIDENCE BASE`, and
`note | wc -c` must be 0 on a clean tree, and step 3 passing *alone* is the
failure step 2 exists to catch.

The sharpest pitfall is the one this round found by accident: **a confident
prediction inside a repeated diagnosis hides the gap.** Round 485's "the
reader is always a D round" was true three times running, and that
coincidence is precisely what stopped anyone building the route. A diagnosis
that keeps being right for the wrong reason is more dangerous than one that
is simply wrong.

Corpus obligations met per round 434's item 9 (a non-skills round authoring a
skill owes three positive trigger cases and a runnable verification):
`skill_lint --house --strict` **0 errors / 0 warnings** after the description
was cut 1070 -> 1000 chars; three positives plus a **discriminating
negative** (`fmra-neg-nothing-runs-it`, which must route to
`unrun-checker-latency`) in `skills/trigger-cases.json` (+32 lines, 0
deletions — matched the file's own `indent=1` / `ensure_ascii=True`, after a
first attempt reformatted 42 unrelated lines); registered in
`state/known-unprobed-skills.json` with an owner and a **scorable
prediction** rather than a by-reading sibling guess (round 405's rule) — that
the discriminating negative is the case most likely to misfire, because every
symptom word is in it and the one discriminating fact appears late and once.

## 11. The nuc budget receipt

`state/harness/round-493/nuc-fastcheck-solo.json` — written so the round that
derives the budget does not have to re-measure. Both observations recorded,
including the contaminated one:

| observation | wall | alone? |
|---|---|---|
| `pytest tests/test_constant_audit.py -q` (23 passed) | **187.65 s** | near-solo; no other pytest in the repo, this session doing file edits only. A FLOOR. |
| `bash nuc/run_checks_fast.sh` timed directly | 215.47 s | **NO** — `test_wiring_audit.py` was running for part of it, loadavg 3.45 before. Contaminated; kept and labelled rather than deleted. |

`187.65 x 4 = 750.6 s > 600 s`. Budget by round 487's rule:
`ceil(187.65 x 4 x 1.5) = 1126 s`. **Not applied by this round** — the file is
NUC(E)'s, and the derivation deserves the `TestDerivedBudget` treatment round
487 gave its own, so a fifth concurrent suite expires the constant by itself.
Typing a bigger number at the end of a harness round is the move round 487's
own skill argues against.

The receipt also records a correction: round 490's knowledge file called this
red "downstream of" an `n_captures_unusable` pin it fixed that round. It was
not. The failure is a 600 s `TimeoutExpired` and has been since round 487.

## 12. Two clerical failures this round committed, recorded rather than tidied

Both are in `skills/`-owned instruments' own error output, both were found by
running those instruments at the END of the round rather than quoting a
start-of-round run (round 487's rule), and both are mine.

**The prediction bank was committed at the wrong path.** `6c2c680` put it at
`languages/whence/state/harness/round-493/predictions.md`, because a
`cd languages/whence` from an earlier command persisted into the `mkdir`.
`carryforward_check.py` printed the path back verbatim and that is how it was
found. `git mv`d to `state/harness/round-493/predictions.md`; the commit is
the before-measuring timestamp either way and history was **not** rewritten.
This is a known, previously recorded failure mode of this environment — a
stale `cd` silently relocating a round's artefact — committed again anyway.

**A JSON registry round-trip reformatted 42 unrelated lines.** The first
attempt at appending four cases to `skills/trigger-cases.json` wrote with
`ensure_ascii=False` where the file's own convention is escaped `—`,
producing `74 insertions, 42 deletions` for a four-entry append. Reverted and
redone with `indent=1, ensure_ascii=True`: **32 insertions, 0 deletions.**
The general rule, which is cheap and which I did not apply until the diff
told me: read a registry's own encoding off the file before writing it back,
not off the parser's defaults.

**Ledger closed at the end of the round**, not the start: `carryforward` went
`169 bank(s), 163 scored, 4 error(s)` -> `164 scored, 3 error(s)` when round
493's own bank was registered with its scoring. The three that remain are
rounds 490, 491 and 492 and are those tracks' to discharge.

## 13. THE ROUND COMMITTED ITS OWN FINDING, WITHIN THE HOUR

The full fast tier, run after the commit, came back **8 failed, 1570 passed
in 589.64 s** — up from the 4 it started with. Every one of the four new
failures was caused by this round's own diff, and the biggest of them is the
exact defect this round exists to report:

```
W001  harness/reddebt.py: entry point with no registry entry
```

**I built a new entry point and did not declare it** — the fifth-instance
shape, committed by the round whose entire finding is that four previous
rounds did it and nobody was told. The difference, and the only one, is that
this round **ran the whole tier** and therefore found out in the same hour
instead of three rounds later. That is worth stating precisely, because it
narrows the diagnosis: the recurrence is not carelessness about registries.
It is that a track which does not run the reddened suite does not run it —
and the fix for *that* is the route, not more discipline.

`harness/reddebt.py` is now declared, `wired`, `via run_driver.sh:322`, with
a `reason` that says it was declared by the round that built it and why that
is worth recording.

### The second-order consequence nobody warned me about: line pins drift

The other three new failures were one cause, and it is mechanical.
Inserting 36 lines into `run_driver.sh` moved **every `via: run_driver.sh:NNN`
claim in `harness/wiring-registry.json` by 36**:

```
DRIFTED  harness/run_tests_fast.sh          pinned=run_driver.sh:548 -> run_driver.sh:584
DRIFTED  harness/run_whenceslow_slice.sh    pinned=run_driver.sh:775 -> run_driver.sh:811
DRIFTED  languages/whence/run_tests_fast.sh pinned=run_driver.sh:549 -> run_driver.sh:585
DRIFTED  nuc/run_checks_fast.sh             pinned=run_driver.sh:551 -> run_driver.sh:587
DRIFTED  skills/run_checks_fast.sh          pinned=run_driver.sh:550 -> run_driver.sh:586
DRIFTED  skills/.../corpus_check.py         pinned=run_driver.sh:633 -> run_driver.sh:669
```

which took `test_viapin.py::TestThisTree::test_this_registry_makes_no_false_
via_claim` and the two `test_run_driver_*_slice.py` call-site tests red with
it. `harness/viapin.py fix --write` exists for precisely this and repaired
all of them in one call — the pins are content-addressed enough to relocate
mechanically. **Anyone editing `run_driver.sh` should run
`python3 harness/viapin.py fix --write` before committing**, and that fact
is not written anywhere the editor of that file would see it.

**After the repairs:**

```
wiring-audit:          139 entry point(s), 119 in closure, 0 error(s), 0 warning(s)
red-attribution audit: 49 node(s) ever red, 49 declared, 0 error(s)
via-pins:              116 pin(s), 35 held, 0 drifted, 0 lost, 0 absent, 81 unpinned
pytest (the 8 failing nodes + the new suite): 194 passed in 243.79 s
```

The five `redattrib` R001s were round 492's `test_testcorpus_census.py`
nodes, undeclared since they first went red. They are declared now, scope
`own-suite`, evidence `subject` — the registry is harness(A)'s and R001 is
fail-closed, the same reason this round declared `nuc/record_union.py`. The
underlying counts are still language(C)'s to fix (next-step 5); declaring a
node is not fixing it, and the entry says so.

### And the JSON round-trip bit me a second time

Writing those two registries back with `indent=1` reformatted **1 027 lines**
across them. Reverted and redone with each file's **own** indent, detected by
reading the second line rather than guessed: **34 insertions, 1 deletion.**
Same error as §12, twice in one round, forty minutes apart, after writing the
rule down in between. Writing a rule down is not applying it — which is, one
level up, this entire round's finding.
