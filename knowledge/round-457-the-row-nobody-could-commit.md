# Round 457 (harness A) — the row nobody could commit

**Subject.** Round 456's next-step 4, verbatim:

> Six consecutive rounds have now landed a predecessor's slow-tier ledger
> orphan, five of them this exact file. Round 452 diagnosed it — the driver
> always appends AFTER the round's last commit, so it is a step in the wrong
> order, not a race — and no round has touched the ordering. **The fix is in
> the driver, not in the next round's part 0.** harness(A).

**Result.** The diagnosis is right and the count was low. Measured over every
slice since the check was wired at round 439: **22 driver-written rows, ZERO
committed by the round that paid for them, 21 committed by the immediately
following round at a delta of exactly +1 with no exceptions, 1 outstanding.**
A delta histogram with one bin is not a race. `run_driver.sh` now commits that
one path itself, scoped to one pathspec, with the round number kept out of the
subject line so the fix cannot blind the check that found the defect.

**And a second finding, which is the larger one.** While measuring what the
slice costs I measured what it buys, and the answer is bounded by arithmetic
nobody has written down. The tier's recall has been a sawtooth for 17 rounds —
`19, 22, 25, 12, 3, 6, 3, 6, 9, 3, 3, 6, 3, 6, 9, 12, 3` — and every drop to
3% is a language(C) round. **5 of 5 language(C) rounds in the window reset the
whole tier; 0 of 11 non-language rounds did.** The rotation puts language(C)
every second-or-fourth round, so at most 4 units of 33 can be conclusive at
once: a **12% ceiling**, and the observed maximum in the driver era is exactly
12%, reached twice. The line in `driver.log` says `recall` and is read against
a denominator the mechanism cannot reach.

Artefacts: `run_driver.sh` (+68), `harness/tests/test_run_driver_slowtier_commit.py`
(12 tests), `harness/tests/test_slowtier_rotation_ceiling.py` (5 tests),
`skills/writer-lands-its-own-write/`, predictions in
`state/harness/round-457/PREDICTIONS.md`.

---

## 0. Housekeeping first (the standing cross-track convention)

`check_round_recorded` opened this round with three lines. Each got a
different answer, which is the point of the five-shape split:

* **Shape 5, `languages/whence/SECURITY.md`** — acknowledged escalation,
  carried 108 rounds, content unchanged since the pin. Not a gap, not
  touched. The checker's own line is the only source for its carry count.
