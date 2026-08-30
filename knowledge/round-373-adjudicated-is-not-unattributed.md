# Round 373 (harness A) — a dirty-tree check that could not tell "unseen" from "decided"

Round 370's next-steps item 7, restated as round 371's item 5 and round 369's
item 10, addressed to the track that owns the checker:

> A process cost worth naming: the record-gap check has flagged this same
> known, deliberately-unresolved file at the top of ten straight rounds, each
> paying the same inspection. A third category — *known-escalated
> tracked-file diffs* — would let the checker report it as acknowledged.

The item is right about the shape and wrong about the size, and the way it is
wrong is the more interesting half.

## 0. What this round did

1. Verified and landed round 372's leftover diff (it died interrupted, no
   knowledge file, no state entry).
2. Measured the cost the item names, from `logs/driver.log` rather than from
   prose.
3. Built the fifth gap shape in `check_round_recorded.py` —
   `state/known-escalated-diffs.json`, **content-pinned**, satisfying round
   349's objection rather than overriding it.
4. Fixed the driver's injected NOTE, which had described gap shape 1 for four
   shapes and ~120 rounds.
5. Fixed a defect that fix introduced (a truncated driver.log entry).
6. Removed the third hand-maintained copy of the same adjudication, in
   `harness/pristine_check.py`'s rule-1 waiver, and used the result to
   re-run the pristine differential rounds 367/369/371 kept deferring.

Predictions banked before any of it: `state/harness/round-373/PREDICTIONS.md`.
**10 HIT / 0 MISS, plus one supplementary HIT** — and a low miss count is
itself a finding about the predictions, discussed in §8.

## 1. The measurement — the prose was wrong three different ways

`logs/driver.log` records one `record-check FOUND gap(s) — <stdout>` line per
round. Parsing all 55 of them:

| | |
|---|---|
| rounds whose record-check output names `languages/whence/SECURITY.md` | **25** (349-373, consecutive) |
| of those, rounds where it is the **only** unattributed path | **13** |
| of those, rounds where it is the only finding **of any shape** | **13** |
| total path-inspections charged across those 25 rounds | 148 |

So in 13 of 25 rounds — 52% — the script's entire non-zero exit, and the
entire NOTE injected into that round's prompt, existed for an item round 349
had already inspected, decided, and deliberately left open. Those 13 rounds
are 350, 352, 353, 354, 358, 359, 360, 362, 366, 368, 370, 371, 372.

**The ordinals in the next-steps list were all wrong, and no two agreed.**
Round 369 wrote "TWELFTH consecutive round", round 370 wrote "TENTH", round
371 wrote "ELEVENTH" — in that order. Three consecutive rounds, three
hand-typed ordinals, one going *backwards*, none matching the log's 21st,
22nd and 23rd. This is round 333's stale-number class (*a line asserting a
number that no round re-executes*) inside the very mechanism the program uses
to carry work forward, and it is the fourth independent instance after rounds
333, 365, 369 and 371. The fix here is not to correct the number: the
checker now **computes** the carried count from the driver log
(`latest_round - escalated_round + 1`) and prints it, so no round has to
type it again.

## 2. Why the standing-dirty allowlist is the wrong fix, and what is the right one

Round 349 found the diff (the Hermes gateway rewrote `SECURITY.md` to assert
four security controls this repo does not have; round 349 checked all four,
found four for four false, and escalated to the operator because it is an
outward-facing document in a domain where the operator has authorship
interest). It also refused, explicitly, to put it in
`state/known-standing-dirty-paths.json`:

> that registry models untracked leftovers, and allowlisting a tracked file
> would mean "never look at this diff again", which is the wrong answer

That refusal is correct and is the whole design constraint. A separate system
*can* edit that file again, and that new edit is the single most important
event this checker could report. An unconditional allowlist entry would
guarantee it went unseen.

**`state/known-escalated-diffs.json` is not an allowlist. It is a pin.** Each
entry records the adjudicating round, its reasoning, and BOTH blob hashes of
the diff:

```json
"languages/whence/SECURITY.md": {
  "escalated_round": 349,
  "worktree_blob": "61248e50a3f5...",   // git hash-object <path>
  "head_blob":     "929c52c42523...",   // git rev-parse HEAD:<path>
  "reason": "...", "suite_neutral": true
}
```

`classify_escalated_diffs` returns one of three states:

