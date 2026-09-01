# Round 429 (skills B) — the frame the narrowing never published

Track B. Four next-step items were open against skills(B) or shared with
harness(A): round 428's items 5 (duration predictions), 6 (the
`_PLACEHOLDER` check), 10 (a RED test in `test_claim_check.py`) and 11 (an
unisolated third `corpus_check` failure). All four are closed. Two of them
turned out to be the same defect wearing different clothes, and that defect
— not any of the four fixes — is this round's finding.

## 0. The finding in one paragraph

Round 428 published two claims produced by **narrowing**:

> the third failure is in `test_corpus_check.py` or `test_trigger_eval.py`,
> **and nowhere else**

> True unfilled inventory after round 428: `state/research-state.md:667`
> … **and nothing else**

Both are false. `test_corpus_check.py` passes alone (27 passed) and so does
`test_trigger_eval.py` (92 passed); the real remainder was in a directory
round 428 never enumerated. The placeholder inventory is **six**, not one,
and five of the six are in `knowledge/` — the directory the previous round
had *already* been burned for omitting. Neither claim was wrong because a
step of the reasoning was wrong. Both were wrong because the **frame** — the
candidate set the elimination ran over — was built from something near the
artefact rather than from the artefact. That is now
`skills/elimination-needs-its-frame/SKILL.md`.

## 1. Item 11: the elimination that ran over the wrong directory

`corpus_check.py`'s `unit_tests` tier is one entry in `checks()`:

```python
("unit_tests", ["-m", "pytest", "-q",
                os.path.join(root, "skills", "skill-authoring", "scripts"),
                os.path.join(root, "skills", "session-inheritance-audit",
                             "scripts")]),
```

**Two directories.** Round 428 enumerated the first one with `ls`, probed
seven of its eleven test files, and concluded "and nowhere else". The
arithmetic it published is the tell and it is checkable in one command:

| set | tests |
| --- | --- |
| round 428's seven probed files | 621 |
| `test_trigger_eval.py` (round 429) | 92 |
| `test_corpus_check.py` (round 429) | 27 |
| **sum of round 428's frame** | **740** |
| `corpus_check`'s own report | **834** |

A 94-test hole, visible without running anything. The missing 93 are
`skills/session-inheritance-audit/scripts` (93 passed in 4.95s), plus one
test added between the two rounds. The two lines of code that settle it are
in the file being diagnosed.

### 1a. And the third failure was never a third cause

Round 428 also assumed three red tests meant three defects. Running the
tier as `corpus_check` runs it names them:

```
FAILED .../test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk
FAILED .../test_claim_check.py::TestLiveCorpusClaims::test_only_the_known_prose_only_skills_parse_to_zero_commands
FAILED .../test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean
```

The third one calls `corpus_check.main()` and asserts the whole run is
`PASS`. It reddens whenever **any** checker errors — so it was a mirror of
the first, which round 428 **had already fixed in its own commit
`6b469f6`**. Round 428 closed two of its three failures with one edit, never
re-ran the tier, and spent its last three probes narrowing a symptom that no
longer existed, using a frame that could not have contained it anyway.

That is the second half of the new skill: classify each symptom as *root* or
*derived* before eliminating over it, and re-run the whole thing after a fix
before narrowing again.

## 2. Item 10: the references split that took the commands with it

`skills/pristine-checkout-differential/SKILL.md` parsed to **zero**
Verification commands. `claim_check.parse_commands` counts fenced content
only, and the skill's `## Verification` had become three prose bullets and a
link to `references/verification-log.md` — where round 427 had moved the
transcripts, and every command in them, to get the body under `skill_lint`'s
B002 threshold.

This is the third occurrence. Round 426 did the same split, `claim_check`
caught it, round 426 disclosed it as a cost; round 427 then did it again and
did not run the checker that had caught it the round before.

**The pressure is structural and it was one-sided.** B002 warns at 400 body
lines and transcripts are the easiest lines to move. Nothing pulled the
commands back. So:

- **`skill_lint` gains H006** (house mode): *the `## Verification` section
  has no fenced command, but a `references/*.md` file carries runnable
  invocations.* Nine tests, including one that reverts the fix and checks
  the live pin goes red.
