# Round 453 (skills B) — the check that runs after you are gone

**Subject.** Round 452's `skills-check` reported **3 errors** where round
451's reported 0. All three were introduced by round 452, and **round 452
could not have seen any of them**: `skills/run_checks_fast.sh` runs after the
round's process exits, and round 452 was killed by the driver's outer 3300 s
timeout at 11:25 with the check's verdict landing at 11:37.

**Result.** Round 363 built that check to cut a corpus violation's detection
latency from *"the rotation, up to six rounds"* to one round. Measured here
for the first time, over all **89** `skills-check` lines in `logs/driver.log`
(rounds 364–452): **24 red rounds of 89 (27%), 16 episodes, mean 1.50 rounds,
longest 4** — and the two rows that matter, **0 of 16 episodes were opened by
a skills(B) round**, while **9 of 15 were closed by one**. The rounds that
break the corpus are never the round that owns it. One round is a *floor*,
not a target, and the only way under it is a check the author can run while
still alive. `corpus_check.py --precommit` is that check: **25.95 s** against
the full **124.74 s**, catching all 19 violations round 452 shipped.

---

## 1. Housekeeping first — and it was most of the round's evidence

`check_round_recorded` reported 14 uncommitted paths and a round-452 entry
missing from `research-state.md`. Round 452 had committed parts 0 and 1 and
died holding everything else: its knowledge file, the entire Whence v0.44
implementation, `depthcensus.py` and two SKILL.md upgrades.

Verified before landing, never taken on 452's own narration:

```
tests/test_v44.py test_depthcensus.py test_v43.py -> 103 passed in 66.14s
tests/test_v22.py                                  ->  55 passed
```

The driver's own post-round whence check had already run against that exact
tree: `1 failed, 2343 passed, 3 skipped`. **The single failure was
`test_v22.py::test_research_state_track_c_names_the_same_version_as_spec_md`
— i.e. the absence of round 452's state entry itself.** That test exists
because a version number lives in two places and the second one "gets a test
instead of a promise" (round 416). Writing the entry is the fix; exempting
the test would have deleted the only thing that noticed.

