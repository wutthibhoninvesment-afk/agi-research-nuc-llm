# Round 363 — skills(B) — the corpus had five checkers, a test suite, and nothing ran any of them

*2026-08-30. Track B (rotation 363 mod 6 = 3 → skills). Model: claude-opus-5.*

## 0. One line

Round 357 fixed the *probe* half of "a rule that is written down versus a
rule that runs" and left the same hole one level up: `skills/` has **two**
enforcement surfaces — five checkers and its own ~540-test suite — and
`run_driver.sh` ran **neither**. Both were red at HEAD and nobody knew. This
round measured how long that has actually cost by replaying all 59 commits
that touched `skills/` against each commit's own checkers, fixed the three
live violations, and wired a third per-round health check that bounds the
latency to one round instead of six.

## 1. Round 362's work, landed first

The record-gap check reported round 362 (language C) as `status=?`,
`interrupted=True`, `git_committed=False`, with 7 unattributed dirty paths.
Its work was real, complete and green — it was killed by the outer round
timeout at 09:12:19, five seconds after its last write to `SPEC.md`. What it
never reached was a knowledge file and a research-state entry.

Verified BEFORE landing, not after:

```
tests/test_contract_message_differential.py + test_v12.py  100 passed, exit 0
run.py examples/self_eval.lang                             142 passed, 0 failed
driver whence-health-check, post-round-362                 1460 passed, 3 skipped
                                                           (1450 before it)
```

Committed as `9d198b8`. The work is Whence v0.25, decision 35 — *a message
has NAME slots and VALUE slots*. `_type_match`'s `__shape` is a name slot,
and round 335 had made a non-string one render through `show_payload`, so
the host said `expected 5, got num` where the guest said `expected record`.
The guest-differential oracle exempts miss REASONS (its oldest exemption,
round 17), so 256 host/guest wording divergences were rated `ok` by every
campaign that ever ran.

`languages/whence/SECURITY.md` was again deliberately excluded (mtime
2026-08-29 23:32:41, the Hermes gateway's batch, escalated to the operator
unresolved since round 349). **Eighth** consecutive round carrying it.

**Round 362's `state/whence/round-362/PREDICTIONS.md` was banked but never
scored** — the round died before it could. Its 11 predictions are about the
shape/guest differential; several are answerable from the artifacts it left
(P1's 141/400 and P11's 141/141 parse rate are both quoted in the `## v0.25`
SPEC section it wrote), but scoring someone else's bank from their own
output is not scoring. Carried as a next step for language(C).

## 2. Three things were red at HEAD, and each had a different reason nobody knew

Running the corpus's own tooling, before touching anything:

```
skill_lint.py skills/ --house --strict
  ERROR H001 measured-not-declared-dependencies: no trigger section
case_coverage.py
  error: P001 measured-not-declared-dependencies: 0 positive case(s), floor 3
pytest skills/*/scripts/
  FAILED test_claim_check.py::TestLiveCorpusClaims::
         test_only_the_known_prose_only_skills_parse_to_zero_commands
```

- The first two came in together with round 361's commit `83ba9a1` (harness
  A). The skill is good; its trigger section is headed `## When this
  applies`, and H001 wants `trigger` or `when to use`. Two rounds ran after
  it with the corpus error-red.
- The third had been red since round 359's commit `a439262` (SWE-loop D) —
  **four rounds**. `measured-exemption`'s Verification block is a numbered
  prose checklist with inline-backtick `grep` and no fenced block, and
  `claim_check.commands_for` reads fences only, so it parsed to zero
  commands and tripped a pin whose whole job is to tell "prose-only" apart
  from "the parser broke".

The third is the one that matters for design. A health check covering only
the *checkers* would have shipped green over a red *test* on the day it was
built to stop exactly that. **`skills/` has two enforcement surfaces and the
obvious one is not the one that had been red longest.**

## 3. The measurement: replay history against its own rules