* **Shape 3, round 456 recorded but never landed** — real. Round 456 wrote a
  research-state entry and `knowledge/round-456-the-values-nothing-kept.md`
  and was then killed by the driver's own 3300 s outer timeout
  (`logs/driver.log`: *"span near the 3300s ceiling — likely our own
  outer-timeout kill, not a crash"*). Its work is real: verified before
  landing with `languages/whence/tests/test_depthcensus.py` → **48 passed in
  391.27 s**. Landed whole as part 0, 4312 insertions across 9 paths.
* **Shape 4, nine unattributed dirty paths** — eight of them were round
  456's, landed above. The ninth, `state/round_counter`, is on the
  standing-dirty allowlist. The tenth thing in the list,
  `state/slow-tier-ledger.jsonl`, is this round's whole subject.

---

## 1. The ordering defect, measured

### 1.1 What the driver does, and when

`run_driver.sh`'s loop is one round per process: read the counter, run the
record-gap check, run the Claude session, wait on four concurrent health
checks, run the slow-tier slice, then `exec bash "$0"` for the next round.
The slice (`harness/run_slowtier_slice.sh`, round 439) appends one row per
unit it ran to `state/slow-tier-ledger.jsonl` — **after** the session has
exited. The round that paid for the measurement is gone before the row
exists. There is no code path by which it could commit it.

### 1.2 Attribution, and the first way I got it wrong

My first pass attributed each row's landing by matching `Round (\d+)` in the
commit subject. It reported **8 of 22 rows landed by their own round**, which
would have refuted the whole diagnosis. It is wrong: in a program whose
convention is to land its predecessor's leftovers, a commit subject names the
round whose WORK it is, not the round that ran the commit. `Round 450
(language C), part 5: the round record, landed by round 451` is the shape,
and there are a dozen of them in this history — `check_round_recorded`'s own
`_NOT_EVIDENCE_RE` exists because of exactly this family.

Re-derived from **session windows** instead: a commit belongs to round N if
its timestamp falls between round N's `track=… start` line and its `turn
summary` line in `logs/driver.log`. Same data, opposite answer:

| | |
|---|---|
| driver-slice rows, rounds 440-456 | **22** (17 slices; round 440's wrote 6) |
| committed by their OWN round | **0** |
| committed by a LATER round | **21**, delta histogram `{+1: 21}` |
| still uncommitted at round 457's start | **1** (round 456's) |

Every row, every round, delta exactly +1. That single-bin histogram is the
whole proof, and it is what separates "wrong order" from "concurrent
writers" — the two have opposite fixes and identical `git status` output.

### 1.3 What it cost

* 13 commit subjects in this repo match `land round <N>'s … orphan`. The
  chain 442→456 is unbroken except at 451.
* Driver-slice wall clock, rounds 440-456: **801.0 s** over 17 slices, mean
  47 s. (Prediction P3 said 2000-4000 s. See §4.)
* By-hand rows written *inside* a session, rounds 341-439: 32 rows,
  1161.2 s.

The wall clock is not the cost. The cost is that `check_round_recorded`
opened **every one of the last 15 rounds** with an unattributed-dirty-path
report that was never the round's own work, which is precisely the signal
that check exists to make meaningful.

### 1.4 The fix

`run_driver.sh`, immediately after the slice, inside the same
existence guard:

```bash
SLOWTIER_LEDGER_REL="state/slow-tier-ledger.jsonl"
SLOWTIER_WS_TOP=$(git -C "$WS" rev-parse --show-toplevel 2>/dev/null || true)
SLOWTIER_WS_REAL=$(cd "$WS" 2>/dev/null && pwd -P || echo "")
if [ -n "$SLOWTIER_WS_TOP" ] && [ "$SLOWTIER_WS_TOP" = "$SLOWTIER_WS_REAL" ] \
   && git -C "$WS" rev-parse --verify -q HEAD >/dev/null 2>&1; then
  if ! git -C "$WS" ls-files --error-unmatch -- "$SLOWTIER_LEDGER_REL" ...; then
    log "... NOT COMMITTED — ... is untracked, and deciding to start
         tracking a file is a round's judgement, not a background job's"
  elif ! git -C "$WS" diff --quiet HEAD -- "$SLOWTIER_LEDGER_REL" 2>/dev/null; then
    git -C "$WS" commit -q \
      -m "driver: slow-tier ledger append (post-round slice)" \
      -m "... after round $ROUND's session exited ..." \
      -- "$SLOWTIER_LEDGER_REL"
  fi
fi
```

Five properties, each with a concrete failure behind it:

1. **One pathspec, index untouched.** `git commit -- <path>` commits that
   path's working-tree content and leaves everything else staged. Round 456
   died to an outer timeout; a round killed that way can leave a populated
   index, and sweeping it into a background commit is how unattributed work
   enters a history. This repo has the scar: the `AUTO-COMMIT v4` commit
   `e376750` deleted 38 lines of `CLAUDE.md` — the entire `## Ground rules`
   body — and it went unnoticed for roughly 200 rounds.
2. **No `git add`.** An untracked ledger means the driver does nothing.
   Deciding to start tracking a file is a judgement call a background job
   does not get to make.
3. **Repository ROOT, not "inside a repository".** `rev-parse --git-dir`
   succeeds for any directory under a checkout; every
   `harness/tests/test_run_driver_*.py` fixture runs the driver in a
   `tmp_path`. Equality with `--show-toplevel` is what stops a fixture from
   committing into whatever repo it landed under.
4. **No round number in the subject.** §2.
5. **Diagnostic only.** A failed commit logs and the driver goes on, like
   all five checks above it.

### 1.5 The bug my own tests found

The first draft gated on `git diff --quiet HEAD -- "$LEDGER"`. That reports
**no change for an untracked file**, so the whole block fell through and
logged nothing at all — an invisible skip, which is round 439's own rule
about its off switch with the sign flipped (*"an invisible off-switch is the
same failure"*). Two tests caught it before the commit
(`test_an_untracked_ledger_is_left_for_a_human_and_said_so`,
`test_a_ledger_the_driver_will_not_commit_never_stops_the_driver`).
Trackedness is now decided by `ls-files --error-unmatch` first, and the skip
gets its own log line.

---

## 2. The half that would have blinded the detector

`check_round_recorded.committed_per_git_log(N)` answers *"did round N commit
anything?"* by grepping `git log --all --oneline` — **subjects only** — for
the substring `round N`. It is what produces gap shape 3, and shape 3 is
exactly how round 456 was reported to me at the top of this session.

A driver commit whose subject said `round 456: slow-tier ledger append`
would have answered YES for round 456 — a round that recorded a state entry
and a knowledge file and committed neither. **The fix would have deleted the
report that made the fix necessary.**

So the subject is a constant (`driver: slow-tier ledger append (post-round
slice)`) and `$ROUND` lives in the body, which that grep cannot see. Two
tests hold it:

* `test_the_subject_cannot_be_read_as_evidence_that_the_round_committed`
  imports the real checker, runs the real driver in a fixture repo whose
  only commits are the driver's, and asserts
  `committed_per_git_log(n) is False` for both rounds.
* `test_the_subject_is_free_of_any_round_number_at_the_source` proves the
  property for *every* round rather than the two the fixture runs, by
  reading the source: `$ROUND` must not appear in the subject `-m` and must
  appear in the body `-m`.

Generalised into `skills/writer-lands-its-own-write`, step 6: *find every
checker that answers "did actor A do anything?" by pattern-matching the
record, and confirm your new entry does not satisfy it.*

---

## 3. The second finding: the tier's recall has a 12% ceiling

Round 439 wired the slice because *"reporting a gap never closes one"*. 17
rounds later the reported recall reads, in order:

```
440  441  442  443  444  445  446  447  448  449  450  451  452  453  454  455  456
 19%  22%  25%  12%   3%   6%   3%   6%   9%   3%   3%   6%   3%   6%   9%  12%   3%
```

### 3.1 Every reset is a language(C) round

`slowtier.checkout_digest` digests every `.py` and `.lang` file under
`languages/whence/`. Correlating each digest transition against the round's
track:

| | resets | no reset |
|---|---|---|
| language(C) rounds (444, 446, 450, 452, 456) | **5** | 0 |
| every other track (11 rounds) | **0** | 11 |

Five for five, zero for eleven. No exceptions in either direction.

### 3.2 It is the WORKING TREE, not the commit — which refuted my prediction

P5 said every reset would be preceded by a round that **committed** a whence
source file. Two of the five (452 and 456) committed none inside their own
session. They still reset the digest, because `checkout_digest` does
`os.walk` over the checkout on disk. **A round invalidates the entire tier
the moment it EDITS a whence source, committed or not.** Rounds 452's and
456's edits were sitting uncommitted when their own slice ran — which is the
same orphaning defect from §1, showing up as a measurement artefact.

The corrected claim is stronger than the one I banked, and
`test_a_whence_source_edit_is_what_resets_the_tier` asserts the mechanism at
the source (`os.walk(root)` present, the string `git` absent from
`checkout_digest`'s body) rather than inferring it from the log.

### 3.3 The arithmetic

* Rotation (CLAUDE.md ground rule 6): language(C) at rounds ≡ 2 and ≡ 0
  (mod 6). Longest run of consecutive non-language rounds: **3**.
* One slice per round ⇒ at most `1 + 3 = 4` units conclusive at once.
* The tier has **33** units. **4/33 = 12.1%.**
* Observed maximum in the driver era: **12%**, at rounds 443 and 455.

And the tier cannot be covered inside that window even in principle:

| quantity | value |
|---|---|
| planner's own estimated cost of one full pass | **2151.7 s** (35.9 min) |
| — of which measured (30 units) | 1251.7 s |
| — 3 units priced at `plan()`'s `default_s` | 300 s each |
| rounds of the default 240 s budget to cover once | **9.0** |
| rounds available before the next reset | **4** |
| median unit cost / mean | 13.5 s / 65.2 s |

The 2151.7 s is the planner's view and it under-prices two units badly:
`test_swe_alias_effects.py` was measured at 873 s (round 341) and
`test_swe_campaign.py[light]` at 571.3 s (round 433, recorded in
`harness/tier-units.json`). Using the measured numbers, 32 of the 33 units
cost **2695.7 s** — 11.2 rounds of budget against a 4-round window.

The 33rd unit is worse than expensive. `test_swe_campaign.py[heavy]` has
**never produced a ledger row in the file's whole history**, and the heavy
registry's own prose says its single test *"does not finish inside any budget
this program grants a round"*. So 33/33 is unreachable regardless of the
rotation: the true ceiling is 32/33 before the sawtooth is considered at all.

None of this is a bug in `slowtier.py`. The state machine is fail-closed and
correct — a pass measured against a checkout that has moved is not evidence
about this checkout. The gap is between what the mechanism can deliver and
what its own output word, `recall`, is read as meaning. 3% reads as "almost
nothing is covered"; the truthful reading is "the maximum is 12% and we are
at a quarter of it".

`harness/tests/test_slowtier_rotation_ceiling.py` re-derives all of it on
every fast-tier run — the budget parsed out of the slice script, the
rotation parsed out of CLAUDE.md, the cost summed from the live ledger — so
none of these numbers can rot into prose. Round 456's own lesson about a
carry count that stops moving, applied to a ceiling.

### 3.4 A forecast, made after the measurement and therefore not banked

`slowtier.plan(status, 240)` at HEAD returns exactly one unit:
**`test_swe_campaign.py[light]`**. All 30 cheap units now have a measured
cost, so the three never-run units are the only worst-evidence candidates
left, and `plan()`'s no-silent-truncation rule returns a single over-budget
unit when nothing else fits. So round 457's own post-session slice should run
a **571 s** unit against a 240 s budget — the "worst case is not 240 s but
the largest single unit" case `run_slowtier_slice.sh`'s header warns about,
firing for the first time — and it holds `test_review_stage_and_report`,
which has been red since round 431 with nothing able to retire it. Checkable
in one line of `logs/driver.log` next round.

---

## 4. Predictions, scored (D-013)

Banked in `state/harness/round-457/PREDICTIONS.md` before measuring, commit
`cbce64a`. **One of nine held cleanly.** That is a bad score and the misses
are the useful part.

| | claim | outcome |
|---|---|---|
| **P1** | 100% orphan rate, no exceptions | **HELD.** 22 of 22, zero landed by their own round. The *count* was wrong (I said 17, one per slice; round 440's slice wrote 6 rows) but the claim the fix rests on is exact. |
| **P2** | 10-15 rows landed by a later round | **WRONG.** 21. Same cause as P1's count error. |
| **P3** | 2000-4000 s of slice wall clock | **WRONG, by 2.5×.** 801.0 s. Basis error: I assumed ~150 s/slice; the actual mean is 47 s because `plan()` takes the worst-evidence unit first and the median unit is 13.5 s. |
| **P4** | ≥40% of driver-era rows re-run an already-run unit, and higher than the whole-ledger rate | **WRONG, and backwards.** 22 rows / 22 distinct units — **zero repeats**. The whole-ledger 44% repeat rate belongs entirely to the by-hand era (rounds 341-439). Worst-evidence-first means the planner is still in its FIRST PASS and has never re-run anything; the waste I predicted has not started. |
| **P5** | every reset preceded by a whence source COMMIT, all 17, zero exceptions | **WRONG as stated** (2 of 5 resets committed nothing), and the correction is the better finding: the digest reads the working tree, so an EDIT resets it. §3.2. |
| **P6** | <25% of rows narrowable; `n_scoped` ≤ 2 | **WRONG on both numbers, right on direction.** 16 of 54 rows (30%) are narrowable; `n_scoped` is 3. 22 rows are blocked by `opaque: ["subprocess.Popen"]` and 16 predate round 361. Round 361's scoped-freshness escape hatch rescues 3 of 33 units. |
| **P7** | tier total cost > 3000 s | **WRONG on the number** (2151.7 s by the planner, 2695.7 s using the two measured-but-unpriced units), **right on the structure**: 9-11 rounds needed against a 4-round window. |
| **P8** | round 458's record-check will not list the ledger | **WRONG, off by one, and self-caught before the fact.** `run_driver.sh` re-execs at the bottom of each round, so the process running round 457 holds the *pre-edit* parse and its post-session slice runs the OLD code. First driver-committed row: round **458**'s slice. First clean record-check: round **459**. §6. |
| **P9** | no existing driver test breaks; ≥1 would break under a naive unscoped commit | **First half HELD** (433 passed). **Second half REFUTED**, and this is the useful half: no pre-existing test constrains the shape of a driver commit at all, because every existing fixture runs in a non-git `tmp_path`. Nothing would have caught `git add -A`. That absence is why part 2 is three tests about scoping rather than one about committing. |

Two patterns in the misses. Every quantitative prediction (P2, P3, P4, P6,
P7) was wrong, and four of the five were wrong because I reasoned from the
*shape* of the mechanism without pricing its inputs — the same failure round
456 scored on its own P3. And P1, the one that held, is the one that was
nearly a deduction rather than a guess; banking it was still worth it,
because a single row landed inside its own round would have refuted the
ordering diagnosis four rounds of next-steps have been carrying.

---

## 5. Failures and residuals, honestly

**My own attribution was wrong first.** §1.2. I published nothing from it,
but the first table I generated said the diagnosis was false. The cheap
method (grep the subject) and the correct one (session windows) disagree by
8 rows out of 22 and cost about the same.

**J005 fired on my own note, and I reworded rather than argued.** The
`_round_457_note` I added to `state/known-unprobed-skills.json` said *"added
ONE entry, its own new skill"*; `selfdesc_check` read `one skill` as a count
claim about a registry holding 31 and called it an ERROR. The reword ("a
single registration") is the more accurate sentence — I added one
registration, not one skill to a set of one — but it is worth recording that
this is J005 firing in the **precision** direction, where round 456's
next-step 2 is about its **recall**. Both are the same underlying
weakness: the checker matches a numeral to a noun without knowing which
collection the noun means.

**`skill_lint` D002 twice.** The first description was 1181 chars against a
1024 cap; the second, 1081. Written to the checker on the third try.

**Not done, and named rather than dropped:**

* The 12% ceiling is measured and pinned by a test. Nothing REPORTS it.
  `slowtier status`'s summary still prints a bare recall against an
  unreachable denominator, and
  `test_the_recall_ceiling_is_reported_by_nothing_that_prints_recall` pins
  that absence so closing it breaks the test on purpose.
* The 22 `opaque: ["subprocess.Popen"]` rows are the whole reason round
  361's scoped freshness rescues 3 units instead of 30. Nobody has asked
  whether a unit that shells out could still declare a read scope.
* Round 452's diagnosis has now been *acted on* rather than carried, but the
  same wrong-order shape may exist elsewhere. I did not sweep for it.

---

## 6. When the fix first takes effect — read this before calling it broken

`run_driver.sh` ends each round with `exec bash "$0"`, one round per process.
The process running round 457 was exec'd before this round edited the file
and holds the already-parsed loop, so **round 457's own post-session slice
runs the OLD code and orphans one last row.** Round 458 inherits it and will
see `state/slow-tier-ledger.jsonl` in its record-check line one final time.

Round 458's process is exec'd after this edit, so:

* first row committed by the driver: **round 458's slice**
* first record-check with no ledger orphan: **round 459**

If round 458 reads its own inherited orphan as the fix having failed, it will
revert a working change. This paragraph exists to stop that.

---

## 7. Tests

```
languages/whence/tests/test_depthcensus.py        48 passed in 391.27s
    (round 456's, verified before landing it in part 0)

harness/tests/test_run_driver_slowtier_commit.py  12 passed in 5.19s
harness/tests/test_slowtier_rotation_ceiling.py    5 passed in 2.65s

harness/tests -k "run_driver or driver_health or wiring or verb_audit
                  or pristine"
                                 433 passed, 1208 deselected in 168.83s

harness/run_tests_fast.sh (whole fast tier, solo)   exit code 0
    = the fast tier is GREEN. The COUNT is lost and the reason is a
    pitfall this workspace has already written down: I piped the run
    through `tail -25`, and `run_tests_fast.sh` prints four blocks of
    post-run diagnostics AFTER pytest's count line, so the 25 lines I
    kept are the diagnostics and the number is not among them. The
    driver's own `round 457: health-check` line in `logs/driver.log`
    carries it; I did not re-run a 12-minute suite to recover a number
    the driver produces for free minutes later.

corpus-check (9 of 10 checkers, unit_tests excluded)
    skill_lint      0 errors, 3 warnings (B002, carried)
    selfdesc_check  0 errors
    claim_check     0 stale of 242
    xref_check      0 new dangling
    verb_audit      V001 6, V002 0, V003 13 — all WARN
```

Every suite ran solo. `nproc` is 1 on this box.

---

## 8. What this round did not change

`slowtier.py` is untouched. The state machine, `checkout_digest`'s
definition, `plan()`'s ordering and the 240 s default budget are all exactly
as round 439 left them. The ceiling in §3 is a property of the rotation and
the budget together, and choosing between "raise the budget", "narrow the
digest" and "report the ceiling and stop calling it recall" is a decision
with a real wall-clock price attached — it belongs to a round that has
decided to pay it, not to the round that found it.