So this round backfilled the `### Round 452` entry and the
`- **Language (C):** **v0.44**` line from 452's knowledge file, labelled as a
backfill, and landed the diff — excluding `SECURITY.md` (escalated round 349,
the operator's) and `state/round_counter` (standing dirty).

**Fifth consecutive round to land its predecessor's work: 448→449, 449→450,
450→451, 451→452, 452→453.** Round 452's own knowledge file called four in a
row "a pattern, not three coincidences". It is five.

---

## 2. The three errors, and why the round that made them could not see them

| checker | finding | fix |
|---|---|---|
| `xref_check` X001 | `decision 53` cited at **18** authoritative sites, never written into SPEC.md's `## Anti-mainstream design decisions` registry | registered as entry 53 |
| `xref_check` X004 | `values.py:533` cites `state/whence/round-452/depth-census.json` as "that round's reading"; the file was never committed | **re-derived**, not reworded |
| `carryforward` K003 | the ledger still said round 452's bank was `unscored` while its knowledge file carried the full 16-row scoring | moved to `scored` |

Round 452 wrote the `## v0.44` narrative section describing decision 53 and
stopped there. **A decision's identity lives in two places — the narrative
section and the registry — and only the narrative one is load-bearing at
authoring time.** All 18 findings cleared with ONE registry line, because
`xref_check`'s finding key is `CODE:identifier` rather than `file:line`; the
registry is now 40 entries.

The X004 fix was made by **re-running the instrument rather than editing the
sentence**. `depthcensus.py` at HEAD (33.9 s) reports max BUILT depth **14**
(`self_host.lang`), max PRINTED **2**, **3,587,551** nodes walked — matching
round 452's headline exactly. Had it disagreed, that would have been the more
valuable result and the round file says so (bank C2).

K003's own wording is the general lesson and it caught itself:
*an acknowledgement that outlives its debt is a mute button.* The moment 452's
entry moved to `scored`, K001 fired demanding an entry for **this** round's
bank — the checker is symmetric, which is why it works.

The three `unit_tests` failures were not count pins (bank C4 predicted they
were — MISS). They were the **live-corpus mirrors** of the two red checkers:
`test_carryforward_check.py::TestLiveCorpus::…`,
`test_xref_check.py::TestLiveBaselineIsHonest::…`, and
`test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`. That
overlap is what makes §4's exclusion safe, and it was measured rather than
assumed.

---

## 3. The measurement: what one round of latency has actually cost

Parsed from every `skills-check` line in `logs/driver.log`, rounds 364–452.

**A parsing failure worth recording**, because it produced a plausible wrong
answer first. `re.search(r"(\d+) error\(s\)", line)` reports round 452 as
`errors=0`: the line contains `selfdesc_check … 0 error(s), 0 warning(s)`
*before* the aggregate. Anchoring on the summary
(`corpus-check: \d+ checker\(s\), (\d+) error\(s\)`) changes 28 "red" rounds
into the true 24 and changes *which* rounds they are. Caught only because a
round I knew to be red parsed as green. **A count extracted from a log line
must anchor on the summary token, not on the unit** — the same shape as round
452's P13, which banked a suite total against a number whose SCOPE it had not
checked.

```
runs with >=1 ERROR    24 of 89 (27%)
episodes               16 — mean 1.50 rounds, longest 4 (419-422, 431-434)
opened by track        language(C) 7 | SWE-loop(D) 6 | harness(A) 2 | NUC(E) 1
                       skills(B) ZERO
closed by skills(B)    9 of 15 (60%)
latency opened->closed mean 1.53 rounds, median 1, max 4
```

**Zero of sixteen episodes was opened by the track that owns the checkers.**
Every corpus violation in 89 rounds of history was introduced by a round
working on something else, and the majority then waited for skills(B) to come
back around. `unrun-checker-latency`'s step 7 predicts exactly this shape as a
*mechanism* ("opened by any contributor, closed only by the one who owns that
area"); these are its numbers.

This also **refines round 435's carried reading**, which said the check "goes
red at the rate of the ROTATION, and the rotation is six rounds". The rotation
does not govern the *duration* — mean 1.50, median 1. It governs *who closes*.
Round 435 was looking at episode 431–434, one of only two length-4 episodes in
the whole log, and generalised from the tail.

---

## 4. `corpus_check.py --precommit` — the subset the author can run

Every checker priced solo on this box (`nproc` 1):

```
unit_tests  99.31s   verb_audit 15.29s   xref_check 4.44s   selfdesc 4.37s
carryforward 0.56s   skill_lint  0.21s   placeholder 0.19s  case_cov  0.15s
claim_check  0.13s   state_claim 0.09s                       TOTAL 124.74s
```

`unit_tests` was measured twice — **99.83 s** run standalone earlier in the
round and **99.31 s** inside the timing harness above; both are solo, the
0.5 s spread is run-to-run noise, and the source comment's estimate is
"~37s".

**One checker is 79.6% of the cost.** Dropping it leaves 25.4 s measured, and
the surviving nine catch all 19 of round 452's violations (§2). Measured
end-to-end: `--precommit` = **25.95 s, 0 errors**.

The prose costs already in `checks()` (`0.7 s`, `<0.5 s`, `~2 s`, `~30 s`,
`~37s`) are stale in both directions — `unit_tests`' "~37s" against 99.3 s
measured here and 162.34 s measured by round 451 under contention;
`verb_audit`'s "~30 s" against 15.29 s. A test now requires every exclusion to
carry a reason containing a digit.

**Design decision: the preset is defined by what it EXCLUDES.** This file's
own history is the argument — `checks()`'s docstring said "five" checkers for
two checkers' worth of drift, and `run_checks_fast.sh`'s header said "six"
until round 429. An inclusion list rots silently by omission. Written as an
exclusion, a new checker joins the preset automatically and anyone who wants
it out must name it with a measured reason.
`test_the_exclusion_table_is_the_only_thing_keeping_a_checker_out` enforces
that, and `test_no_exclusion_names_a_checker_that_no_longer_exists` enforces
the mirror-image rot (K003's class, applied to this table).

**A subset run must not print a summary a full run could have printed.**

```
corpus-check: 9 checker(s); SUBSET, did NOT run: unit_tests, 0 error(s), …
```

`subset_clause([])` returns `""`, so a full run's line stays byte-identical to
every line before round 453 — `run_driver.sh` greps it and rounds quote it.
A typo'd `--only xref` is `rc=2` naming the known checkers, never an empty
green run: shipping a false all-clear inside the fix for false all-clears
would be the joke writing itself.

10 new tests in `test_corpus_check.py`, all passing.

---

## 5. The non-vacuity check, run because a skill demanded it one round ago

Round 452 shipped two configuration differentials whose two arms were the same
arm — `full_show_named(node, cap=FULL_SHOW_NEST)` binds the constant at
DEFINITION time, so patching the module global compared new against new and
**both tests passed against a completely unchanged renderer**. That defect was
promoted into `skills/named-guardian-must-go-red/SKILL.md` ("The differential
arm nothing moved") in the diff this round landed in part 0.

So the flag was checked for vacuity before it was trusted (bank E1):

```
full      : 10 checkers, skipped []
precommit :  9 checkers, skipped ['unit_tests']
only=xref :  1 checker,  skipped 9
NON-VACUOUS: the flag moves the selected list, not just a label.
```

`checks()` builds its list at call time from a literal, so the trap was not
available here — **but the way you know that is by asserting the two
selections differ, not by reading the code and feeling reassured.** E1: HIT,
first try, and the assertion is now
`test_precommit_selects_a_strict_subset_and_not_the_whole_list`.

### The tests passed standalone and failed under the only runner that runs them

Written, run, green: **11 passed**. Then the full corpus check ran them and
**5 of the 11 failed**.

`corpus_check.run_one` sets `REENTRY_ENV` for every checker it spawns — the
re-entry guard, so that a runner which runs a suite that invokes the runner
terminates — and `checks()` reads it and **omits `unit_tests`**. So inside
the only runner that ever executes this suite, `checks()` returns a NINE-row
table with the one excluded checker missing, and every assertion in the new
class was quietly made against the wrong table:

```
--only unit_tests            -> ValueError: unknown checker
--precommit                  -> selected the whole list (assertNotEqual fails)
PRECOMMIT_EXCLUDES           -> names a checker that "does not exist"
run_checks_fast.sh --list    -> subprocess INHERITS the guard; prints 9 rows
```

Reproduced in one command — `SKILLS_CORPUS_CHECK_RUNNING=1 pytest -k
Precommit` → `5 failed, 5 passed` — which is the whole diagnosis.

The fix clears the variable in `setUp` rather than skipping under it: the
properties are about the COMPLETE table and the selection logic over it, and
**a skip would have hidden these tests from the runner that matters, which is
the same mistake in a different costume.** A new
`test_the_full_table_includes_the_excluded_checker` guards the fix itself, so
a future `setUp` regression cannot silently put every other test in the class
back on the nine-row table. 11 pass under both environments now.

Three things went green-then-red in this one round for three different
reasons — round 452's default-argument differential, this re-entry table, and
`carryforward` K003 firing on my own bank the moment the knowledge file
appeared. **`--precommit` would not have caught this one**, because it
excludes `unit_tests`, which is where these tests live. That is the honest
cost of the exclusion in §4, and it is not hypothetical: it happened inside
the round that made the exclusion. The post-round full check found it, doing
exactly the job §3 says it does — one round late, except that this time the
author was still alive to read it.

---

## 6. Predictions, scored

Banked at `state/skills/round-453/PREDICTIONS.md`, committed (`afe52d6`)
before any measurement in the subject ran.

| # | basis | claim | verdict |
|---|---|---|---|
| A1 | MODEL | `unit_tests` > 50% of total cost | **HIT** — 79.6% |
| A2 | MODEL | ≥6 of 10 checkers under 10 s | **HIT** — 8 |
| A3 | MODEL | cheap-4 under 60 s, likeliest ~25 s | **HIT (band)** — 5.40 s; likeliest wrong by 4.6x |
| A4 | MODEL | `case_coverage` is 2nd most expensive | **MISS** — it is 8th (0.15 s); `verb_audit` is 2nd |
| A5 | SENT | no non-`unit_tests` checker over 120 s | **HIT** — max 15.29 s |
| B1 | MODEL | red rounds in band 8–25 | **HIT** — 24 |
| B2 | MODEL | mean red-run length ≥ 2 | **MISS** — 1.50; 11 of 16 episodes are singletons |
| B3 | MODEL | longest episode ≥ 4 | **HIT** — 4, twice |
| B4 | MODEL | ≥60% of episodes closed by skills(B) | **HIT** — 9 of 15, exactly 60% |
| B5 | SENT | ≥1 episode closed by a non-skills round | **HIT** — 6 of them |
| B6 | NONE | red rounds exceed green *(expected FALSE)* | **MISS as stated** — 24 vs 65; the annotation was right |
| C1 | MODEL | one registry line clears all 18 X001 sites | **HIT** |
| C2 | MODEL | re-derived max BUILT depth is 14 | **HIT** — exact, independently re-run |
| C3 | MODEL | 0 errors after all fixes | **HIT** — see §7 |
| C4 | SENT | the 3 `unit_tests` failures are count pins | **MISS** — live-corpus assertions |
| C5 | MODEL | ≥1 failure in `test_xref_check`/`test_carryforward_check` | **HIT** — both, plus `test_corpus_check` |
| D1 | MODEL | under 120 added lines in `corpus_check.py` | **MISS** — 135 |
| D2 | MODEL | subset catches ≥18 of 19, likeliest all | **HIT** — 19 of 19 |
| D3 | MODEL | subset under 60 s | **HIT** — 25.95 s |
| D4 | SENT | K003 is order-dependent, not pre-commit catchable | **HIT** — and see §8 |
| D5 | NONE | declined: whether a future round adopts it | **declined, not scored** |
| E1 | MODEL | non-vacuity passes first try | **HIT** |

**16 HIT, 5 MISS, 1 declined of 22.**

**The misses are not one family this time, which is itself the finding.**
Round 452's five misses were all the same defect (a population silently
scoped to `examples/`), and I banked with that in mind — every population
above is named explicitly, and no population miss occurred. What went wrong
instead was *magnitude*: A3 got the band right and the likeliest value wrong
by 4.6x, A4 was wrong about which checker is expensive, B2 was wrong about
episode shape, D1 undercounted my own comment-writing. **Correcting last
round's error class does not lower this round's error rate; it moves it.**
A4 and B2 are the pair worth reading — both are claims about a distribution's
SHAPE made from a single remembered instance (`case_coverage` sounded
expensive; episode 431–434 was the one I had read), and both are the kind of
claim a 20-second command answers.

C4 is the honest small miss: I predicted the failing tests would be pinned
counts because that is the common shape in this repo, without opening the
file. They were live-corpus assertions — the *better* shape, and the one that
made §4's exclusion argument available.

---

## 7. Verification

```
$ bash skills/run_checks_fast.sh --precommit | tail -1
corpus-check: 9 checker(s); SUBSET, did NOT run: unit_tests, 0 error(s),
7 warning(s); coverage: …                                    [25.95s]

$ bash skills/run_checks_fast.sh --only nosuchchecker; echo rc=$?
corpus_check: unknown checker(s): nosuchchecker; known: skill_lint, …
rc=2

$ python3 -m pytest -q skills/skill-authoring/scripts/test_corpus_check.py \
    -k Precommit
10 passed, 40 deselected in 0.25s

$ python3 skills/skill-authoring/scripts/skill_lint.py \
    skills/unrun-checker-latency --house --strict
skill-lint: 1 skill(s), 0 error(s), 0 warning(s)

$ SKILLS_CORPUS_CHECK_RUNNING=1 python3 -m pytest -q \
    skills/skill-authoring/scripts/test_corpus_check.py -k Precommit
11 passed, 40 deselected             # under the runner's own environment

$ bash skills/run_checks_fast.sh | tail -1        # the FULL check, all ten
corpus-check: 10 checker(s), 0 error(s), 8 warning(s); …
  unit_tests  ok  939 passed in 103.10s
```

Round 452's line was `3 error(s)`; this round's is **0**. The warning count
went 7 → 8: the new one is `state_claim_check` S005, raised because this
round's own state entry added re-derivable claims (coverage 1/8 → 2/10). A
warning here is a carried debt by design and never sets the exit code —
recorded rather than silenced.

`skills/unrun-checker-latency/SKILL.md` 267 → **351** lines, new section
*"The runner you installed still has a floor of one"*, a new consequence under
step 10 (re-entry changes what the checker LIST is), and four new Verification
commands. The section's measurement and worked design were split into a new
`references/detection-latency-floor.md` (108 lines) when the body crossed
`skill_lint`'s B002 line — the precedent set by rounds 285 and 315 — taking it
from `1 warning(s)` back to **`0 error(s), 0 warning(s)`**. The `description` frontmatter was deliberately **not** changed —
the new material is inside its existing scope ("installing a runner whose
exit code cannot cry wolf"), and changing it would invalidate the skill's
probed trigger cases and add a fifteenth item to the unpriced probe backlog.

**One Verification command was written unrunnable and caught by running it.**
`python3 -c "import corpus_check…"` fails with `ModuleNotFoundError` from the
repo root; it needs the `sys.path.insert`. Shipped only after being executed
as written. A Verification block whose commands were never run is the C001
defect this corpus has an error code for.

---

## 8. Failures and residuals, honestly

**The subset is BUILT and NOT WIRED, and that is this round's own instance of
the pitfall the skill it upgrades warns about.** `unrun-checker-latency`'s
own pitfall list says to build and wire in one change, and measures the cost
of not doing so at 5, 21 and 0 rounds on this repo. I cannot wire this one:
it must run *inside another round's session, before that round's last
commit*, and the harness has no hook that fires there. The driver can only
run it after the process exits, which is the latency this round exists to
measure. So the unwired state is recorded here and in next-steps rather than
disguised: **`grep -c "precommit" run_driver.sh` returns 0, on purpose, and
if a future round wires it that number is the check.**

**D4's residual is real and ordering-shaped.** `carryforward`'s K003/K001
cannot be satisfied by a pre-commit run in the general case: the debt is
discharged by a knowledge file the round writes last. The documented order
therefore puts `--precommit` *after* the knowledge file, not before the first
commit — which weakens the "catch it early" story for exactly one checker,
and pretending otherwise would make the tool wrong in a way only a later
round would find.

**`verb_audit` at 15.3 s is 60% of the subset's cost and can never turn the
corpus red** — every finding it emits is a WARN by construction. It is in the
preset because the preset is an exclusion list and nobody has excluded it; on
the argument used for `unit_tests` (error-detection power per second) it is
the next candidate, and the counter-argument is that it publishes coverage
into the summary line. **Not decided. Named.**

**Not measured:** whether 27% red is high or low. There is no comparison
corpus, and the number is reported as a rate against this repo's own history
rather than as a judgement. Likewise the 19-of-19 catch rate is measured on
**one** shipped tree (round 452's); it is the only tree available at full
fidelity, and a second instance would need history replay of the kind
`corpus_history.py` already does for commits.

**Carried, untouched by this round, and NOT re-derived:** the J005 recall gap
(round 435 item 2); `selfdesc_check`'s top-level-only sweep, still 82 of 680
prose fields; the **fourteen**-deep probe backlog, which needs operator
authorisation and money this round did not have; and CLAUDE.md's
`CRITICAL MISSION` block, now re-escalated for the **nineteenth** time and
still a one-line deletion only the operator can make.
