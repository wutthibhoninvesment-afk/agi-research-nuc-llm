---
name: gate-attributes-what-the-change-introduced
description: Use when moving an existing whole-artefact check — a linter, a complexity or escape scan, a schema validator — to the moment of authorship (pre-commit hook, pre-push step, PR bot) so a defect's author hears about it while they can still fix it. The scan is already correct; what is missing is ATTRIBUTION, because scanning a touched file reports the lines the author inherited alongside the one they wrote. NOT for a checker nothing invokes (unrun-checker-latency) nor a scheduled red that routes to nobody (finding-must-reach-an-actor). Symptoms: an author-time check people skip; "that warning is always there"; a hook whose output is mostly about someone else's code; a gate proposed on a scan whose historical false-positive rate was never measured. Covers replaying the scan over every commit that touched the subject, splitting each firing into introduced vs inherited, an identity key surviving a line shift, keeping the gate advisory, and pinning recall on real episodes and on changes written correctly.
---

# A gate that blames you for someone else's line gets switched off

You have a correct check. It runs somewhere useful but late — a nightly job,
a suite in a tree the author does not run, CI after merge. The defect it
finds keeps recurring, so the obvious move is to run it earlier, at commit
time, where the author is still present.

The obvious move has a trap. The check scans an **artefact**; a commit
touches a **file**. Run the artefact scan over each touched file and it
reports every finding in that file — including the ones that were there
before the author opened it. The author reads a warning about a line they
did not write, on a commit that did not make anything worse, and learns that
the hook is noise. After that it does not matter how right the check is.

The fix is not to soften the check. It is to make the gate report only the
**delta the change introduces**, and to prove that with a replay before the
gate is wired to anybody.

## Trigger conditions

- You are about to put an existing whole-tree scan into a pre-commit hook,
  pre-push step, or PR bot.
- A hook already exists and people have a habit of ignoring one of its steps.
- Someone says "that warning is always there for this file".
- A defect class has recurred three or more times, each instance introduced
  by a change whose own test suite stayed green.
- You are arguing for an author-time gate with "this would have caught it"
  and no number.
- A gate is proposed as **blocking** on a check whose historical
  false-positive rate has not been measured.

## Steps

1. **Find the real episodes first, from version control, not from the issue
   tracker or a retention-limited log.** Retained CI/health logs usually know
   fewer recurrences than the history does. List every commit that introduced
   the defect: `git log -S '<the exact spelling>' -- <subject>`, then confirm
   each by checking who closed it.

2. **Replay the scan over every commit that ever touched the subject.** For
   each such commit, scan the post-commit content of the files it touched:

   ```sh
   git log --format=%H --diff-filter=ACMR -- '<subject>/*.<ext>'
   # per commit: git show <sha>:<path> | <the scan>
   ```

   Record, per commit: how many files were in scope, how many findings, and
   which files. Write it to a JSON artefact — the numbers below are the
   argument for the gate and they should be re-derivable.

3. **Split every firing into INTRODUCED and INHERITED.** For each firing
   commit, run the same scan on the file at the commit's **parent** and
   subtract. A file absent at the parent inherits nothing, so every finding
   in an added file is introduced.

4. **Choose the finding identity deliberately, and do not put the line number
   in it.** Adding an import above a finding shifts its line; a line-keyed
   identity reports that edit as new and reintroduces exactly the noise you
   are removing. Key on (file, the offending expression/text, kind). Write a
   test for this — it is the single easiest thing to regress.

5. **Report the two rates side by side and let them decide the design.**

   | | commits that fire | findings | commits firing ONLY on inherited lines |
   |---|---|---|---|
   | whole touched file | … | … | ← this number is the noise |
   | minus the parent/HEAD | … | … | should be 0 |

   If the second row does not preserve recall on the real episodes from
   step 1, differencing is wrong for this check and you have learned that
   cheaply.

6. **Pin recall AND the controls.** Test that the scan fires on each real
   historical episode, replayed from git. Then test that it does **not** fire
   on the changes in the same window that were written correctly. A recall
   test alone cannot tell a check from `return True`.

