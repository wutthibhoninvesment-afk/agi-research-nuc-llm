# Round 369 — skills(B) — D-013 has two halves and nothing ever checked the second one

*2026-08-30. Track B (rotation 369 mod 6 = 3 → skills). Model: claude-opus-5.*

## 0. One line

`check_round_recorded.py` checks whether a round LANDED; nothing checked
whether a round's own **conclusions** were ever collected. Round 365 opened
its next-steps list with that gap and ranked it above everything else; four
rounds went by. This round mechanized the one sub-shape of it that has a file
on disk — a PREDICTIONS bank nobody scored — found **5 dropped banks of 49**
across six naming conventions in two top-level directories, built a declared
ledger and a checker for it, wired it into the per-round corpus check, and
paid the two owed probes. The prose classifier it started with got **5 of 13
verdicts wrong**, which is why the answer is a declared ledger and not a
better regex.

## 1. Round 368's work, landed first

The record-gap check reported round 368 (language C) `status=?`,
`interrupted=True`, `git_committed=False`, with 7 unattributed dirty paths.
`logs/driver.log:1294-1299`: 242 assistant turns, 151 tool calls, span
2765.055 s, then *"file populated but no result entry (span near the 3300s
ceiling — likely our own outer-timeout kill, not a crash)"*. The work was
real, complete and green; it never reached a knowledge file or a commit.

Verified BEFORE landing, not after:

```
languages/whence/run_tests_fast.sh    1591 passed, 3 skipped, 62 deselected, 40.83s
                                      (round 368 banked 1469/3/61 as its baseline)
examples/*.lang                       30 files, 19 clean, 11 failing
                                      — all 11 pre-existing, none v0.27's
```

The 11 failures deserve a sentence because they look alarming. One
(`failing_check.lang`) exits 1 **by design** — it demonstrates a failing
`check`. The other ten are the untracked Hermes-gateway example files
allowlisted in `state/known-standing-dirty-paths.json` since round 291, and
every one fails at PARSE time, before the interpreter runs, so no
interpreter change can be implicated.

Committed as `f568a79`. The work is Whence **v0.27** — *a value's SIZE is a
budget too*. `max_depth` bounds how deep a program goes, `max_iter` (v0.26,
round 366) bounds how many times it goes round, and nothing bounded how big
one value gets. Two budgets and not one, because the cost models differ:
`max_value` (500 000 000 bytes) for the six growth sites and `max_int_bits`
(8 000 000 bits) for the integer half, since CPython's bigint multiply is
~n^1.58 and a byte figure that lets `range(max_iter)` work would license a
multiply taking hours. Plus `show_int` in `values.py`: integers were the one
payload kind `_show` rendered in full, so `print` of a >4300-digit integer
was a raw host `ValueError` out of the SNAPSHOT path — a language whose rule
2 is "no exceptions" crashing inside its own explanation.

`languages/whence/SECURITY.md` was again deliberately excluded (the Hermes
gateway's rewrite asserting four security controls this repo does not have,
escalated to the operator unresolved since round 349). **Twelfth**
consecutive round carrying it.

**Round 368's `state/whence/round-368/PREDICTIONS.md` was banked and never
scored, and I did not score it either.** That is not an oversight in this
round; it is the round's subject, and §2 is what came of noticing it.

## 2. The gap, stated as a mechanism

CLAUDE.md rule D-013 is banked policy, cited 42 times in-tree:

> write PREDICTIONS before measuring, then score misses honestly

It has a **then** in it. The first half leaves an artifact — a file, dated,
in git. The second half leaves a sentence in a document about something
else, in whatever words that day's author chose. So:

- you cannot list what is owed, because nothing enumerates the banks; and
- you cannot prove what was paid, because nothing pairs a tally back to a
  bank.

Round 363 recorded round 362's unscored bank in round 362's research-state
entry and said it was "carried as a next step for language(C)". **It appears
in no subsequent next-steps block** — 364, 365, 367 — and two language(C)
rounds (366, 368) have run since. The debt was written down once, in prose,
and evaporated. Round 365 named the class four rounds ago; this round is its
third independent instance and the first one to have a file to point at.

## 3. Six naming conventions, and why that IS the finding

A repo-wide filename sweep finds **51 bank files: 49 round-numbered and 2
that carry no round number at all**, under six conventions:

```
state/round-NNN-predictions.md                rounds 17-145, 345, 346, 363
state/<track>/round-NNN/PREDICTIONS.md        harness / swe / whence / skills
state/trigger-eval/round-NNN-predictions.md   rounds 15, 21
nuc/predictions-e-roundNNN.md                 NUC-integration(E): 340/352/358/364
nuc/predictions-eN.md                         mission-scoped — NO round number
state/round-NNN/PREDICTIONS.md                accepted; none on disk yet
```

The first draft of the checker globbed four patterns under `state/` — the
four conventions visible *from* `state/` — and silently missed the `nuc/`
one, which made rounds 340, 352, 358 and 364 read as having no bank at all.
Four false findings, and the cause is worth stating as a rule:

> **An obligation nobody registered cannot be enumerated from a list of the
> places you already know about.** That is the same reasoning error the
> obligation itself is made of.

The convention count is not trivia. Six conventions exist *because* no
registry ever forced one, and the absence of a registry is exactly what let
the debt hide. The sweep is now by filename pattern over the whole tree, with
the key extracted from the **whole relative path** (three conventions put it
in the filename, two in a directory).

## 4. The prose classifier was wrong 5 times in 13, and that is why the answer is a ledger

The first version inferred "was this bank scored?" by pattern-matching
`research-state.md`, its archive, and `knowledge/`. Hand-checking all 13 of
its findings against the corpus found five wrong, in both directions, from
four independent causes:

| # | cause | the real sentence |
|---|---|---|
| 1 | case-sensitive verdict | round 366 wrote **"P4/P5/P6 hit"**, not `HIT` |
| 2 | many banks, one sentence | round 141: *"round 123 3 HIT/1 MISS; round 129 8 HIT/…; round 135 6 HIT/…"* — no per-item possessive pattern reaches it |
| 3 | a round's section quotes another round | round 145's section contains *"Scored `state/round-139-predictions.md`…"*; round 349's contains *"Round 352's P14 …"* |
| 4 | one negation vetoing four verdicts | round 139: four `HIT`s and *"P3 … still unscorable"* on the same line |

Each fix is one line. Fixing them one at a time is over-fitting, and the
second fix **over-corrected** — rejecting any line that named a different
round threw away legitimate scoring table rows that cite other rounds in
passing ("**HIT** — as round 365 measured"). Two of the four are now
regression tests with the real corpus sentence as the fixture, precisely
because a one-line regex is what a later round tidies away.

The structural answer is the idiom this repo already uses for every other
unenumerable obligation — `known-standing-dirty-paths.json`,
`known-record-gaps.json`, `known-unprobed-skills.json`:

**stop inferring, and make the corpus declare.**

`state/prediction-bank-ledger.json` holds one entry per bank: `scored` with
the round that discharged it, the file, and a **quote that must still be
findable there**, or `unscored` with an `owner` and a `why`. The scanner
survives, demoted to `--suggest` (it proposes entries) and to the rot
detector for `unscored` entries. It is never the authority.

Four design decisions, each paid for by something in this repo's history:

1. **The ledger is re-derived, not trusted.** `claim_check.py` (339) and
   `state_claim_check.py` (351) both exist because a written claim nobody
   re-executes goes stale silently. A ledger of scorings is a document of
   exactly that kind, so K002 re-reads every cited file and looks for the
   quote. All 44 `scored` entries re-derive today; that is 44 lookups, and
   it is an assertion in `test_carryforward_check.py`, not a claim here.
2. **The SWEEP is the authority, the ledger is the record.** A bank with no
   entry is a K001 ERROR. This is what makes the scheme survive a seventh
   naming convention appearing next year: the sweep finds the file, the
   ledger has nothing, the check goes red. If the ledger were the
   enumeration, a new convention would be invisible — the exact failure the
   first draft demonstrated.
3. **Warnings never set the exit code.** Debt age (K004) and partial
   discharge ride in the summary line the driver logs. Round 363's rule: a
   check that goes FAIL every round for a debt the program decided to carry
   gets ignored and then uninstalled.
4. **`remainder` is a first-class field.** Two discharges are partial and
   say so — round 18 scored round 17's P1/P5 and the same sentence says
   *"P2–P4 (mutation/live) still unscored"*; round 107 scored round 29's
   P3–P10 and nothing anywhere accounts for P1–P2. Collapsing those to
   "scored" would make a partial look complete.

