---
name: skip-reason-is-a-claim
description: Use when a guard decides whether a check RUNS — a pytest skipif, a feature-flag early return, a "not applicable" branch in a linter or CI job, a monitoring alert's suppression rule — and its condition can be true for more than one cause. Symptoms: one predicate returning a truthy "why" string that several different situations produce; a skip message that is true in the case you wrote it for and false in another ("corpus moved: missing X" where nothing moved); a condition that is `if anything_is_missing`; a suppression that would also fire on the event the check exists to catch; the same guard helper copied into two files. The move is to enumerate the guard's states, give each cause its own answer, and find the state that must NOT be exempt. NOT for an exemption you have never counted (measured-exemption), NOT for classifying missing CONTENT (deleted-vs-never-written).
---

# A skip reason is a claim, and one sentence cannot serve two causes

A guard that skips a check publishes a sentence to whoever reads the run.
That sentence is an assertion about the world, made by code, in a place
nobody re-reads — and it is the one part of a test suite that is never
itself tested, because a skipped test is green.

The failure has a shape. Someone writes a guard for the cause they are
looking at, phrases the reason for that cause, and implements the condition
as the broadest thing that is true of it. Later a *different* cause makes
the same condition true. The check goes quiet under a sentence that is now
false, and — worse — the newly-swallowed cause is often the one the check
was most needed for.

The case this was written from: a test-suite guard asked "has the corpus
this measurement was frozen against been rewritten?" and implemented it as
"walk the frozen census; return a reason string for the first file that is
missing OR whose bytes differ." Two causes, one answer.

| state | old answer | what it should be |
|---|---|---|
| all present, all as frozen | run | run |
| all present, one **rewritten** | skip: "corpus moved: changed X" | skip |
| **none** present (a fresh checkout) | skip: "corpus moved: missing X" | skip, *different reason* |
| **some** present, some gone (drift) | skip: "corpus moved: missing X" | **RUN, and go red** |

Both wrong rows cost something and they are not the same cost. The loud one:
in every clean checkout, seven tests announced a rewrite that had not
happened, and two rounds of work were spent reading that as a finding. The
quiet one: had the upstream system ever *deleted* one of the files, the
tests measuring it would have gone silent about the single loudest thing
they could have discovered.

## When to use (triggers)

- A `skipif` / `if not applicable: return` whose condition is a disjunction,
  or is "the first thing that looks wrong", or is `if anything is missing`.
- A guard that returns a *reason string* rather than a boolean — the string
  is a claim, and one function producing it usually means one sentence for
  several causes.
- The same guard helper exists in two or more files. The duplication is the
  visible problem; look for the conflated states, which is the real one.
- A reason string that reads oddly in an environment you did not write it
  for: a CI container, a fresh clone, a worktree, a fork without secrets.
- A suppression rule in monitoring/CI whose condition would also match the
  incident it is supposed to page on.
- You are about to add a skip so that a suite is green in a new environment.
  That is the highest-risk moment for this defect: the new environment's
  cause gets bolted onto the existing condition.

**When NOT to use:** the exemption has exactly one cause and you only want
to know whether it still fires (`measured-exemption`); you are classifying
missing repository CONTENT (`deleted-vs-never-written`); the guard is a
plain capability probe with no alternative cause (`if not shutil.which(...)`).

## Steps

1. **Enumerate the states, in a table, before touching code.** Columns:
   state, how it arises, what the check should do, what it does today. Write
   the row for every environment the code actually runs in — developer tree,
   CI, fresh clone, worktree, fork, container without credentials. The
   states that get missed are the ones nobody's laptop produces.

2. **Find the state that must NOT be exempt.** For each row ask: *if this
   were the world, is the check's silence a service or a cover-up?* Exactly
   the states whose silence is a cover-up must return "run". This is the
   only question in the whole procedure that is a judgement call; everything
   else follows from it.

   Rule of thumb: a state that means *the subject is not here* is a skip;
   a state that means *the subject changed under us* is usually a skip;
   a state that means *part of the subject is gone* is a **failure**,
   because "gone" is the one that can be a mistake.

3. **Split the predicate along the states, not along the code.** One
   function per distinguishable fact, each answering a single question and
   saying nothing about the others:

   ```python
   def subject_missing(root):  ...   # which declared parts are not here
   def subject_absent(root):   ...   # ALL of them -> never was this tree
   def subject_changed(root):  ...   # present but not as frozen
   ```

   Then ONE decision function that composes them and is the only thing a
   caller uses. Predicates answer facts; the decision function encodes
   policy, and the ORDER of its checks IS the policy — write the order down
   as a comment because it is not recoverable from the individual answers.