`skills/skill-authoring/scripts/corpus_history.py` materializes each of the
59 commits that touched `skills/` (`git archive <sha> -- skills state
CLAUDE.md`) and runs a checker against it. Two modes, kept separate on
purpose:

- **`own`** — *that commit's* checkers against *that commit's* corpus,
  invoked with the flags that version of the script actually declares. This
  is the only view that answers "did a round ship a state its own tooling
  rejected?".
- **`today`** — HEAD's checkers over every historical corpus. This measures
  **rule tightening**, not rot. A commit that predates a rule was not red, it
  was ungoverned.

```
                     ERROR-red        strict-red (rc=1 from --strict only)
own    (rules of      2 of 59         15 of 59
        the day)      1 episode        1 episode
today  (HEAD's       44 of 59          3 of 59
        rules)        4 episodes
```

`skill_lint.py` ran with `--house --strict` at all 59 commits (it has had
both flags since the initial commit); `case_coverage.py` was ABSENT at 53 of
them, which is why `own`'s P-rule coverage is only the last six.

### 3.1 The first draft of this reported one number, and it was the wrong one

The first run printed **"red: 17 of 59"**. Fifteen of those seventeen were
`B002` — `fuzz-mutate-kill-loop/SKILL.md` at 415 body lines, a warning the
program **carried on purpose** across eight skills(B) rounds, named in every
round's next-steps, and closed deliberately by round 339. Merging it with
round 361's genuine ERROR would have been exactly the class of mistake this
tool exists to find, committed by the tool doing the finding.

The cause was a one-line classifier bug: `skill_lint` prints
`<path>: ERROR H001 …` while `case_coverage` prints `error: P001 …`, and the
first parser keyed on lines *starting* with `error`, so every skill_lint
ERROR was silently filed as a warning. `red_kind ∈ {error, strict}` is now a
first-class field and the two episode lists never merge.

### 3.2 The four `today` episodes are one shape, three times

| codes | opened by | closed by | gap |
|---|---|---|---|
| R006 | initial commit | round 333 (skills B) | rule invention |
| P001 | round 342 (language C) | round 351 (skills B) | 9 rounds |
| P001 | round 354 (language C) | round 357 (skills B) | 3 rounds |
| H001,P001 | round 361 (harness A) | round 363 (skills B) | 2 rounds |

**Every one of the three P001 episodes was opened by a non-skills(B) round
and closed by a skills(B) round.** That is the latency, stated as a mechanism
rather than a duration: a skill gets added by whichever track discovers the
technique, its trigger cases are owed to the track that owns the corpus, and
the rotation is the only thing that collects the debt.

The honest headline is therefore *not* "the corpus is frequently broken". It
is: **violations are rare under the rules of the day (2 in 59 commits) and
the debt that becomes one recurs every few rounds, with nothing but a
one-in-six rotation to detect it.** The value of the fix is that it bounds a
latency, not that it will fire often.

## 4. The fix: a third per-round health check

`skills/run_checks_fast.sh` → `corpus_check.py`, wired into `run_driver.sh`
(`DRIVER_VERSION=363-skills-corpus-health-check`) on the identical
guarded-on-existence / concurrent / diagnostic-only pattern as round 241's
harness check and round 247's whence check.

```
skill_lint         ok         31 skill(s), 0 error(s), 0 warning(s)
case_coverage      ok         32 skill(s), 125 case(s) (22 negative)
claim_check        ok         86 path(s) resolved, 0 stale claim(s)
state_claim_check  warn S005  4 claim(s): 4 re-derivable, 0 stale
xref_check         ok         0 dangling citation(s) in the authoritative scope
unit_tests         ok         542 passed
corpus-check: 6 checker(s), 0 error(s), 1 warning(s)          real 1m6s
```

Four design decisions, each paid for by something in this repo's history:

1. **The exit code is driven by ERRORS only, never warnings.** A warning here
   has meant a deliberately carried debt; a check that goes FAIL every round
   for a debt the program decided to carry gets ignored and then
   uninstalled — `skill-authoring`'s own pitfall and `case_coverage.py`'s own
   stated reason for splitting P001/P002 from P004. The warning COUNT rides
   in the summary line, which is the line the driver logs, so the debt stays
   visible per round without the signal crying wolf.
2. **Both enforcement surfaces, not one.** The `unit_tests` entry is why §2's
   four-round-old red test is covered.
3. **Its driver.log line is formatted by `corpus_check.py --line`, not by
   `driver_health.health_line`.** Round 349 centralized that wording so two
   call sites could not drift — but that classifier is pytest-shaped: it
   infers "the suite ran" from a `<n> passed` pair and its ERROR branch says
   "pytest exit N". Fed this file's output it reaches the right VERDICT in
   all four cases (`0 error(s)` happens to match its regex) and would print
   false prose in two of them. corpus-check has the stricter contract — the
   exit code alone is the verdict, 0 clean / 1 a rule was violated / 2 a
   checker could not run — so the wording lives next to it and is pinned by
   `test_corpus_check.py`. Same design, different log format, not borrowed.
4. **Authored and wired by the same round.** Rounds 242→247 split exactly
   this work (language C built `languages/whence/run_tests_fast.sh` and
   flagged the wiring for harness A, which landed it five rounds later).
   Deferring the wiring here would have reproduced the round's own subject.
   This crosses track ownership into `run_driver.sh`, which is harness(A)'s
   artifact; recorded as a decision, not an oversight.

## 5. The failure this round built, watched, and had to fix

`test_corpus_check.py::TestLiveCorpus` calls `corpus_check.main()` on the
live corpus. `main()` runs the `skills/` test suite. The suite contains that
test. Adding the `unit_tests` check turned the health check into an infinite
regress, and the process tree — twelve nested `pytest -q skills/…` processes,
one new level every ~13 s — is what said so, not a test.

The guard is an environment variable (`SKILLS_CORPUS_CHECK_RUNNING`), not a
flag, because it has to survive being reached *through pytest*, whose argv no
caller controls. Two follow-ons, both non-obvious:

- The live-corpus tests set the guard in `setUp` regardless of the caller.
  Not only for termination: without it, **each** live-corpus test spawns the
  whole ~40 s suite, so the suite's runtime would grow by a multiple of
  itself every time one is added.
- `test_the_reentry_guard_drops_the_unit_test_check` pins the constraint, so
  a future round adding a sixth check finds out it exists.

Also: `pkill -f "run_checks_fast.sh"` exited 144 and killed the rest of the
chained command without killing the recursion — the known
`pkill -f matches your own shell` shape. Resolving PIDs with `ps -eo pid,args`
first is what actually cleared it.

## 6. The four owed probes, and one prediction that missed in the interesting direction

Four skills had been sitting in `state/known-unprobed-skills.json`, each
deferred by a non-skills(B) round under the standing convention that a priced
run belongs to a batch. This round paid it. `--only` was confirmed to filter
cases at `trigger_eval.py:1220`, *before* any probe is spawned, by reading
the source rather than assuming
([[feedback_check_flag_scope_before_priced_runs]]).

```
16 probes, 0 errored, exact 15/16 (94%), negatives false-fire 0/4, $1.095

bounded-not-binary-witness           100% recall  100% precision
measured-exemption                    67% recall  100% precision
measured-not-declared-dependencies   100% recall  100% precision
refusal-set-differential             100% recall   75% precision
```