| state | condition | effect |
|---|---|---|
| `acknowledged` | dirty **and** both hashes match | quiet line with the carried count; **does not affect the exit code** |
| `changed` | dirty and either hash moved, or is unpinned, or cannot be computed | reported **louder** than an ordinary unattributed path; rc=1 |
| `resolved` | not dirty at all | a dead acknowledgement; reported so it is deleted; rc=1 |

Three properties are load-bearing and each is pinned by a test.

**Both halves, because a diff is a pair.** Pinning only the working-tree bytes
is not enough: a later commit can move the base while the bytes on disk are
untouched, and the acknowledged diff is then a different diff.
`test_classify_expires_the_pin_when_only_the_base_moved` constructs exactly
that — it asserts the observed worktree hash still equals the recorded one
and that the entry expires anyway.

**Fail closed.** If the tree is known and the path is dirty but a hash cannot
be computed, the entry does **not** suppress. Everywhere else in that module
an unavailable git degrades to "don't flag"; here that would be a suppression
rule whose own precondition failed open, which is the one direction that
loses information. This is round 367's rule 10 ("a run that did not FINISH
may not narrow") in a different file.

**...but "the tree could not be read at all" is a different question.** The
first version returned `resolved` for every entry when `working_tree_status`
came back `None`, which declares every acknowledgement dead on any
non-checkout caller — and it broke two pre-existing tests that run the CLI
against a `tmp_path` that is not a git repo. `status is None` now returns
nothing at all: every state below it is a claim about the dirty set, and
none of them can be made.

**A dead acknowledgement is reported, not silently kept.** This is round
372's `test_each_exemption_is_load_bearing` in another registry: an
acknowledgement that suppresses nothing reads as coverage.
`test_live_registry_is_well_formed_and_every_entry_is_load_bearing` asserts
it against the repo's own registry, so the entry has to be deleted the day
the operator resolves the file.

## 3. The driver was describing a different check than the one it ran

`run_driver.sh` pastes the checker's stdout into the next round's prompt
under a fixed preamble:

> the round(s) below ran per logs/driver.log but have no
> state/research-state.md entry yet

That sentence describes gap shape 1. The checker has had shape 2 since round
259, shape 3 since round 273 and shape 4 since round 291. **This round's own
injected note is the proof**: that sentence, followed by three dirty paths,
none of which is a round.

Nothing asserted the correspondence, so nothing reported the drift for four
shapes. `test_injected_note_preamble_enumerates_every_implemented_gap_shape`
now counts the `Round N added a <ORDINAL> ... gap shape` claims in the
checker's own module docstring and requires the preamble to enumerate exactly
that many — so a sixth shape cannot ship without the note that carries it.
All three preamble tests were confirmed RED against the pre-change file
before being kept.

## 4. The defect the fix introduced

The driver's PASS branch logged `$RECORD_CHECK_OUT` through `tr -d '\r'`. That
was correct for as long as a zero-exit run printed exactly one sentence — and
the fifth shape prints acknowledged escalations on a zero-exit run. `log()` is
`echo ... | tee -a`, so the multi-line output produced a driver.log entry
whose continuation lines carry no timestamp and match none of
`check_round_recorded.py`'s own line regexes. Confirmed by removing the fix
and watching the e2e test report the entry truncated at
`...if the file or its base moves):` with the path itself gone.

The general rule: **any log a program parses line-by-line needs the newline
squeeze on every branch that can grow a second line**, not just the branch
that had multi-line output when it was written.

## 5. The third copy of the same fact

`harness/pristine_check.py status` had been printing, for rounds:

```
allowed-dirty (rule 1 waived by hand): languages/whence/SECURITY.md
```

That is a *third* hand-maintained encoding of round 349's adjudication (after
its own prose and the checker's output), and it required a hand-typed
`--allow-dirty` at every invocation — one of the reasons the ~12-minute
re-run kept being deferred.

`escalation_allowed_dirty()` reads the same registry, and waives a path only
when **both** conditions hold:

- the pin still holds (so the waiver expires with the acknowledgement), and
- the entry declares `"suite_neutral": true`.

The second condition is the one worth stating. Rule 1 asks *could this dirty
file have changed a suite's outcome?* — and "has been adjudicated" says
nothing about that. An escalated `.py` must keep blocking. `suite_neutral` is
a separate, separately-justified claim about THIS diff (checked for
`SECURITY.md`: no test in any suite reads it, nothing imports or globs it,
the diff is prose inside one Markdown file), and it rides on the same content
pin, so editing the file expires both together.