4. **Order the decision by which cause is louder.** Two states can be true
   at once (a part deleted *and* another rewritten). Check the one whose
   silence costs more FIRST. Getting this backwards is easy and invisible:
   the first draft of the case above returned the rewrite's skip and buried
   the deletion under it, and only a test written for the combined state
   caught it.

5. **Give each skip its own sentence, and make them un-confusable.** Assert
   it: each reason must contain a claim the other does not.

   ```python
   def test_the_two_reasons_cannot_be_mistaken_for_each_other():
       assert "REWRITTEN" in changed and "REWRITTEN" not in absent
       assert ".gitignore" in absent and ".gitignore" not in changed
   ```

6. **Quarantine the old guard as a test fixture, do not delete it.** Copy
   the defective helper verbatim into the test file, take its inputs as
   arguments, and assert the differential on the state it got wrong. Nine
   lines, and the falsification re-runs on every suite run instead of
   living in a scratch directory that gets thrown away.

   ```python
   def _old_guard(root, census_path):
       """<file>'s round-N helper, VERBATIM apart from taking its paths."""
       ...

   def test_the_old_guard_skipped_the_state_that_must_stay_red(tmp_path):
       root = _drifted_tree(tmp_path)
       assert _old_guard(root, census) is not None      # old: skip
       assert new_skip_reason(root) is None             # new: run, go red
   ```

7. **Pin the single home.** Copies come back. Declare the files allowed to
   contain the guard, with a written reason each, and check the set — the
   quarantine copy is one of the declared entries, not an exception to the
   rule.

   ```python
   HOMES = {"lib/guard.py": "the reader",
            "tests/test_guard.py": "the quarantine; never called on the live tree"}
   ```

8. **Run the suite in the environment the wrong sentence appeared in.**
   A fresh `git worktree add --detach /tmp/wt HEAD` (or a clean container)
   and `pytest -rs`, and READ the skip lines. The reason strings are the
   deliverable; a green run proves nothing about them.

## Pitfalls

- **Fixing the wording and leaving the condition.** The misleading sentence
  is the symptom people notice; the swallowed state is the defect. If you
  only re-phrase, the check is still quiet in the case that matters.
- **An anchor-free pin matches its own text.** `assert "def _old_guard" not
  in src` over a directory that includes the test file matches the
  assertion's own string literal — the test then passes with the subject
  deleted. Anchor it (`re.compile(r"^def _old_guard\(", re.M)`), and assert
  the quarantine copy still exists as a separate claim.
- **Emptying an exemption list instead of closing it.** If a state stops
  being exempt, an empty list makes every "for each exemption" test
  vacuously true. Assert the list is empty AND that the case has a named
  home elsewhere, with the home read from disk rather than cited in prose.
- **Building the drift fixture from the wrong bytes.** A fixture tree whose
  files are placeholders reads as *changed* against the real frozen record,
  so tests meant to exercise *missing* accidentally exercise *changed*.
  Generate the fixture's own record from the bytes you wrote.
- **Monkeypatching after you measure.** In a test that redirects the guard's
  data source, the redirect must be in place before the first predicate
  call, or an early assertion silently runs against production data and
  passes for the wrong reason.
- **Treating "same six lines in two files" as the whole problem.** Merging
  two copies of a wrong guard produces one wrong guard. Decide the states
  first; the deduplication is what makes the decision enforceable, not what
  makes it correct.

## Verification

Each of these must produce the stated shape of output.

```bash
# 1. every state has a test, and the names say which state
grep -n "def test_" tests/test_<guard>.py
#    expect one per row of your step-1 table, including the combined state

# 2. the falsification runs, and it is a differential
pytest tests/test_<guard>.py -q -k old_guard
#    expect: passed — and the test body must call BOTH the old and new guard

# 3. no second copy of the guard
grep -rnE "^def _<old guard name>\(" --include=*.py .
#    expect: no output (the quarantine copy is renamed, e.g. _old_*)

# 4. the reasons are distinguishable
pytest tests/test_<guard>.py -q -k reasons_cannot_be_mistaken

# 5. the sentence is right in the environment that produced the wrong one
git worktree add --detach /tmp/<scratch-worktree> HEAD >/dev/null
cd /tmp/<scratch-worktree> && pytest tests/ -q -rs 2>&1 | grep SKIPPED
#    READ them. Each must name the cause that is actually true there.
git worktree remove /tmp/<scratch-worktree>

# 6. the live tree still RUNS the checks (a guard that skips everywhere is
#    the same defect with the sign flipped)
pytest tests/ -q -rs 2>&1 | tail -1
```