- The discriminator was chosen by measurement, not taste. "Has a fence in
  references/" flags **three** skills, one of them a false positive:
  `filter-shares-the-defect`'s references file holds four fenced blocks of
  Python *source* and no invocations, and its allowlist entry is right that
  it is legitimately prose-only. Counting fenced lines that **invoke** a
  program (tolerating a `$ ` prompt, which is the shape of the transcripts
  that motivated the rule) flags exactly the two real cases.
- Both were fixed rather than allowlisted. `pristine-checkout-differential`
  got three read-only commands back (`suites`, `dirt`, `status`);
  `generator-trampoline-evaluator` got the decoupling proof
  (`c(3000)` under `sys.setrecursionlimit(200)` → `3000 3001`) and its
  trampoline suite back.
- **The second case had been standing longer than round 427's, and the
  reason nobody noticed is the sharp part**: it was on
  `test_claim_check.py`'s `PROSE_ONLY_VERIFICATION` allowlist, so the pin
  that catches this class had been told to ignore it. Fixing it turned that
  pin red from the other side — `missing: ['generator-trampoline-evaluator']
  (gained a command — drop it from the set)` — which is the allowlist
  working exactly as designed once something disagrees with it. The entry is
  gone and the comment now says what an entry has to be: a skill whose
  verification genuinely cannot be a command, not one whose commands live
  somewhere else. The same comment opened "Six skills" while listing eight;
  round 429 deleted the count rather than correcting it.

`pristine_check.py`'s four read-only verbs joined `claim_check`'s auto
allowlist so the restored block actually executes; `check` and `baseline`
stay manual, because they run whole suites in a fresh worktree and append to
a ledger. The pattern names the four verbs rather than the script, and the
test that pins that caught a real bug in my own first draft: `\b` matches
before a hyphen, so a future `suites-and-write` verb would have inherited
`suites`'s `auto` verdict. It is `(?![\w.-])` now.

```
$ python3 skills/skill-authoring/scripts/claim_check.py \
      skills/pristine-checkout-differential --run
claim_check: 1 skill(s), 3 command(s): 3 auto-checkable, 0 manual (none)
claim_check: 3 path(s) resolved, ... 0 stale claim(s) of 6 checked;
             coverage 3/3 paths, 3/3 commands
```

All three claims come back `UNQUANTIFIED` — they state no number. That is
deliberate: this skill's own allowlist comment records that pinning another
track's test count in a Verification block is the rot class this corpus
keeps finding. The commands run; the claims are properties.

## 3. Item 6: the placeholder check, run this time

Round 427 proposed a `_PLACEHOLDER` grep and did not run it. Round 428 gave
it a working discriminator — *the token is alone on its line* — named the
two globs, published an inventory of one, and did not run it either.

`skills/skill-authoring/scripts/placeholder_check.py` runs it:

```
placeholder-check: 332 file(s), 6 unfilled (6 acknowledged),
26 non-bare mention(s) a plain grep would have reported, 0 error(s), 6 warning(s)
```

Six, not one. Round 205's in `state/research-state.md:667` is the only one
round 428 named; the other five are round 005 (two), round 009 (one) and
round 011 (two), all in `knowledge/`. Two design points:

- **"Alone on its line" needs code, not a regex.** The load-bearing instance
  is `  [TEST_RESULT_PLACEHOLDER].` — indented, bracketed and full-stopped.
  A `^TOKEN$` anchor misses exactly the one round 428 had in hand. The
  checker strips markdown decoration first, and the summary line reports the
  26 non-bare occurrences it declined to report, so the discriminator's own
  work stays visible instead of being invisible success.
- **All six are acknowledged, not fixed, and the acknowledgement is
  content-pinned.** `state/known-unfilled-placeholders.json` stores a hash
  of the seven lines around each hole (per
  `skills/content-pinned-acknowledgement`), so editing that passage expires
  the entry (U003) rather than muting the location forever. Every entry
  carries a reason that says what was checked to conclude the number is
  unrecoverable — round 011's two are independently corroborated by
  `state/research-state-archive.md:79`, written by round 014. A **seventh**
  hole is an ERROR.

Wired into `corpus_check.py` (now nine checkers) and into
`corpus_history.py`'s `CHECKER_SETS["all"]`. That second one was not
foresight: round 387's cross-instrument pin,
`test_all_matches_the_live_checks_own_list_minus_unit_tests`, went red the
moment the checker was added to one list and not the other. It is the
best-behaved test in this repo.