The record keeps them apart: `escalation_allowed_dirty` is a distinct ledger
field from `allowed_dirty`, because a ledger reader must be able to tell a
hand judgement made at run time (unverifiable afterwards) from a
content-pinned one (re-checkable at any later date).

A smaller consistency bug fell out: `pristine_check.py dirt` used
`blocking_dirt`'s default allow set, so the preview printed `BLOCKING
languages/whence/SECURITY.md` while `check` on the same tree was about to
waive it. A preview that disagrees with the thing it previews is worse than
no preview.

## 6. The pristine differential, re-run

Rounds 367 (item 4), 369 (item 8) and 371 (item 8) all carried the same
observation: `harness/pristine_check.py status` was printing a recorded
verdict that no round re-executes — round 333's stale-number class in a
STATUS LINE, which is worse than in prose because the line looks live. It
named two tests as failing that round 367 had already confirmed pass. The
re-run kept being deferred at ~12 minutes and a hand-typed `--allow-dirty`.

With the pinned waiver, rule 1 cleared with no flag typed, and the run went
in the background:

| suite | recorded (stale) | re-run, this round |
|---|---|---|
| `harness-fast` | `both_failed`, live `524 passed / 1 failed` | **clean**, live = pristine = `587 passed, 323 deselected` (95.9 s) |
| `whence-fast` | `clean`, `1193 passed` | **clean**, `1595 passed, 3 skipped, 70 deselected` (84.6 s) |
| `whence-slow` | `both_failed`, live `53 passed / 1 failed` | **clean**, `70 passed, 1598 deselected` (1014.6 s) |

```
ref HEAD (91acd9c5af97)   verdict clean
  17 untracked path(s) exist here and in no fresh clone
  allowed-dirty (escalation pin, suite-neutral): languages/whence/SECURITY.md
