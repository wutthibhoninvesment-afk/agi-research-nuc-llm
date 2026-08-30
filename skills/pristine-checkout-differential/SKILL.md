---
name: pristine-checkout-differential
description: Use when a test suite has only ever run in the tree it was written in — one long-lived working directory, one host, a CI box that never re-clones — and you need to know whether it passes from version control alone. Symptoms: a test builds its corpus by scanning a directory (glob/listdir/iterdir) instead of asking the VCS what it tracks; a corpus size floor (`assert len(files) >= 20`) whose number nobody can source; another process or agent writes files into a directory your tests read; `git status` shows untracked paths that have sat there for months and nobody sees any more; a suite green every day that has never been checked out clean and run. Covers building the pristine tree with `git worktree`, differencing the two runs by failing node id, the four fail-closed rules that keep the answer interpretable, and the VCS-derived enumeration that fixes the test. NOT for flaky tests, and NOT for environment drift — a missing package fails in BOTH trees, deliberately a different class.
---

# Pristine-checkout differential

A suite you have only ever run in one tree tells you that **the suite passes
in that tree**. That is a weaker claim than anyone reads it as, and the gap
is invisible by construction: the files that make the difference are the
ones version control was never told about, so no diff shows them, no review
covers them, and no failure points at them.

The question this skill answers is narrow and checkable: *if someone cloned
this repo right now and ran the suite, would it pass?*

## Trigger conditions

- **A test enumerates a directory instead of asking the VCS.**
  `glob.glob(d + "/*.ext")`, `os.listdir`, `Path.iterdir`, `find`. The
  moment the directory is writable by anything but the suite's own authors,
  the corpus is whatever happens to be lying there.
- **A magic floor on a corpus size.** `assert len(paths) >= 20`,
  `assert total > 3000`, `--min-cases 26`. Ask where the number came from.
  If it was read off a live directory, it encodes that directory's contents
  — including anything a stranger left in it — as a requirement.
- **Another agent, process or tool writes into the repo.** Codegen, a
  sibling autonomous system, a scratch/output directory that shares a parent
  with a fixtures directory, a downloader that caches next to the inputs.
- **`git status` has long-lived untracked entries.** Paths that have been
  `??` for weeks are exactly the ones nobody sees any more. They are also
  absent from every fresh clone.
- **The suite has never been run anywhere else.** No CI, or CI that reuses a
  persistent workspace and never re-clones. One host, one directory, years.
- **You are about to trust a green run as evidence about the repo** — before
  a release, a handoff, an "is this reproducible?" claim, or an audit.
- Proven on: `languages/whence/tests/test_lexer_guest_parity.py` (round
  355). Corpus built by `glob`, guarded by `assert len(paths) >= 20`, in a
  directory holding 30 files of which git tracked 16. Clean checkout at the
  same commit: `assert 12 >= 20` — a fresh clone had failed the repo's own
  suite for five rounds while every round reported green.

## Why a worktree, and not a clone or a copy

`git worktree add --detach <path> <ref>` materialises exactly the tracked
content of `<ref>` and nothing else, which is what a fresh clone gets, for
the price of one checkout — it shares `.git`, so it does not re-transfer
history. That last property matters more than the speed: **`git ls-files`
works inside a worktree**, and VCS-derived enumeration is the fix this
skill recommends, so the tree you test in must support it.

Do not substitute `cp -r` (copies the untracked files, which is the whole
problem), `git stash` (mutates the tree you are comparing against), or
`git clean -xdn` reasoning (tells you what is untracked, not what breaks).

## Steps

1. **Establish the two trees are comparable before spending any time.**
   `git status --porcelain` must be clean of *tracked* modifications, or the
   runs differ for two reasons at once and no finding can be attributed. A
   pristine-only failure in a dirty tree is as likely to be an uncommitted
   fix as a missing file. Commit first. This ordering is not bureaucracy:
   you cannot ask "does git carry everything?" until your work is in git.

2. **Classify the difference between the trees, in three buckets, not one.**

   ```
   git status --porcelain=1 --untracked-files=all --ignored=matching
   ```
   ` M` tracked-modified (blocks step 1), `??` untracked (the bucket that
   causes findings), `!!` ignored (also absent from a clone, but
   deliberately — a dependency on one of these is usually legitimate local
   state, and conflating it with `??` is how this check starts crying wolf).

