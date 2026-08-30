# Round 357 — skills(B) — the corpus had never been measured, and one draw is not a measurement

*2026-08-30. Track B (rotation 357 mod 6 = 3 → skills). Model: claude-opus-5.*

## 0. One line

Twenty-four of this workspace's twenty-seven skills had never been probed —
three of them had no test case at all — because the shipping checklist that
requires a probe is enforced by nothing that runs. This round probed the
whole corpus for the first time (105 cases, $6.86, 90% exact match), then
re-probed the ten misses and found **seven of the eight no-fire cases fired
on an identical second draw**. One miss survived, was a real vocabulary gap,
and is fixed and re-measured. The instrument that produced all of this
existed already; what did not exist was anything that ran it.

## 1. Round 356's work, landed first

The record-gap check reported round 356 (language C) as `error:max_turns`
with `git_committed=False` and 18 unattributed dirty paths. Its work was
real and complete: Whence v0.23, the mandatory statement separator.

Verified BEFORE landing, not after:

```
whence  pytest tests/ (fast + whence_slow)   1309 passed in 359.65s, exit 0
skills  skill_lint.py --house --strict       27 skills, 0 errors, 0 warnings
```

Committed as `80bcf4f` with attribution. **`languages/whence/SECURITY.md`
was deliberately excluded** — it is the Hermes gateway's rewrite, asserting
four security controls this repo does not have, escalated to the operator
unresolved since round 349 §8 and untouched by round 356. That is now the
seventh consecutive round it has been carried, and the exclusion is a
decision, not an oversight.

Round 356 had itself landed round 355 the same way. Two consecutive rounds
now begin by finishing the previous one; the convention works, and the fact
that it keeps being needed is its own finding (§7).

## 2. The gap: a checklist item with no teeth

`skills/skill-authoring/SKILL.md`'s shipping checklist:

```
[ ] trigger_eval.py shows 100% recall on the skill's cases and no false
    fires on negatives
[ ] trigger_eval.py … --audit <reports-dir> exits 0: every skill `probed`
    under its current description, none STALE/never
```

`--audit` is real, offline, free, and **exits 1 when that is false**. Its
first run this round:

```
summary: 24 never, 3 probed; 3 under the 3-positive floor; exit 1
```

Three skills — `errors-that-name-the-fix` (round 354),
`pristine-checkout-differential` (355), `unenforced-documented-rule` (356) —
had **zero** cases. One per round, three rounds running, each added by a
round whose track was C or A, each invisible to every instrument the corpus
owns. A skill with no cases cannot be probed, cannot regress, and cannot
fail.

This is round 356's own finding, one round later and one level up: a rule
stated in the documentation and checked by nothing. The corpus wrote the
skill for that shape (`skills/unenforced-documented-rule/`) and was an
instance of it. The mechanism is round 355's, verbatim — *a rule living in
one function's docstring does not reach the next function that needs it;
only something that RUNS does* — and `--audit` is a stronger version of the
same trap, because it is not a docstring. It is executable, correct, and
never invoked.

## 3. What was built: `case_coverage.py`, and where the line is drawn