```

Both named tests pass today, in both trees. The stale verdict was stale in
exactly the direction round 367 suspected, and it had been carried for three
harness rounds. The `allowed-dirty (escalation pin, ...)` line is the new
mechanism working end to end on the real repo: the ledger entry now records a
waiver a later reader can re-check rather than one typed by hand.

Note what the differential does NOT say. `clean` means the two trees agree,
not that the suite is comprehensive; and the 17 untracked paths still exist
here and in no fresh clone, which is the standing round-355 condition, not a
new one.

## 7. What the tests caught that I did not predict

Adding a fifth registry with a repo-root-relative default (`--escalated-diffs-
file`, defaulting to `state/known-escalated-diffs.json`) broke **six**
pre-existing end-to-end tests immediately. They pass `--ack-file` and
`--standing-dirty-file` pointed at non-existent `tmp_path` files precisely to
neutralise the other two registries; the new default leaked the live repo's
registry into a `tmp_path` workspace, where the pinned path is not dirty, so
every run reported a dead acknowledgement and exited 1.

This is round 349's own finding in a different guise — that round found
pytest's *config discovery* reaching out of the workspace and taking down
1043 tests. A default resolved against the caller's cwd is a hidden input.
The suite caught it in seconds because someone had already written the
neutralising flags for the other two registries; the fix was to add the
third, at the same 14 call sites.

## 8. Honest failures and limits

1. **10 HIT / 0 MISS is a signal about the predictions, not about the round.**
   D-013 exists to make a round wrong in public, and a bank that goes 10/10
   was mostly *retrodiction*: P3-P8 asked about facts already fixed in the
   repo's history and merely unread. The genuinely uncertain ones were P1/P2
   (the log's own count and the dilution ratio) and P11 — and P2 landed at
   13/25, one round either side of its threshold. A future round banking a
   bank like this should mark which predictions are about the FUTURE and
   which are about an unread PAST, and expect only the first kind to teach
   it anything.
2. **The escalation stops reaching the round's prompt.** On a zero-exit run
   the driver logs the acknowledgement line but injects nothing, so an
   acknowledged escalation now reaches rounds only via `driver.log` and the
   state file's next-steps. That is the intended trade — it is what "stop
   paying the inspection 13 times" means — and it is not free. It is stated
   here and in the SKILL.md pitfall rather than left to be discovered. No
   threshold ("re-surface after N rounds") was added: the blocker is an
   operator decision, and an alarm that fires on something no round can fix
   recreates the noise with extra steps.
3. **`changed` and `resolved` have never fired on real data.** Both are
   fixture-tested only, the same never-observed-live shape as round 310's
   item 3 and round 349's `classify_health_log`. `changed` will fire the next
   time the gateway edits `SECURITY.md`; `resolved` will fire the day the
   operator resolves it, which is the only way this registry empties.
4. **The carried-rounds count assumes the escalating round appears in the
   driver log.** `latest_round - escalated_round + 1` is not a count of
   record-check lines naming the path; it happens to equal the log's own 25
   here because the flagging has been unbroken since 349. If a path were
   escalated, resolved, and re-escalated, the number would over-count. Not
   fixed, because the registry has no history field and inventing one for a
   case that has never occurred is speculative.
5. **`suite_neutral` is a claim a round makes, and nothing verifies it
   mechanically.** The check "no suite reads this file" was a grep, not an
   instrument. A `.md` is easy; the first `.py` entry will need better, and
   the safe default (absent/false ⇒ keeps blocking) is what makes that
   acceptable today.
6. **Round 372 still owes a knowledge file and a research-state entry.** This
   round verified and landed its diff (both tiers green at that exact tree)
   and deliberately did not write round 372's record for it — that is
   language(C)'s, and manufacturing an entry would hide the gap rather than
   close it. It remains reported by shape 1.

## 9. Verification

| what | result |
|---|---|
| `pytest skills/session-inheritance-audit/scripts/test_check_round_recorded.py` | **80 passed** (was 56; +24) |
| `pytest harness/tests/test_run_driver_record_gap_check.py` | **7 passed** (was 3) |
| `pytest harness/tests/test_pristine_check.py` | **62 passed** (was 54) |
| `bash harness/run_tests_fast.sh` | **587 passed, 323 deselected** (was 575) |
| `languages/whence/run_tests_fast.sh` (round 372's diff) | **1595 passed, 3 skipped, 70 deselected**, 42.6 s |
| `pytest -m whence_slow tests/` (round 372's diff) | **70 passed, 1598 deselected**, 523.4 s |
| `pristine_check check` x3 suites | **clean / clean / clean** — see §6 |
| `corpus_check.py` | <!--CORPUS--> |
| live `check_round_recorded.py` | <!--LIVECHECK--> |

**Falsified, not merely asserted.** Every new test in this round that pins a
behaviour change was confirmed RED against the pre-change file before being
kept:

- the three preamble tests, against the shape-1-only wording;
- the driver-log single-line test, against `tr -d '\r'` alone — it reported
  the entry truncated at `...if the file or its base moves):` with the path
  gone.

**And the `changed` state was exercised by hand on the real registry**, not
only in a fixture, per the new skill's own verification rule:

```
$ printf '\n<!-- simulated third-party edit -->\n' >> languages/whence/SECURITY.md
$ python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
check_round_recorded: 1 known-escalated tracked-file diff(s) whose
ACKNOWLEDGEMENT NO LONGER HOLDS - ... NOT suppressed:
   M languages/whence/SECURITY.md - escalated round 349: working-tree content
   moved: 89bfce636a5b != recorded 61248e50a3f5 - a third party edited this
   tracked file AGAIN; re-inspect before re-pinning
$ # restored; back to "carried 25 round(s), pinned 61248e50a3f5"
```

## 10. Prediction scoring

| # | prediction | result |
|---|---|---|
| P1 | SECURITY.md named in >= 10 rounds' record-check output | **HIT** — 25, consecutive 349-373 |
| P2 | it is the ONLY unattributed path in more than half of them | **HIT** — 13/25 = 52%, one round either side of the threshold |
| P3 | the first such round is 349, not 350 | **HIT** |
| P4 | exactly 1 tracked file qualifies today | **HIT** |
| P5 | its content has not moved since round 349 | **HIT** — the only commit ever touching it is the repo's initial commit; mtime still 23:32:41 |
| P6 | no test asserts the NOTE preamble matches the gap shape | **HIT** |
| P7 | rewording the preamble needs 0 edits to existing tests | **HIT** — the only two occurrences of that sentence anywhere were `run_driver.sh` and this round's own bank |
| P8 | the checker's unit tests live under `skills/`, >= 20 of them | **HIT** — 56 |
| P9 | after landing: 0 unattributed paths, 1 acknowledged escalation, still exits 1 for round 372's missing entry | <!--P9--> |
| P10 | zero live `resolved` instances | **HIT** |
| P11 (suppl.) | >= 10 of the 25 rounds would have produced no finding at all | **HIT** — 13 (rounds 350, 352, 353, 354, 358, 359, 360, 362, 366, 368, 370, 371, 372) |

See §8.1 on why 10/10 is a criticism of the bank rather than a result.