3. **Build the pristine tree and run the same suite in both.** Same command,
   same interpreter, same markers — the only intended difference is the
   tree.

   ```
   git worktree add --detach /tmp/pristine HEAD
   ( cd /tmp/pristine && <the exact suite command> )
   ( cd .              && <the exact suite command> )
   git worktree remove --force /tmp/pristine
   ```

4. **Difference the FAILING TEST IDS, not the pass counts.** Counts move for
   uninteresting reasons (collection differences, skips, a parametrised case
   count that depends on the corpus you are investigating). Node ids do not.
   Normalise separators and any `./` prefix so the same test compares equal
   across two roots.

5. **Sort each difference into one of four verdicts**, and never collapse
   them:
   - `git_incomplete` — fails only in pristine. **This is the finding.**
   - `untracked_breaks_test` — fails only in the live tree. The mirror case:
     a stray file is breaking a test, equally invisible, equally worth
     knowing.
   - `both_failed` — a plain broken test. Not this class; report separately.
   - `inconclusive` — either run did not complete. No verdict.

6. **For each `git_incomplete`, find the file it wanted.** Read the failure,
   then `git status --porcelain --untracked-files=all` for candidates under
   the directories that test touches. The assertion usually names it (a
   count, a path, a missing fixture).

7. **Fix by enumerating from the VCS, not by adding the files to git.**
   Committing the stray files makes the symptom go away and leaves the test
   still unable to tell its corpus from anyone else's — and if another
   process owns those files, you have now taken ownership of them.

   ```python
   def corpus(root):
       """Only what git tracks: a directory is not a corpus."""
       try:
           out = subprocess.run(["git", "ls-files", "fixtures"], cwd=root,
                                capture_output=True, text=True,
                                timeout=10, check=True)
           names = sorted(l for l in out.stdout.splitlines()
                          if l.endswith(".dat"))
           if names:
               return names
       except (OSError, subprocess.CalledProcessError,
               subprocess.TimeoutExpired):
           pass
       return sorted(glob.glob(os.path.join(root, "fixtures", "*.dat")))
   ```

8. **Re-derive every floor against the curated corpus and write the number
   down with its date.** The old floor was measured against the polluted
   directory. Measure the new one, put the measurement in the comment, and
   keep it a FLOOR — its job is catching a corpus that silently emptied.

9. **Pin the discrimination, not just the outcome.** A test asserting only
   "the corpus is non-empty" passes again the instant someone reverts the
   fix, because a glob and a `git ls-files` agree in any clean checkout.
   Assert the difference itself:

   ```python
   listed = set(corpus(ROOT))
   assert listed == tracked_set()                 # never more
   extra = on_disk_set() - tracked_set()
   if extra:                    # true on the polluted host, false in a clone
       assert not (listed & extra)
   ```

10. **Verify the pin by reverting the fix, not by reading it.** Put the glob
    back, run the test, confirm it fails, restore. A regression pin nobody
    has seen fail is a comment.

11. **Record the verdict where the next person will see it.** A check that
    must be remembered will not be run. Print the last recorded verdict
    beside the routine test output — cheap (one file read) and it makes the
    gap visible every day instead of once.

12. **Make "no recorded check" print as itself.** Absence of evidence is not
    a pass. An unrun check must never render as green.

## Pitfalls

- **Running the differential in a dirty tree produces a confident wrong
  answer.** The two trees now differ by your uncommitted work AND by the
  untracked files, and nothing distinguishes them. Enforce this as a
  blocking verdict, not a warning.
- **A blanket `--force` to get past that is how the rule dies.** If you need
  an escape hatch, make it name ONE path, so the question "could this file
  have changed the suite's outcome?" is answerable, and record the waiver in
  the output. `git grep -l <path>` over the suite is usually the whole
  proof.
- **A "standing dirty" file will block you forever.** Most repos have one —
  a counter, a lockfile, a generated timestamp that is always modified. It
  needs a registry of paths excused from the blocking rule, separate from
  the escape hatch. Excusing it from the *blocking* rule does not make it
  present in a clone: it stays in the untracked/modified accounting.