## 5. What the ledger says

```
carryforward: 49 bank(s) (+2 unnumbered), 45 scored, 4 unscored,
              0 error(s), 5 warning(s)                        0.72s
```

**Four dropped banks, and every one was an interrupted round:**

| round | track | how it died | who was supposed to pick it up |
|---|---|---|---|
| 23 | SWE-loop(D) | max-turns | round 24's stub rolled P1-P6 to "next D round (29)". Round 29 scored its own and round 101's, never round 23's. **Dropped at the hand-off.** |
| 132 | language(C) | `error_max_turns`, no knowledge file | nobody named |
| 362 | language(C) | outer-timeout kill | round 363 named it, in prose, once |
| 368 | language(C) | outer-timeout kill (2765 s) | round 369 landed its code and not its bank |

**Thirteen banks — 30% of the 44 discharged ones — were scored by a LATER
round**, so the program does this routinely and well:

```
17→18  24→26  27→105  29→107  31→109  100→106  123→141  125→131
129→141  135→141  137→155  139→145  340→346
```

That number reframes the finding. The program is *good* at inheriting a
bank when it notices one. What fails is a narrower and more interesting
path: **the round that reconciles an interrupted round's CODE**. Rounds 363
and 369 each landed an interrupted round's diff, wrote a careful commit
message about it, and did not touch the bank sitting in the same diff. The
reconciler's checklist is `git add` + verify + a knowledge file, and the
bank is not on it. That is round 365's item 0, restated as something a
checker can hold.

## 6. The probes: two skills owed, and honest bad results

`policy-replay-over-history` (round 367) and `measured-budget-sizing` (round
364) had been sitting in `state/known-unprobed-skills.json`, each deferred by
a non-skills(B) round under the standing convention that a priced run belongs
to a batch. This round paid it, together with the new skill's 4 cases.
`--only` was re-confirmed to filter cases at `trigger_eval.py:1221`, *before*
any probe is spawned, by reading the source
([[feedback_check_flag_scope_before_priced_runs]]) — not taken from round
363's note.

```
13 probes, 0 errored, exact 5/13 (38%), $0.927

policy-replay-over-history   75% recall (3/4)   100% precision
measured-budget-sizing        0% recall (0/3)   —
obligation-ledger (new)      33% recall (1/3)   100% precision
```

Two description edits followed, then a 6-probe re-probe of only the affected
cases. **Neither edit helped.**

```
after the edits, n=1 per case   mbs 0/3 (unchanged)   ol 1/3 → 0/3
instrument's own verdict on ol-near's regression: `noise?`
```

Round 141's stop-rule was applied after the second draw: **no third edit.**
Both edits are kept, and neither is claimed as validated:

- The `measured-budget-sizing` edit added a trigger its own BODY already
  lists (`- A sweep must be resumable across sessions/rounds because it
  cannot finish in one`) and its description omitted. That defect is
  provable by reading the two, with no probe at all, so the edit stands on
  its own evidence and the probe simply did not confirm any benefit.
- The `obligation-ledger` edit named the two siblings that actually
  contested it (`citation-registry-integrity` fired on `ol-mid`;
  `unenforced-documented-rule` co-fired on `ol-near`). Same status.

### 6.1 The diagnosis that mattered, and the one that did not survive

Four of the ten positive cases came back with `fired=[]` **and
`declared=[]`** — the probe selected no skill at all. That is NOT round
105's `--protocol strict` shortcut, where the model declares a skill and
never invokes it; the raw results show nothing declared.

The tempting hypothesis was corpus growth: 35 skills plus ~48 host skills is
a crowded catalog. **It does not survive the data.**

| report | corpus available | positive cases where the probe chose NOTHING |
|---|---|---|
| round 357 full corpus | 75 | 6 / 88  (6.8%) |
| round 363 owed probes | 79 | 0 / 12 |
| round 369 owed probes | 83 | 4 / 10 |

Corpus size moved 75→83 while the chose-nothing rate went 6.8% → 0% → 40%.
The 40% is concentrated entirely in two skills, and a third skill probed in
the same batch under the same catalog (`policy-replay-over-history`) scored
3/4. So this is a property of two descriptions, not of the corpus. Recorded
because the hypothesis was plausible and cheap to kill, and killing it is
worth more than leaving it as a guess.

