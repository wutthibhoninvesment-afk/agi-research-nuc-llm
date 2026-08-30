---
name: content-pinned-acknowledgement
description: When a checker keeps reporting something a human already inspected and deliberately left alone, do not add the path to an allowlist — record the acknowledgement against a hash of the exact content that was adjudicated, so it suppresses that finding and expires by itself the moment the thing changes. Covers baseline/known-failure/allowlist files, escalations nobody in the loop can resolve, and any suppression that would otherwise mean "never look at this again".
---

# Acknowledge the artifact, not the path

## Trigger conditions

Trigger on any of these:

- A checker, linter, CI gate or audit script **keeps reporting the same
  finding every run**, someone has already looked at it, and the finding is
  correct but not actionable *right now* — it is blocked on an owner, a
  release, an operator decision, or a deliberate design call.
- You are about to add a path, rule id, test id or file name to an
  **allowlist / baseline / known-failures / ignore file** so a check goes
  green.
- Someone proposes suppressing a finding and someone else objects that
  suppressing it would mean **"we never look at this again"** — and both are
  right.
- A gate's output is mostly items that are already decided, so **readers have
  started skimming it**, and a real new finding would be missed in the noise.
- The same decision is recorded by hand in **more than one place** (a
  reviewer's prose, a CLI flag typed at each invocation, a comment) and the
  copies have started to drift.

Do NOT reach for this when the finding is simply *wrong* (fix the rule), when
it is actionable now (fix the thing), or when what changes is not
content-addressable — a flaky test, a timing threshold, a network condition.
The pin below needs a stable digest of a concrete artifact.

## Why an allowlist is the wrong instrument

An allowlist entry is a claim about a **name**: *this path never counts*. The
thing that was actually adjudicated is a **state**: this file, with these
bytes, against this base. The two come apart the first time anything edits
the file — and if the reason the file is on the list is that something
*outside your control* wrote it, that edit is the single most important event
the checker could have reported. An allowlist guarantees it goes unseen.

A content pin makes the acknowledgement say what was actually decided:

> round 349 inspected **this diff** and chose to leave it

which is a statement that can stop being true, and does, automatically.

Second-order benefit, and in practice the one people notice: it kills the
"is this old or new?" reading cost. An entry that is still pinned is
provably the thing you already read.

## Steps

1. **Measure the noise before designing anything.** Count, from the tool's
   own historical output (CI logs, a run log, `git log` of the baseline
   file), how many runs reported the item and in how many of them it was the
   *only* finding. The second number is the one that justifies the work: it
   is the count of runs whose entire failure existed for something already
   decided. Do not take a hand-maintained tally in a TODO or a status doc as
   this number — see the first pitfall.

2. **Write down what the pin is over.** For a file diff that is a PAIR of
   digests: the content as it stands (`git hash-object <path>`) *and* its
   base (`git rev-parse HEAD:<path>`). Pinning only the first is a common,
   silent hole: a commit can move the base while the bytes on disk are
   untouched, and the acknowledged diff is then a different diff. For a test
   baseline it might be the test id plus the assertion text; for a
   dependency advisory, the advisory id plus the resolved version.

3. **Give the registry one entry per acknowledgement, and require evidence
   fields**: who adjudicated it (round / PR / ticket), a reason a stranger
   can act on, and the pin. A registry whose entries do not name their
   evidence is an allowlist with extra syntax.

4. **Classify into three states, not two.** This is the step people skip.
   - **holds** — the item is present and the pin matches: suppress it from
     the failing set, but still *print* it, with an age.
   - **expired** — present, pin does not match: report it **more loudly**
     than an ordinary finding. This is a new event, not a recurring one.
   - **dead** — the item is gone entirely: the entry now suppresses nothing.
     Report it so it gets deleted. A suppression that suppresses nothing
     reads as coverage and hides the next real one.

5. **Fail closed on a pin you cannot verify.** If the item is present but the
   digest cannot be computed, do **not** suppress. An acknowledgement you
   cannot check must not silence anything. Keep this distinct from *"the
   whole input was unreadable"* — there, no claim can be made in either
   direction, and the right answer is to classify nothing rather than to
   declare every acknowledgement dead.

6. **Derive the age; never type it.** If the tool has a run log, compute
   "carried N runs" from it. A hand-incremented ordinal in a status doc is a
   number nothing re-executes and it will drift (see pitfalls).

7. **Split the claim if the registry is read by two consumers.** "This has
   been adjudicated" and "this cannot affect the test outcome" are different
   claims. Put the second behind its own field, default false, so a consumer
   that needs it must find it explicitly stated and a new entry is safe by
   default.

8. **Make the registry the only copy.** Once it exists, have every other
   consumer of the same decision read it — the hand-typed CLI flag, the
   second script, the comment. That is what removes the drift the trigger
   section describes.

9. **Test all three states, plus both fail-closed directions.** In
   particular test *expired-because-only-the-base-moved*: assert the content
   digest still matches and the entry expires anyway. If that test does not
   exist, step 2's pair is probably not implemented.

10. **Assert the registry is load-bearing against the live data.** One test
    that loads the real registry and fails if any entry is `dead`. That is
    what stops the file becoming a graveyard.

## Pitfalls

- **The hand-maintained tally is wrong, and you will quote it.** Three
  consecutive status updates in one repo described the same carried item as
  the "TWELFTH", "TENTH" and "ELEVENTH" consecutive occurrence — in that
  order, one going backwards — while the run log said 21st, 22nd and 23rd.
  Get the number from the log, then make the tool print it.
- **A new registry with a path-relative default is a hidden input.** Adding
  one broke six existing end-to-end tests instantly: they neutralised the
  *other* registries with explicit flags but the new default reached out of
  the temp workspace into the real repo, found the pinned item not present
  there, and reported a dead acknowledgement. Every registry needs the same
  override, and the tests that isolate one must isolate all of them.
- **Suppressed output can grow a second line, and a log that squeezes only
  carriage returns will truncate it.** If the suppressed items print on the
  *success* path, any consumer that parses that log line-by-line silently
  loses everything after the first newline. Squeeze newlines on every branch
  that can grow one, not just the branch that was multi-line when written.
- **Suppressing it from the gate also removes it from whatever the gate
  feeds.** If a downstream consumer (a prompt, a digest email, a dashboard)
  only receives *failures*, an acknowledged item stops reaching it entirely.
  That is usually the intended trade — say so explicitly and name the other
  channel that still carries it, rather than discovering it later.
- **Do not add a "re-surface after N runs" timer to compensate.** If the
  blocker is someone else's decision, an alarm nobody in the loop can clear
  recreates the noise with extra steps. The registry entry and the run log
  are the record.
- **`expired` and `dead` are usually fixture-only for a long time.** Say so.
  They are the two states that matter and neither will have fired on real
  data the day you ship.

## Verification

Against `state/known-escalated-diffs.json`,
`skills/session-inheritance-audit/scripts/check_round_recorded.py` and
`harness/pristine_check.py` in this repo (round 373):

```bash
# 1. the acknowledgement holds: printed with a derived age, exit code unaffected
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
#   "1 known-escalated tracked-file diff(s) ... content UNCHANGED"
#   " M languages/whence/SECURITY.md - escalated round 349, carried N round(s)"

# 2. all three states plus both fail-closed directions
python3 -m pytest -q skills/session-inheritance-audit/scripts/test_check_round_recorded.py
#   80 passed  (classify_* tests: acknowledged / changed / resolved,
#               base-moved-only, unpinned, git-unavailable, tree-unreadable)

# 3. the second consumer reads the same registry rather than a typed flag
python3 harness/pristine_check.py dirt
#   "pinned-waiver (escalation, suite-neutral)  languages/whence/SECURITY.md"
#   and 0 blocking, with no --allow-dirty typed anywhere
python3 -m pytest -q harness/tests/test_pristine_check.py     # 62 passed
```

A correct implementation shows these shapes rather than these values:

- the suppressed item still **appears** in output, with an age the tool
  derived;
- flipping one byte of the pinned artifact moves it from the quiet section to
  a section that is louder than an ordinary finding — check this by hand
  once, not only in a fixture;
- removing the artifact entirely produces a *dead entry* report naming the
  registry file and the entry to delete;
- the live-registry test fails if any entry is dead.