- **Ignored files are a different class and mixing them in destroys the
  signal.** `.venv/`, build output and logs are absent from a clone by
  design. If a test needs one, that is a bootstrap-documentation problem,
  not a version-control bug, and reporting it as one trains people to skip
  the check.
- **Environment drift is not this class either.** A missing package fails in
  BOTH trees. That is why `both_failed` is a separate verdict rather than
  being folded into the finding.
- **The suite may write into the pristine tree.** Scratch files, `.pyc`,
  caches. Remove the worktree with `--force`, or the cleanup fails and you
  have leaked exactly the orphan this check is supposed to be disciplined
  about. Remove it on the exception path too.
- **A stale worktree registration outlives the directory.** If a run is
  killed between `add` and `remove`, `git worktree list` keeps the entry and
  the next `add` at the same path fails. `git worktree prune` clears it;
  better, use a unique path per run.
- **A worktree is not a clone in one respect that can bite: hooks and
  `.git/config` are shared.** If the suite depends on a local git config
  value or a hook, the pristine tree still has it and the check will miss
  that dependency. Fixture and corpus dependencies — the common case — are
  covered correctly.
- **Fixing the test by `git add`-ing the stray files is a trap**, twice
  over: the test still cannot distinguish its corpus, and if another system
  owns those files you have adopted them and will now see their churn in
  every diff.
- **Counts are not ids.** "1191 vs 1192 passed" invites you to hunt for one
  test; the FAILED lines name it. And a count differential goes silent
  entirely when one test starts failing as another starts passing.
- **The check costs a full second suite run.** Budget for it. It is a
  periodic or pre-handoff check, not a per-commit one — but its *recorded
  verdict* is free to display, and that is what keeps it honest.

## Verification

Round 355 (harness A), on this workspace, `harness/pristine_check.py`:

```
$ python3 harness/pristine_check.py check \
      --suite harness-fast --suite whence-fast \
      --allow-dirty languages/whence/SECURITY.md
ref HEAD   verdict git_incomplete
  18 untracked path(s) exist here and in no fresh clone
  allowed-dirty (rule 1 waived by hand): languages/whence/SECURITY.md
  harness-fast   clean            live={'passed': 476, ...} pristine={'passed': 476, ...}
  whence-fast    git_incomplete   live={'passed': 1192, ...} pristine={'failed': 1, 'passed': 1191, ...}
      GIT-INCOMPLETE  tests/test_lexer_guest_parity.py::test_small_example_files_lex_identically
```

Step 1's blocking rule, observed rather than asserted — one tracked file
was dirty and the check refused to run until it was named:

```
$ python3 harness/pristine_check.py dirt
tracked-modified 2 (blocking 1)  untracked 18  ignored 456
  BLOCKING  languages/whence/SECURITY.md
```

Step 10, the pin reverted on purpose:

```
$ <put the glob back>; python3 -m pytest -c pytest.ini tests/test_lexer_guest_parity.py -q
FAILED tests/test_lexer_guest_parity.py::test_the_corpus_is_what_git_tracks_and_not_what_the_directory_holds
1 failed, 81 passed in 45.76s
```

Step 8's re-derived floors, measured on the curated corpus (2026-08-30):
12 small files / 3972 tokens, 16 files total / 35188 tokens, 0 divergences.
The floors they replaced were 20 and 26, both unreachable by a clone.

The checker's own rules are mutation-checked, not assumed — dropping the
step-1 short-circuit, forcing "the run completed", dropping `--force` from
worktree removal, and disabling the pristine-only comparison each kill 1-2
of the 49 tests in `harness/tests/test_pristine_check.py`. 4/4 caught.

## Related

- [[copied-mirror-drift]] — the sibling failure where a second copy of a
  rule stops tracking the first. This skill's fix creates exactly such a
  copy on purpose (VCS enumeration in two places), and the differential is
  what makes that safe: divergence surfaces as a pristine-only failure.
- [[carried-claim-rot]] — a floor read off a live directory is a number
  nobody re-derives. Step 8 is that skill's rule applied to a threshold.
- [[deleted-vs-never-written]] — when a pristine-only failure looks like a
  missing file, that skill separates "removed" from "never committed".