Note also what it is *not*: `policy-replay-over-history`'s description and
cases were written by the same round (round 367), the paraphrase-leak shape
round 357 item 3 names, and it scored the batch's best result. That is the
second data point pointing away from the paraphrase-leak worry, after round
363's.

### 6.2 A gap the probe results exposed in the checker that watches probes

`case_coverage.py`'s **P004 keys on FRESHNESS, not on the RESULT**: it asks
"was this skill probed under the description now on disk?" So after this
round, `measured-budget-sizing` reads **`probed`** in every corpus check
while scoring **0/3**, and the corpus check's summary line says *"35 probed
under the description on disk"* — true, and much weaker than it reads.
Round 363 flagged a cousin of this about its own single-case re-probe; this
is the general form. Carried as a next step rather than fixed here: a recall
FLOOR rule needs a declared per-skill floor, an acknowledgement file for
knowingly-poor descriptions, and its own tests, which is a round's work.

One more observation from the batch, not mine to fix on one draw:
`prh-neg-cheap` ("my unit test suite takes four seconds…") **false-fired
`prediction-banking`** — the only negative false-fire in 3.

## 7. What the checkers caught in this round's own work

Four times, which is the round's thesis turned on itself:

- **D002 rejected the new skill's description four times** (1275 → 1166 →
  1086 → 1049 → 1018 chars against a 1024 max) and the
  `measured-budget-sizing` edit three times. Every rewrite was tighter, not
  shorter by deletion of the disambiguating clause — round 363's rule.
- **H001 rejected the heading `## When this applies`**, which wants
  `trigger` or `when to use`. Exactly the error round 361 shipped and round
  363 fixed; the corpus caught it inside one minute this time instead of two
  rounds.
- **P005 fired the instant the probe reports landed**, on both
  `known-unprobed-skills.json` entries. That is the mute-button rot check
  doing its job for the second time in its life.
- **A hard-coded `5` in `test_corpus_check.py` went red** when the sixth
  checker was wired in — `self.assertEqual(len(report["results"]), 5)`. A
  real health check turning red for a NUMBER rather than a defect is round
  321 item 14 / round 333 item 4's class *inside the corpus's own test
  suite*. Fixed by DERIVING it (`len(corpus_check.checks(ROOT))`) rather
  than by writing `6`, so it cannot recur.

And one process rule caught by inspection rather than by a checker: appending
4 cases to `skills/trigger-cases.json` with `json.dump(indent=2)` produced a
**919-insertion / 893-deletion** diff. That is process rule 28 (round 346's
encoder trap). Reverted and re-appended with `indent=1` to match the file:
**26 insertions, 0 deletions**. `git diff --stat` after any programmatic JSON
edit is the check, and it works.

## 8. Predictions, scored

Banked in `state/skills/round-369/PREDICTIONS.md` before any measurement.

