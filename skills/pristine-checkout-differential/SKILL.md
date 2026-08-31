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
   git worktree add --detach /tmp/pristine-$$-$(date +%s) HEAD
   ( cd "$WT" && <the exact suite command> )
   ( cd .     && <the exact suite command> )
   git worktree remove --force "$WT"
   ```

   **Name the worktree so that no other path can prefix-match it.** This is
   not tidiness. Round 409 lost a real finding to it: a repo checked out at
   `/tmp/wt-408` was compared against a fake pristine tree at `/tmp/wt`, and
   the harness that decides "which tree is this call in?" answered by
   `"@/tmp/wt" in joined_string`. `/tmp/wt-408/languages/whence` contains
   `@/tmp/wt`. Both trees got the pristine tree's canned failure, the
   `git_incomplete` finding collapsed into `both_failed`, and the suite was
   green in the live tree and red in the worktree at the same commit for 53
   rounds. **A short, human-typed worktree name is a prefix of the next one
   you type.** Prefer `$$`/timestamp suffixes, and compare paths by
   components (`a == b or a.startswith(b + os.sep)`), never by `in`.

   **Say WHICH suite, every time.** A repo with more than one test tree has
   more than one baseline, and the fast script for one subsystem is not a
   baseline for another. Round 402 published a standing recipe — "`git
   worktree add --detach /tmp/wt-N HEAD` and run it THERE" — that named no
   suite; round 408 followed it with `harness/run_tests_fast.sh`, which runs
   `harness/tests/` and nothing under `languages/whence/`, so three of that
   round's eight red tests were invisible to the check that was supposed to
   see them. Register the suites by name (see `pristine_check.py:SUITES`) so
   the choice is made once and cannot be forgotten under time pressure.

   **A baseline is not a differential, and refusing to run it in a dirty
   tree is why people hand-roll this.** Step 1's clean-tree rule is correct
   for the *comparison* and wrong for the question "what does this COMMIT
   do?", which is what a round asks before it starts editing and still needs
   answered after it has. Provide both: a gated `check` and an ungated
   `baseline` that runs the pristine tree ALONE and records the live tree's
   dirt as a caveat rather than a veto. Every hand-rolled worktree in this
   repo's history was someone routing around the missing second mode — and
   hand-rolling is what produced both defects named above.

   **Before attributing a pristine-only failure to git, change the
   worktree's NAME and run it again.** One extra checkout, seconds, and it
   separates two causes that look identical: "this commit does not carry
   what the test needs" and "this test is sensitive to where it was checked
   out". Round 409:

   ```
   ( cd /tmp/wt-409       && pytest -q harness/tests/test_pristine_check.py )  # 1 failed
   ( cd /tmp/pristine-409 && pytest -q harness/tests/test_pristine_check.py )  # 67 passed
   ```

   Same commit, same command, two verdicts — so the dependence is the
   directory NAME, and no amount of reading the diff would have found it.
   A failure that survives the rename is about the commit; one that does not
   is about your environment, and reporting it as a finding costs the next
   round a paragraph of disproof. Round 408 reported five reds from a
   hand-made worktree: four were the ignored-corpus pitfall below and the
   fifth was this, and it characterised neither.

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
- **An IGNORED corpus makes every worktree red at every commit, forever.**
  The dual of the pitfall above it. If a test reads files that are named in
  `.gitignore`, it does not fail "in a fresh clone" — it fails in *every*
  checkout of *every* commit, including the pristine tree this check builds,
  so the check itself reports a permanent, false `git_incomplete`. Round 402
  ignored fourteen gateway-written `.lang` files for a good reason; four
  tests that read them off disk then failed in every worktree, and because
  nobody had run that tier from a worktree for seven rounds, the repo's own
  differential instrument was quietly disabled by its own `.gitignore`.
  The fix is a SKIP with a reason that names the cause — and it must be
  **all-or-nothing**: none of the corpus present means "this checkout was
  never the tree that has it", so skip; *some* present means real drift, so
  stay red. A skip keyed on "any file missing" swallows the deletion you
  built the corpus check to catch.
- **A test double that tells two trees apart by a path substring will
  eventually be fooled by where the repo is checked out.** The instrument's
  own default path is usually collision-proof, so the instrument can never
  provoke the bug — only a human following the recipe can, which means the
  failure appears in exactly the situation where it is read as a finding
  about the code under test. Pin the case with an explicit `repo=` argument
  so it is red or green identically in every checkout, rather than leaving
  it reachable only from a particularly-named directory.
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

Round 409 (harness A), the ungated second mode, first run, at `d71d7cd`
with seven tracked files dirty — a tree in which `check` refuses to run at
all:

```
$ python3 harness/pristine_check.py baseline --ref HEAD
baseline  HEAD (d71d7cd36c81)  verdict=red
  NOTE: taken while the live tree had 7 tracked-modified and 0 untracked
        path(s) — the baseline is of the COMMIT, not of that tree.
  harness-fast   green      269 deselected, 961 passed (98s)
  whence-fast    red        81 deselected, 4 failed, 1933 passed, 10 skipped (89s)
      FAILED tests/test_field_corpus_selector.py::test_ten_of_the_fourteen_still_fail_to_parse
      FAILED tests/test_field_corpus_selector.py::test_the_census_and_the_directory_still_agree
      FAILED tests/test_field_corpus_selector.py::test_the_live_tree_has_no_drift
      FAILED tests/test_v24.py::test_the_tracked_example_set_is_the_one_this_repo_decided_on
```

Those four are the ignored-corpus pitfall above, reproduced exactly: green
in the live tree, red at the same commit in any checkout. Note also what
this run does NOT show — `harness-fast` is green here while the same tier
was red in a hand-made `/tmp/wt-408`, because this command's own worktree
path (`/tmp/pristine-check-<pid>-<ts>`) cannot prefix-match, which is the
substring pitfall from the other side: **the instrument was structurally
incapable of finding the bug in its own test double.**

## Related

- [[copied-mirror-drift]] — the sibling failure where a second copy of a
  rule stops tracking the first. This skill's fix creates exactly such a
  copy on purpose (VCS enumeration in two places), and the differential is
  what makes that safe: divergence surfaces as a pristine-only failure.
- [[carried-claim-rot]] — a floor read off a live directory is a number
  nobody re-derives. Step 8 is that skill's rule applied to a threshold.
- [[deleted-vs-never-written]] — when a pristine-only failure looks like a
  missing file, that skill separates "removed" from "never committed".