7. **Keep it advisory, and test that it is.** An author-time gate can refuse
   the commit of someone with no time left to debug it, and losing the whole
   change is worse than one more instance of the defect. End the step in
   `|| true`, fail open on any infrastructure trouble, and write a test that
   asserts the step cannot block — so a later "let's strengthen this" has to
   read why.

8. **Stay silent when there is nothing to say.** Most changes touch nothing
   in the subject. A scan of zero files must exit 0 and print nothing. This
   is the opposite of the whole-tree mode, where a scan that read nothing is
   a broken invocation rather than a pass — if one program has both modes,
   test that they differ here.

9. **Edit the hook's TRACKED generator, never the hook file.** `.git/hooks/`
   is not in version control. A step added directly to the hook is invisible
   to every other checkout and is silently clobbered by the next install.
   Find whatever writes the hook, add the step there, reinstall, and pin the
   full ordered step list in a test so deleting one is a failure.

10. **Say what the author's own suite will do.** The whole reason the gate is
    needed is that the check lives where the author does not look. One line —
    "this reddens `<suite>`, which your track does not run" — is the
    difference between a warning and a warning that closes the loop.

## Pitfalls

- **Measuring the gate on the current tree.** If the tree is clean today,
  every design looks equally quiet. The historical replay is the only place
  the noise is visible.
- **Scanning the worktree instead of the staged blob.** They differ exactly
  when the author staged one version and kept editing, and the staged one is
  what lands. Use `git show :<path>`.
- **Reimplementing the scan for the incremental mode.** Two implementations
  of the same arithmetic drift, and a commit-time check that disagrees with
  the suite trains the author to ignore it. Factor out one per-file function
  and test that both modes agree on the same input.
- **Passing repo-relative paths to a scan whose arithmetic is relative to a
  subtree root.** Every depth shifts by the root's depth and the check
  answers a different question without erroring.
- **Blocking because the defect is "serious".** Seriousness is an argument
  for the check, never for the gate's exit code.
- **Counting recurrences from retained logs.** They roll over. The history
  does not.

## Verification

Run all of these; each should be a command, not a judgement.

```sh
# 1. The two rates, from the replay artefact you wrote in step 2/3.
python3 -c "import json,sys; r=json.load(open(sys.argv[1])); \
  f=[x for x in r if x['n_findings']]; \
  print('fire', len(f), 'noise-only', sum(1 for x in f if x['n_new']==0), \
        'findings new/inh', sum(x['n_new'] for x in f), sum(x['n_inherited'] for x in f))" \
  <replay.json>
# PASS when noise-only is 0 after differencing.

# 2. Recall on the real episodes, and silence on the correct controls.
pytest <suite> -k "real_episodes or written_guarded" -q

# 3. The gate is silent and green on a change that touches nothing.
git stash -u >/dev/null 2>&1 || true; <the --staged command>; echo "exit=$?"
# PASS on exit 0 and no output.

# 4. The gate speaks, names the file AND the line, on a staged instance.
#    (create a scratch file carrying the defect, `git add` it, run, `git reset`)

# 5. The installed hook matches its tracked generator, and every step is
#    still there in order.
pytest <hook suite> -k "steps_in_order or cannot_refuse" -q
```

## Worked instance

Round 515 of this program. `harness/swe/copyparity.py escapes` finds path
expressions in `languages/whence` that reach above the subtree and break when
the tree is copied into a sandbox. Its verdict is asserted by three nodes in
`harness/tests/test_swe_copyparity_real_subject.py` — a tree that
`languages/whence/run_tests_fast.sh` does not run. Four rounds (464, 504,
507, 512) shipped the defect and four SWE-loop(D) rounds (467, 505, 509, 515)
closed it; round 512 had *read* the read-set instrument's output in the same
commit and declined the fix on ownership grounds.

Replay over all 137 commits that ever touched a `*.py` there: a whole-file
staged scan fires on 25, **72 of its 120 findings are inherited**, and **8 of
the 25 commits introduce no escape at all**. Subtracting HEAD leaves 17
firings, 48 findings, 0 noise-only commits, and keeps 4/4 of the real
episodes — every one was an added file, so it inherited nothing. Written up
in `knowledge/round-515-the-instrument-that-was-opt-in.md`; artefacts in
`state/swe/round-515/`.
