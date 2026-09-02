---
name: writer-lands-its-own-write
description: Use when a background or post-hoc step writes into a shared record AFTER the actor whose work it describes has exited — a CI job appending to a results file after the build's commit, a cron sweep writing a metrics row, a driver appending to a ledger after the round's session ends, a teardown hook updating a manifest. Symptoms: the same file is dirty at the start of every run and someone lands it "for" the previous run; a ledger or manifest reliably one entry behind its own commits; a recurring "land X's leftover" housekeeping commit; an inheritance check naming the same path unattributed every time. Covers proving the write is ordered rather than raced (a delta histogram with one bin), moving the commit to the writer, scoping it to one pathspec, and keeping the writer's signature from being misread as evidence that the exited actor acted — which blinds the check that found the orphan. NOT for genuine write races.
---

# The step that writes it is the step that must land it

A record written after its author is gone has no author. Someone else lands
it, every time, forever — and the "someone else" is whoever runs next, who
pays a startup tax for work they did not do and cannot verify.

The failure looks like a race and is not one. A race is intermittent. This
is deterministic: if the write always happens after the last commit, the
orphan rate is 100% and the delta between the run that produced it and the
run that landed it is always exactly +1. Measure that first — the constant
delta is what distinguishes "wrong order" from "concurrent writers", and the
two have opposite fixes.

## When to use (triggers)

- The same path is dirty at the start of every run and a recurring commit
  subject says "land <previous run>'s <thing>".
- A post-run hook, teardown step, reporter, or scheduled sweep appends to a
  file that lives in the same repo/record the run commits to.
- An inheritance/gap check (`check_round_recorded`-shaped: "uncommitted,
  unattributed change RIGHT NOW") names the same path run after run.
- A ledger, changelog, coverage file or manifest is reliably one entry
  behind, and nobody can point at when it fell behind.
- Somebody proposes "the next run should remember to commit it" — that is
  the tax, restated as a policy.

Do NOT use when two live processes write the same file (that is a lock or a
CAS problem), or when a genuinely separate system owns the file and always
will (allowlist it — see `state/known-standing-dirty-paths.json` for the
shape).

## Steps

1. **Prove the ordering before fixing it.** For every write, find the run
   that produced it and the run that landed it, from timestamps, not from
   commit subjects. Subjects name the run whose WORK it is, which in a
   program that lands its predecessor's leftovers is the wrong run.

   ```bash
   # producing run: the write's timestamp falls between run N's session end
   # and run N's post-session hook. landing run: the session window that
   # contains the commit that first introduced the line.
   git log --reverse --format='%H|%ct' -- <record> \
     | while IFS='|' read -r h ct; do
         printf '%s %s %s\n' "$h" "$ct" "$(git show "$h:<record>" | grep -c .)"
       done
   ```

   Report three numbers: landed by its own run, landed by a later run (with
   the delta histogram), still unlanded. A single-valued delta histogram is
   the proof. A spread is a race and this skill does not apply.

2. **Move the commit to the writer**, immediately after the write, inside
   the same existence guard the write already has. Do not move the write
   earlier: running the step before the actor would land the PREVIOUS
   record and orphan this one — the same defect, displaced by one.

3. **Scope it to one pathspec, and do not touch the index.**

   ```bash
   git -C "$WS" commit -q -m "<subject>" -m "<body>" -- "$RECORD_REL"
   ```

   `git commit -- <path>` commits that path's working-tree content and
   leaves everything else staged exactly as it was. An actor killed
   mid-flight can leave a populated index; sweeping it into a background
   commit is how unattributed work enters a history.

4. **No `git add`.** If the record is untracked, the commit fails — and
   that is the right answer. Deciding to start tracking a file is a
   judgement call; a background job does not get to make it.

5. **Guard on being the repository root, not on being in a repository.**

   ```bash
   TOP=$(git -C "$WS" rev-parse --show-toplevel 2>/dev/null || true)
   REAL=$(cd "$WS" 2>/dev/null && pwd -P || echo "")
   [ -n "$TOP" ] && [ "$TOP" = "$REAL" ] || skip
   ```

   Test fixtures run the same code in a temp directory. `rev-parse
   --git-dir` succeeds for any directory *inside* a checkout; equality with
   `--show-toplevel` is what stops a test from committing into whatever
   repository it happened to land under.

6. **Make the writer's signature unreadable as the actor's.** This is the
   half that gets missed. Find every checker that answers "did actor A do
   anything?" by pattern-matching the record, and confirm your new entry
   does not satisfy it. Here that check greps `git log --all --oneline` —
   SUBJECTS ONLY — for `round N`, so the round number goes in the commit
   BODY and the subject is a constant. Pin it with a test that calls the
   checker, not with a comment.

7. **Log the skips as loudly as the successes.** An "untracked, so I did
   nothing" branch that prints nothing is an invisible off switch. Every
   path through the new step should leave a line.

8. **Say when the fix first takes effect.** A self-re-executing runner
   holds its already-parsed copy until it re-execs, so the process running
   right now finishes under the OLD code. Write down the first run that
   will actually exercise the change, or the next run reads one last
   orphan as proof the fix failed.

## Pitfalls

- **Attributing landings by commit subject.** In any program that lands its
  predecessor's leftovers, subjects credit the work's owner, not the
  committer. Round 457 got "8 rows landed by their own round" this way; the
  real number, from session windows, was zero.
- **Assuming a repeated orphan is a race.** Two runs writing at once and one
  run writing too late look identical in `git status`. Only the delta
  histogram tells them apart.
- **Fixing it in the next actor.** "The next round lands it in part 0" is
  the tax institutionalised. It also silently trains the inheritance check's
  readers to ignore a real signal.
- **Blinding the detector.** A background commit that names the actor makes
  "actor recorded work but committed nothing" undetectable. The check that
  found your orphan is usually the check you are about to break.
- **`git diff HEAD -- <path>` is blind to untracked files.** It reports no
  change, so a dirtiness guard built on it falls through and the whole
  branch silently does nothing. Use `ls-files --error-unmatch` to decide
  trackedness first.
- **Landing more than the record.** `git add -A` in an unattended step has
  already cost this repo a documented incident: the `AUTO-COMMIT v4` commit
  `e376750` deleted 38 lines of `CLAUDE.md`, including a whole rules
  section, and it went unnoticed for roughly 200 rounds.

## Verification

Run against this repo, which holds the founding instance:

```bash
# 1. the ordering proof and the fix, end to end (12 tests)
.venv/bin/python -m pytest harness/tests/test_run_driver_slowtier_commit.py -q
#    -> 12 passed

# 2. the two properties that are easy to get wrong, by name
.venv/bin/python -m pytest harness/tests/test_run_driver_slowtier_commit.py -q \
  -k "enclosing_repository or cannot_be_read_as_evidence"
#    -> 2 passed

# 3. the guard, evaluated against the live workspace
TOP=$(git rev-parse --show-toplevel); REAL=$(pwd -P)
[ "$TOP" = "$REAL" ] && echo "root-match OK"
git ls-files --error-unmatch -- state/slow-tier-ledger.jsonl >/dev/null \
  && echo "record TRACKED"
#    -> root-match OK / record TRACKED

# 4. the call site itself: one pathspec, no `git add`, after the write
grep -n 'SLOWTIER_LEDGER_REL' run_driver.sh
#    -> the guard, the untracked branch, and a single
#       `commit -q ... -- "$SLOWTIER_LEDGER_REL"`
```

A correct application produces, at minimum: a delta histogram with one bin,
a commit whose `--name-only` output is exactly one path, and a test that
calls the attribution checker and asserts it still says "no".