Case coverage is FREE (it reads two files). Probe freshness is PRICED (this
round's full sweep cost $6.86 of live model calls). One check spanning both
would be either a test that spends money or a rule with no teeth, so the
codes are split by what a test can afford:

| code | severity | what |
|---|---|---|
| P001 | error | skill has fewer than 3 positive cases |
| P002 | error | a case expects a skill not in the corpus |
| P003 | warning | a case prompt contains its own expected skill's name |
| P004 | warning | never probed / STALE, and not in the baseline |
| P005 | error | baseline entry is stale (now probed, or skill is gone) |

P001/P002 are asserted by `test_case_coverage.py::TestLiveCorpus`, which
runs inside the `python3 -m unittest discover` line that already exists in
skill-authoring's Verification block. **That is the whole point of the
file.** A new skill with no cases now fails a test that a skills round
already runs, rather than being reported to nobody by a flag no round types.

Four design points worth keeping:

- **P004 is a warning against a baseline, not an error.** skill-authoring's
  own pitfall says a checker that can never go green gets uninstalled.
  Probing costs money; a hard failure on "never probed" would be a check no
  round could clear without a spend it may not have budgeted.
- **P005 is the baseline's rot check, and it is an ERROR.** An entry that has
  since been probed, that names a deleted skill, or that has no `owner` is a
  mute button outliving its debt. The baseline file
  (`state/known-unprobed-skills.json`) is EMPTY today — this round probed all
  27 — so the mechanism ships tested and unused rather than untested. It
  exists rather than being absent for a reason §11 records: the corpus's own
  X004 check failed the build over the sentence that cited it.
- **Duplicate case ids are NOT a code here.** `trigger_eval.load_cases`
  already raises on them. Two checks for one property is how they drift.
- **P003 fires on the FULL name only.** `alpha-thing` leaks as "alpha thing"
  and "Alpha_Thing", but a single shared token ("skill", "agent", "thing") is
  ordinary domain vocabulary and flagging it would bury the real thing. Also
  scoped to the case's OWN expected skill: naming a *sibling* is how a
  displacement case is written on purpose. Measured result on the live
  corpus: **0 leaks in 105 cases** — measured, not assumed.

21 tests, offline, 0.04s. Three of them guard `TestLiveCorpus` against
passing vacuously (catalog ≥ 27, cases ≥ 105, and every SKILL.md-bearing
directory reaching the catalog `load_catalog` builds).

## 4. The first full-corpus probe

Nine cases were written for the three uncovered skills first (near / mid /
far, phrased without the skill name), taking the corpus to 105 cases.

```
mode=native model=sonnet protocol=strict concurrency=8
probes: 105 ok, 0 errored, exact-match 90%, negatives false-fire 0/17,
cost $6.861
```

Twenty-one of twenty-seven skills at 100% recall. **0/17 false fires on the
negatives** — with 48 host distractor skills present in the staged project,
which is the number that says the corpus is not simply trigger-happy.

The ten misses:

| case | expected | fired |
|---|---|---|
| `fmk-near` | fuzz-mutate-kill-loop | — |
| `pcd-mid`, `pcd-far` | pristine-checkout-differential | — |
| `otd-near` | optimization-transparency-differential | generator-trampoline-evaluator |
| `otd-far` | optimization-transparency-differential | — |
| `cri-far` | citation-registry-integrity | — |
| `dvnw-near`, `dvnw-far` | deleted-vs-never-written | — |
| `udr-mid` | unenforced-documented-rule | +errors-that-name-the-fix |
| `dsp-far` | declaration-scope-parity | +unenforced-documented-rule |

The last two are co-fires, not misses: recall is 100% for both expected
skills and the exact-match rule counts the extra as a false positive on the
OTHER skill. `udr-mid` is my own case-writing artifact — the prompt says
"without wrecking the good error messages we already have", which genuinely
invokes `errors-that-name-the-fix`. `dsp-far` is more interesting: round
356's brand-new skill co-fired on an existing skill's case, i.e. **adding a
skill can move a sibling's precision, and nothing in this corpus would have
noticed, because the sibling had never been probed either.**

## 5. The finding: seven of eight misses were noise

The obvious next move after that report is to start editing the descriptions
that scored 33%. Instead the eight no-fire cases were re-probed immediately —
same instrument, same model, same protocol, **same descriptions, zero edits**:

```
probes: 8 ok, 0 errored, exact-match 88%, cost $0.634

fmk-near   → fuzz-mutate-kill-loop            (was —)
pcd-mid    → pristine-checkout-differential   (was —)
pcd-far    → pristine-checkout-differential   (was —)
otd-near   → optimization-transparency-...    (was generator-trampoline-...)
otd-far    → optimization-transparency-...    (was —)
dvnw-near  → deleted-vs-never-written         (was —)
dvnw-far   → deleted-vs-never-written         (was —)
cri-far    → —                                (was —)   <- the only survivor
```

**7 of 8.** Three skills whose first-draw recall read `33%` are at 100% on
the second draw. `pristine-checkout-differential` — round 355's skill, whose
33% was the most alarming line in the report — fired on both of its "missing"
cases.

So the honest reading of the 90% figure is: **it is a screen, not a
measurement.** At n=1 the per-skill rates over 3-case sets are dominated by
draw variance; a 3-case skill can only score 0/33/67/100, so one noisy draw
looks like a catastrophic description defect. Every one of those numbers is
the kind of thing a round writes into `research-state.md` as a property of
the skill, where it then gets carried forward by copy — the exact rot
`state_claim_check.py` was built for, arriving through a new door.

skill-authoring already warned about this in the abstract ("repeated if a
miss looks like noise", "small models are unreadable at n=1"). This is the
first time the corpus has *measured* it, on its own probe model, and the
effect is much larger than "repeat if it looks like noise" suggests: the
majority of first-draw misses were not real.

**Cost of learning this: $0.63.** Cost of not learning it: a round of
description edits tuned to noise, shipped into 24 descriptions, with a
before/after comparison that would have "improved" no matter what was
written.

## 6. The one real miss, fixed and re-measured

`cri-far` missed twice. Its transcript (`--transcripts`, kept) is one line:

```
SKILLS=NONE
```

The prompt is a far paraphrase — *"turn on a docs linter across a 200-file
repo that will definitely be red on day one, and I don't own half of what it
will flag; how do I roll it out so the team doesn't just delete it?"* —
and `citation-registry-integrity`'s description covered that idea only as
"a keyed baseline so accepted debt stays visible without muting the check".
The concept was there; the roll-out vocabulary (red on day one, a corpus you
do not own, the team deletes it) was not.

Added it. The edit did not fit: the description went to **1233 chars against
a 1024 cap**, and fitting it back cost `"requirement FR-22"`, the
"long-running or autonomous program" phrasing, and the "false-positive
discipline for path references" clause. **The edit was a trade, not an
addition** — and the phrases traded away back other cases that were not
re-probed. That is now a pitfall in skill-authoring, because it is invisible
in a report that only shows the case you were fixing.

After, at n=2 per case:

```
probes: 6 ok, exact-match 100%, cost $0.485       cri-far 2/2 (was 0/2)
```

## 7. Two stale claims the same shape, found by running the other unrun tool

`claim_check.py`'s *static* tier reports 0 stale claims and is the tier
anyone runs. `--run`, which executes the `auto` commands and diffs their real
output, is the priced/slow tier, and nothing runs it either. Its first run
this round:

```
skills/skill-authoring/SKILL.md:325: STALE C002 ran_tests=430, observed 437
skills/skill-authoring/SKILL.md:336: STALE C002 skills=24, observed 27
skills/skill-authoring/SKILL.md:341: STALE C002 skills=24, observed 27
```

Rounds 354, 355 and 356 each added a skill without re-running the sweep —
the *same* rot round 351 fixed in this same file three rounds earlier, in
the document that documents the rot. The generalisation is now hard to
avoid: **this corpus has five checkers, and every one of them has a cheap
tier that gets run and an expensive tier that does not; both expensive tiers
examined this round were hiding real debt.** `--audit` (free but unrun) and
`claim_check --run` (priced and unrun) failed for different reasons and
produced the same outcome.

All three fixed, with the provenance note the house style requires so a
lower number in an older report is not read as a regression.

## 8. Verification

```
whence    pytest tests/ (fast + whence_slow)      1309 passed, exit 0
skills    skill_lint.py --house --strict skills/  27 skills, 0 err, 0 warn
          case_coverage.py                        27 skills, 105 cases,
                                                  27 probed, 0 err, 0 warn
          unittest discover -s .../scripts        458 tests, OK
          claim_check.py skills/                  27 skills, 0 stale (static)
          claim_check.py --run skills/skill-authoring/   3 stale -> fixed
          state_claim_check.py research-state.md  0 stale
          trigger_eval.py --audit state/trigger-eval     exit 0 (was: 24
                                                  never, 3 under floor)
probes    round-357-full-corpus      105 ok, 90% exact, 0/17 false, $6.86
          round-357-miss-reprobe       8 ok, 7 of 8 flipped,       $0.63
          round-357-cri-after          6 ok, 100%, cri-far 2/2,    $0.49
                                                          total    $7.98
```

### Pins checked by mutation

| mutant | killed by |
|---|---|
| a skill with no cases | `TestP001::test_a_skill_with_no_cases_is_an_error` |
| the floor hard-coded to 3 | `test_the_floor_is_a_parameter_not_a_constant` |
| negatives counted toward a skill's floor | `test_a_negative_case_does_not_count_toward_any_skills_floor` |
| a case for a deleted skill | `TestP002::test_a_case_for_a_deleted_skill_is_an_error` |
| P003 firing on one shared token | `test_one_shared_token_is_not_a_leak` |
| P003 firing on a sibling's name | `test_a_leak_of_a_DIFFERENT_skills_name_is_not_flagged_here` |
| a paid-off baseline entry | `test_a_baseline_entry_that_is_now_probed_is_an_error` |
| an unowned baseline entry | `test_an_acknowledgement_without_an_owner_is_an_error` |
| a description edited after its probe | `test_editing_a_description_after_a_probe_reopens_the_warning` |
| `TestLiveCorpus` passing on an empty corpus | `test_the_live_corpus_is_actually_being_read` |

## 9. Pitfalls this round hit

- **`pkill -f "<pattern>"` matched this session's own shell, twice**, and the
  chained command after it died with exit 144 — the recorded
  `[[feedback_pkill_f_matches_your_own_shell]]` pitfall, reproduced live
  including with the `[t]rigger_eval` bracket trick, because the bracket
  protects the *grep* from matching itself and does nothing about the `bash
  -c` line that contains the pattern. Resolve PIDs in a separate step, or do
  not kill at all: the second attempt cost a $0.49 probe run that was
  launched against a description edit that had not yet passed the linter.
- **A description edit can fail the linter after the probe is already in
  flight.** `D002` (1024 chars) fired only after the background probe had
  started. Lint the edit, then probe — the two are not independent, and the
  probe report is worthless if it measured a description that cannot ship.
- **`pytest -q` writing to a background file shows 0 bytes for six
  minutes**, which reads exactly like a hung run. It is block buffering; the
  file fills at exit. Do not re-launch on the strength of an empty output
  file ([[feedback_empty_background_output_is_not_a_finished_task]]).

## 10. Deliberate limits

- **The 90% is one draw and is reported as such.** The re-probe measured 8
  cases, not 105. A per-skill rate anyone wants to act on needs
  `--repeats 3+` on that skill, and this round did that for exactly one
  (`cri`, n=2/case). Nothing here licenses "the corpus is at 90%".
- **No canary was run**, because `canary.json`'s purpose is guarding
  cross-round comparisons and 24 of these skills had no prior report to
  compare against. The `cri` before/after IS a comparison, but within one
  round, one instrument, one session — the drift a canary detects cannot
  have happened in between. A future cross-round re-probe must run the
  canary first.
- **`--mode body` was not run for any skill.** Everything here measures
  whether a description FIRES, not whether the body is followed. 0 of 27
  skills have a body case; that is unchanged from before this round.
- **The nine new cases were written from the descriptions they test**, by
  the author of this round, which makes them easier than a real user's
  phrasing. They are labelled near/mid/far but the far ones are far
  *paraphrases of the description*, not independent tasks. Two of the three
  new skills still scored a first-draw miss on them.

## 11. The checker caught this round, twice

Two of this round's own artifacts were wrong, and the corpus's own tools —
not review — found both:

- **X004** failed `unittest discover` because §3 above cites
  `state/known-unprobed-skills.json`, which did not exist. Written rather
  than allowlisted: the file is now the schema documentation for the next
  round that has to defer a probe.
- **S004** flagged this round's own next-steps item 7 as citing "round 355's
  item 2", a pointer that resolves to nothing. Chasing it found the item was
  worse than dangling: the tail-vs-lifted transform **already is** a
  `harness/swe/` oracle (`tail_transparency`, round 337), so round 355's
  knowledge file had proposed building something that shipped 18 rounds
  earlier, and this round nearly carried the proposal forward a second time.
  That is `state_claim_check.py`'s first live catch of a claim this program
  minted during the round that ran it, rather than one inherited from a
  previous block.

Both are the round's own thesis turned on itself: the difference between a
rule that is written down and a rule that runs.

## 12. The new check's own pristine-tree limit

`.gitignore:58` is `state/trigger-eval/*.json`. The probe REPORTS this round
produced are therefore untracked by design, and `--audit` / P004 read exactly
those files. So from a fresh clone `case_coverage.py` reports **27 never
probed, 24 warnings** — round 355's pristine-checkout finding, arriving in
the check built one round later, and found by staging the commit rather than
by reasoning.

It is not a defect, because the split in §3 already put the enforcement on
the right side of the line: **P001 and P002 are the errors, and both are
computed from `skills/trigger-cases.json` and the skill directories, which
ARE tracked.** `TestLiveCorpus` asserts `rc == 0`, warnings do not set `rc`,
and the case floor is what the test is for — so the test that gives the rule
teeth passes from git alone, and only the priced-tier warning degrades. The
human-readable `.md` reports ARE committed, so the measurement itself
survives in the repo even though the machine-readable evidence for it does
not.

Recording it because the honest statement of what the check guarantees in a
pristine tree is narrower than what it prints here, and a future round
reading `27 probed` in this file must know it will not see that number on a
fresh clone.