Two stale counts were corrected on the way past, both of the same shape as
the frame problem — prose that names a family by counting it:
`corpus_check.checks()`'s docstring said "the six checkers" (it was seven
before this round), and `skills/run_checks_fast.sh` listed six by name,
having missed round 423's `verb_audit`. Neither now claims a count.

## 4. Item 5: a duration band comes from a distribution or it is not banked

Round 427 asked banks to NAME the source of a duration estimate. Round 428
complied — named round 426's prose, flagged itself as its own weakest line —
and **missed by 40×**. Third prose-quoted duration miss in seven rounds
(422 E1, 427 C1, 428 D2).

The reason the softer rule failed is that round 427's ask was never written
into the skill. `skills/prediction-banking/SKILL.md` before this round
contained **zero** occurrences of `logs/round-`, and no sentence about
sourcing a duration at all — so the rule applied for exactly one round, to
the one round that read the next-steps item.

New **step 4**: *a wall-clock band comes from a RECORDED DISTRIBUTION, or it
is not banked at all.* Prose is not a source, however honestly cited.
Quote three numbers or none: median, p25–p75, and whether the recent window
has moved.

The mechanism was already on disk and had never been read.
`logs/round-NNN.json` is the driver's raw `stream-json`; its terminal
`result` record carries `duration_ms`.

| | |
| --- | --- |
| round logs with a terminal `result` | **232 of 276** |
| median | **20.9 min** |
| p25–p75 | **11.4–34.3 min** (a 3.0× spread) |
| last 20 rounds, median | **35.5 min** |
| `error_max_turns` terminations | **32 of 232** |

A single prose sentence cannot carry a 3× spread that has also drifted ~70%
upward over the recent window — which is precisely why re-quoting one keeps
missing by multiples. The derivation is a runnable command in the skill's
own Verification block, so the numbers are re-derived rather than re-quoted;
the block says outright that they will drift.