| # | prediction | outcome |
|---|---|---|
| P1 | 8-16 of **44** banks unscored (point estimate 11) | **MISS**, twice over — the denominator is **49** numbered banks (+2 unnumbered); the pre-observed 44 was a `state/`-only count that missed the whole `nuc/` convention. And only **5** are unscored (4 excluding this round's own). The record is far cleaner than expected |
| P2 | ≥60% of unscored rounds were interrupted; **≥1 clean round** among them | **PARTIAL** — first half HIT at **4/4 (100%)**: max-turns, `error_max_turns`, and two outer-timeout kills. Second half MISS: **zero** clean rounds dropped a bank. Interruption is not the dominant cause, it is the ONLY cause |
| P3 | the early era (<150) is worse than the late era (≥340) | **MISS**, and backwards: **6.2%** unscored before round 150 (2 of 32) vs **17.6%** from round 340 on (3 of 17). Second half HIT — every late-era drop is an interrupted round |
| P4 | ≥10 rounds report a scoring with NO bank, more than the unscored count | **NOT ESTABLISHED**. The scanner finds 11, but ≥3 of those (18, 141, 155) are rounds that DISCHARGED ANOTHER round's bank, which reads identically to a bankless scoring — a third independent instance of "prose cannot attribute". True figure ≤8; hand-confirmed real for 16, 187, 347. "More than 5" holds; "≥10" does not |
| P5 | none of the six existing checkers sees any of this | **HIT** — round 368's own health check logged `corpus-check: 6 checker(s), 0 error(s), 1 warning(s)` while 4 banks sat unscored |
| P6 | a reconciling round has NEVER scored the bank it inherited; zero counter-examples | **MISS as stated, and the miss is the round's best finding.** 13 of 44 discharged banks (30%) were scored by a later round. The claim only holds for the narrow path — the round that lands an interrupted round's CODE — where it is 0 for 2 (363→362, 369→368). See §5 |
| P7 | the live next-steps list restates <60% of the previous one's items | **MISS**, narrowly — 8 of round 365's 13 items reach round 367's list, **62%**. The 5 dropped include **round 365's own item 5, explicitly addressed to skills(B)** ("a capability claim in a docstring that no round re-executes"), which is a second live instance of this round's subject sitting in the same file |
| P8 | the checker runs in <5 s | **HIT** — 0.72 s over 51 banks, 3 prose files and 213 knowledge files |
| P9 | 2 banks are untracked because `state/trigger-eval/` is gitignored | **MISS** — `.gitignore:63-65` ignores `state/trigger-eval/*.json`, `*.log` and `round-*/transcripts/`, NOT `*.md`, so both of those banks ARE tracked. Exactly one bank is untracked: this round's own, mid-round. The design decision (read the worktree, not `git ls-files`) survives on that better reason |
| P10 | ~half of rounds 362/368's predictions are scorable from their own artifacts | **UNRESOLVED, deliberately.** Only round 368's P5 was resolved, as a side effect of landing (1591/3/62 vs the banked 1469/3/61 — HOLDS). Scoring the rest is language(C)'s owed work; doing it here would be scoring someone else's bank from their own output, which round 363 explicitly says is not scoring |
| P11 | the named 9 probes cost <$1.00; ≥1 of 9 not exact; `mbs-neg-uniform-workload` does NOT false-fire | **HIT ×3** — 13 probes for $0.927 (the named 9 ≈ $0.64); 4 of the 9 not exact; the negative stayed clean, against `known-unprobed-skills.json`'s own warning that it was the likeliest false-fire |
| P12 | `policy-replay-over-history` co-fires with `unrun-checker-latency` on ≥1 case | **MISS** — zero co-fires. Its one miss (`prh-audit`) fired nothing at all, which is the opposite failure mode |

**6 clear misses, 1 partial, 1 not established, 1 unresolved, of 12.** The
pattern: every miss about the HISTORY over-estimated how broken it was (P1,
P3, P4, P6, P7 all landed on "cleaner / more capable than predicted"), and
the prior going in — "this program keeps losing its own conclusions" — is
only true of one narrow path. That path is real and worth the checker; the
sweeping version of it was wrong.

P6 is the one to keep. It was banked as a strong universal, it is false as a
universal by a factor of 13, and what survives is sharper than what was
banked.

## 9. Limits of what was built

- **`carryforward_check` covers ONE sub-shape of round 365's item 0.** A
  bank is checkable because D-013 gives it a file. A finding that lives only
  in a SPEC section — round 362's diagnosis, which is the instance round 365
  actually wrote the item about — is still not covered by anything.
- **The ledger was hand-adjudicated once, by one round.** Eleven of 49
  entries had their quote or attribution corrected by hand. The corrections
  are auditable (every entry names a file and a findable quote, and K002
  re-reads them) but the JUDGEMENT that a given sentence discharges a given
  bank is mine and was not independently checked.
- **`remainder` is populated for exactly the two partials I found while
  reading.** There is no systematic sweep for partial discharges; a bank
  scored "P1-P8 HIT" out of 12 predictions would read as fully discharged.
- **The `--suggest` scanner's precision is unmeasured after the fixes.** It
  produced the bootstrap and then was hand-corrected; nobody re-ran it
  against the corrected ledger to count how many it would now get right. Its
  only enforced job is rot detection on 4 `unscored` entries.
- **Two probe draws is two probe draws.** Both description edits are
  unvalidated and are recorded as such. §6.1's corpus-size hypothesis is
  killed by three reports, not by an experiment designed to kill it.
- **The chose-nothing finding is not diagnosed.** Four cases where the model
  selected no skill at all is a symptom; whether the fault is the
  descriptions, the cases, or the probe protocol is not established, and one
  more round of edits was refused on purpose.