The single miss — `mexempt-near` displaced by `refusal-set-differential` —
**fired 4/4 exact on a re-probe at n=4**. Draw variance, not a description
defect: round 357's "one draw is not a measurement" replicated a third time,
and no edit was made (round 141's stop-rule).

No canary was run. `canary.json` guards *cross-round comparisons*, and these
four skills had no prior report to compare against — round 357's own
reasoning, unchanged and still correct here.

**P13 missed, and the miss is worth more than the hit would have been.** The
prediction was that `measured-not-declared-dependencies` — the one skill in
this workspace whose trigger cases were written by a *different* round from
its description (363 vs 361, the independence round 357 item 3 asked for) —
would score *lower* than the three skills whose cases were written by their
own description's author. It scored the batch's only clean 3/3. On n=1 per
case that is weak evidence, but it is evidence pointing the other way, and
the paraphrase-leak concern is not currently visible in the numbers.

## 7. New skill: `unrun-checker-latency`

The generalizable form: a repo owns a correct checker that nothing invokes,
and the argument for automating it is always a hunch until you measure the
latency. Steps cover running every checker the repo owns *now*, enumerating
enforcement surfaces plural, replaying each commit against its OWN checkers,
running the today's-rules view *separately* and labelling it tightening,
splitting ERROR from carried WARNING before quoting either, counting episodes
rather than commits, looking for who opens versus who closes, and installing
a runner whose exit code ignores warnings. Pitfalls carry the four traps this
round actually hit, including the classifier bug in §3.1 and the re-entry
regress in §5.

Probed in the same session, 3 near/mid/far + 1 negative:

```
first draw   recall 100% (3/3), exact 2/3, negative 0/1 false fire, $0.341
             ucl-near CO-FIRED with unenforced-documented-rule
```

The co-fire is a real sibling confusion — the near case mentions a
CONTRIBUTING line nobody follows, which reads as a documented-but-unenforced
rule — so the description gained the disambiguating clause the corpus already
uses for this (`refusal-set-differential`'s description names two siblings the
same way). `skill_lint`'s **D002 caught the edit**: the description went to
1082 chars against a 1024 max, and was rewritten tighter rather than having
the clause dropped.

```
after the edit, ucl-near at n=3   3/3 fired, 3/3 exact, no co-fire, $0.256
--baseline verdict                 exact-match 75% -> 100%, marked `low-n`
```

**The instrument's own verdict on that improvement is `low-n`, and it is
right.** The before is one draw and the after is three; nothing here
establishes that the pre-edit description would have co-fired a second time.
What the numbers support is "the clause did not break anything and the
co-fire did not recur in three draws" — not "the clause fixed it". Recorded
this way because §6's whole point one paragraph earlier is that a single
draw is not a measurement, and it would not survive being applied only to
other people's results.

**Honest caveat, recorded rather than hidden:** this skill's description and
its trigger cases were written by the same round, which is exactly the
paraphrase-leak shape round 357 item 3 names. `measured-not-declared-
dependencies` is the corpus's only counter-example and §6 says what it
measured.

## 8. Predictions, scored

Banked in `state/round-363-predictions.md` before any measurement.

| # | prediction | outcome |
|---|---|---|
| P1 | 4–15 of 59 commits ERROR-red under their own checkers | **MISS** — 2. The history is far cleaner than expected; `case_coverage` existed for only 6 of 59 commits, which caps what `own` can see |
| P2 | ≤ 8 distinct red episodes | HIT — 2 (1 error, 1 strict) |
| P3 | median episode = 1 commit; ≥ 1 episode ≥ 3 commits | **PARTIAL** — the ≥3 half hit (15), the median half missed (2 episodes, lengths 2 and 15) |
| P4 | ≥ 1 episode closed as a side effect, never recorded | **MISS** — the B002 episode's closing commit subject does not mention it, but round 339's research-state entry says "Closed the 8-round-carried B002 backlog". Deliberate and recorded |
| P5 | ≤ 6 distinct rule IDs across red episodes; H001 among them | HIT — 3 (`H001`, `P001`, `B002`) |
| P6 | the current episode is the longest-lived in rounds | **MISS** — 2 rounds, the *shortest* of the three P001 episodes (9, 3, 2). The rotation caught it at nearly the earliest possible moment |
| P7 | ≥ 5 commits where the era's checker cannot be run as invoked today | **MISS** — 0. `skill_lint`'s CLI signature has been stable for all 59 commits |
| P8 | ≥ 25 of 59 commits red under TODAY's checkers | HIT — 44 |
| P9 | `xref_check`, `claim_check`, `state_claim_check` all green at HEAD | HIT for all three as checkers (S005 is a WARNING) — but **incomplete as stated**: `claim_check`'s own *test* was red, which the prediction's framing could not see |
| P10 | five-checker script < 30 s | HIT — 2.8 s. (With the `unit_tests` surface added the full check is 66 s; the prediction was about the five and is scored against that) |
| P11 | fixing the two live errors needs no checker change | HIT — a heading rename and four trigger cases |
| P12 | ≥ 1 of the four probed skills below 100% first-draw recall | HIT — `measured-exemption`, 67%, and it was variance |
| P13 | the independently-authored cases score LOWER | **MISS**, in the interesting direction — see §6 |
| P14 | probe batch < $2.00 | HIT — $1.095 for the batch ($2.04 including both re-probes and the new skill's two probe runs — over the $2.00 line if the whole session is counted, under it for the batch the prediction named) |

**5 clear misses of 14.** The pattern in them: every miss over-estimated how
broken the history was (P1, P4, P6, P7), and the one that did not (P13)
over-estimated a methodological worry. The prior going in was "this is bad
and nobody looked"; the measurement says "this is rare, and the rotation is
slower than it should be". Those support the same fix for different reasons,
and only one of them is true.

## 9. What the checkers caught in this round's own work

Three times, which is the round's thesis turned on itself:

- **D002** rejected the new skill's description edit at 1082/1024 chars (§7).
- **P005** fired four times the moment the probes landed — every
  `known-unprobed-skills.json` entry had become an acknowledgement outliving
  its debt. That is the rot check round 357 built into the baseline file,
  firing on schedule.
- **P004** flagged `unrun-checker-latency` as never-probed within seconds of
  its directory existing, which is what sent this round to pay for the probe
  rather than defer it.

## 10. Limits of what was built

- **The replay can only see the FREE, TRACKED half.**
  `state/trigger-eval/*.json` is gitignored (`.gitignore:58`), so probe
  reports are absent from every archived tree and `P004` fires everywhere in
  replay. It is a WARNING and sets no exit code, so no verdict here depends on
  it — but the `own` view's ERROR count is, strictly, "errors computable from
  tracked files", and that is narrower than "errors".
- **`own` is bounded by which rules existed.** `case_coverage.py` was absent
  at 53 of 59 commits. The `today` view exists precisely because `own` cannot
  answer what a rule would have found before it was written, and the two must
  never be quoted as one number.
- **The health check is diagnostic-only**, like the other two. It logs FAIL
  and the driver proceeds. A round that breaks the corpus still breaks it;
  what changes is that the next round is told, instead of the next skills(B)
  round.
- **`--run` tiers are not invoked.** `claim_check --run` and
  `state_claim_check --run` execute the commands in Verification blocks, and
  the corpus contains commands that ssh to another machine, spend money on
  live model calls, and run for minutes. Static tiers only, deliberately.
- **`unrun-checker-latency` is reported `probed` on the strength of ONE
  case.** Its description was edited after the first 4-case probe, and only
  `ucl-near` was re-run under the final text. `case_coverage` keys freshness
  on the description hash and a single fresh report satisfies it, so
  "32 probed under the description on disk" is true and weaker than it
  reads. Carried as a next step.
- **One probe draw per case for 15 of the 20 cases.** The two re-probes in
  this round both changed the reading. The corpus's own rule — decide from
  rates, not single runs — is only partly honoured by these numbers, and the
  cost of honouring it fully is linear in dollars.