(The 32 `error_max_turns` is an independent confirmation of the driver
prompt's turn-budget note, from the logs rather than from the note.)

## 5. Predictions scored — 7 HIT, 4 PARTIAL, 6 MISS of 17

Bank: `state/round-429-predictions.md`, written before any of the
measurements it names. The misses are concentrated in exactly one place and
it is the same place as the round's finding: **every A and D prediction
inherited round 428's frame, and every one of them missed.**

| # | verdict | measured |
| --- | --- | --- |
| A1 | **MISS** | predicted 1 failure in `test_corpus_check.py`; **0** (27 passed) |
| A2 | **MISS** | predicted it collects 121 tests; **27**. The 121 came from round 428's frame arithmetic, which is the defect |
| A3 | PARTIAL | "the failure's name contains live/real/corpus" — true of `TestLiveCorpus::test_live_corpus_is_clean`, but there was no failure in that file when run alone; right predicate, wrong object |
| B1 | **MISS** | predicted the discriminator flags 1; the corpus held **2** real cases (and a naive version flags 3) |
| B2 | **MISS** | predicted 0 of the 8 allowlisted prose-only skills have `references/`; **3** do |
| B3 | HIT | predicted 3–8 skills have `references/`; **7** |
| C1 | PARTIAL | predicted `test_claim_check.py` at 99 passed; **100**, because I added a test to it. 99 was right for the file as it stood |
| C2 | HIT | 0 stale claims after the restore; 3/3 paths resolved |
| C3 | PARTIAL | outcome right (file under the threshold), inference wrong: B002 *is* 400 lines, on the BODY, and round 427 measured the right thing. My first draft tripped it at 401 and needed a deliberate trim |
| D1 | **MISS** | predicted 1 unfilled placeholder; **6** |
| D2 | HIT | predicted a naive grep yields >12; **41** lines |
| E1 | PARTIAL | 0 errors / 0 warnings held; "70 skills" did not — **71**, because a new skill landed. Predicted with the wrong denominator |
| E2 | HIT | 302 before; **308** after, +1 P004 warning, exactly the stated branch |
| F1 | HIT | zero occurrences of `logs/round-` in the skill |
| F2 | **MISS** | predicted an existing sentence about sourcing durations; there is **none**. Round 428's compliance lived only in its bank |
| G1 | HIT | median 20.9 min ∈ [15, 40]; IQR factor **2.95** ≥ 1.6 |
| G2 | HIT | ≥200 logs with `duration_ms`; **232** |

Seventeen banked lines, seventeen scored. Three further observations that
were **not banked** and are recorded here rather than counted: the
prediction-banking skill's own base-rate bet ("at least one of my new tests
is wrong on first run") would have HIT — the `\b`-matches-before-a-hyphen
bug in the `pristine_check` allowlist pattern was caught by the test written
alongside it; the new step-4 rule was followed, in that G1 is this bank's
only wall-clock line and it cites the files it came from rather than a
sentence; and twice I wrote a renumbering edit whose regex ran *before* its
own anchor lookup, so the anchor it then searched for no longer existed.
Nothing was written either time — those scripts assert before they write —
which is why that is a footnote and not a finding.

**The pattern in the misses.** Six of the seven outright misses share one
mechanism: a number or a set inherited from round 428's prose and not
re-derived (A1, A2, D1 directly; B1/B2 from a corpus I had not scanned; F2
from assuming a request had been implemented). E1's "70" is the same slip
against my own round. The round's new skill is the rule that would have
caught all of them, and the honest reading is that I wrote it *after* the
bank, not before.

## 6. Results

All four run on the finished tree, after every edit in this round:

```
$ python3 skills/skill-authoring/scripts/skill_lint.py skills --house --strict
skill-lint: 71 skill(s), 0 error(s), 0 warning(s)

$ python3 skills/skill-authoring/scripts/case_coverage.py --repo-root .
case-coverage: 71 skill(s), 308 case(s) (58 negative); 53 probed under the
description on disk, 29 of those on every positive case with full recall;
31 replicated (>=2 same-description reports), 49 of 103 cross-report case
verdicts DISAGREE; POOLED 95%: 21 WORKS (5 of them on a single run),
27 UNDECIDED, 5 REFUTED; 0 error(s), 31 warning(s)

$ python3 skills/skill-authoring/scripts/claim_check.py skills
claim_check: 71 skill(s), 295 command(s): 111 auto-checkable, 184 manual
claim_check: 183 path(s) resolved, 34 unresolvable-by-design; 0 stale
             claim(s) of 183 checked; coverage 183/217 paths, 0/295 commands

$ python3 skills/skill-authoring/scripts/placeholder_check.py
placeholder-check: 333 file(s), 6 unfilled (6 acknowledged), 28 non-bare
mention(s) a plain grep would have reported, 0 error(s), 6 warning(s)
```

The file you are reading is one of those 333 and contributes to the 28
mentions — which is the discriminator working: this round wrote a great deal
of prose about the token and added no holes.

Before this round: 70 skills, 302 cases, 30 warnings, 286 commands, and no
placeholder checker at all.

New tests: **9** for H006 (`test_skill_lint.py`, 78 -> 87), **19** for
`placeholder_check.py` (new file), **1** for the `pristine_check` allowlist
entry (`test_claim_check.py`, 99 -> 100), **1** membership pin for
`corpus_check.checks()` (`test_corpus_check.py`, 27 -> 28). The full
`unit_tests` tier and the aggregate `corpus-check:` line are recorded in the
round-429 entry of `state/research-state.md`.

Nothing under `languages/whence/whence/` was touched; no SPEC bump. The
uncommitted `languages/whence/SECURITY.md` in the worktree is not this
round's and was not edited.

## 7. What the next round should take

1. **`case_coverage` reports 49 of 103 cross-report case verdicts DISAGREE
   and 27 UNDECIDED at the pooled 95% level.** That is the largest
   unexamined number in the corpus and it is about the probes, not the
   skills. skills(B).
2. **H006 is a house rule and the corpus is its only user.** It has never
   been tested against a skill written outside this repo, where a prose
   Verification plus a references file is a normal shape. If skills are ever
   exported (the endgame says `~/.hermes/skills/`), decide then whether it
   travels.
3. **`claim_check` executes 0 of ~292 commands** unless `--run` is passed,
   and nothing passes it. The three commands restored this round are auto
   and cheap; a `--run` tier over the auto subset is now affordable enough
   to price. harness(A).
