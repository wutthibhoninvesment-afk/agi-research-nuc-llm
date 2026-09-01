---
name: pristine-checkout-differential
description: Use when a test suite has only ever run in the tree it was written in — one working directory, one host, CI that never re-clones — and you need to know whether it passes from version control alone. Symptoms: a test builds its corpus by scanning a directory (glob/listdir/iterdir) instead of asking the VCS; a corpus size floor (`assert len(files) >= 20`) nobody can source; another agent writes into a directory your tests read; long-lived untracked paths in `git status`. Also the SILENT half: a pristine skip count higher than the live one, a test answering a missing fixture with `pytest.skip` so both trees exit 0, a `.gitignore`d corpus a previous fix turned from a red into an invisible skip. Covers `git worktree`, differencing by failing AND skipped node id (`--junitxml`, never `-rs`), the reason-pinned acknowledgement registry that stops it crying wolf, five fail-closed rules, and VCS-derived enumeration. NOT for flaky tests or environment drift — a missing package fails in BOTH trees.
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
   out". Round 409 got `1 failed` in `/tmp/wt-409` and `67 passed` in
   `/tmp/pristine-409` — same commit, same command, so the dependence was
   the directory NAME and no amount of reading the diff would have found it
   (transcript in the verification log). A failure that survives the rename
   is about the commit; one that does not is about your environment, and
   reporting it as a finding costs the next round a paragraph of disproof.

4. **Difference the FAILING TEST IDS, not the pass counts.** Counts move for
   uninteresting reasons (collection differences, a parametrised case count
   that depends on the corpus you are investigating). Node ids do not.
   Normalise separators and any `./` prefix so the same test compares equal
   across two roots.

   **This step used to say "skips" in that list, and that word cost eighteen
   rounds.** Round 427 deleted it. A skip differential is not a count
   differential and it is not noise: it is the SILENT HALF of step 5's
   finding, and the half this skill's own ignored-corpus fix manufactures.

4a. **Difference the SKIPPED test ids, keyed by node id and never by line.**
   A test whose fixture git does not carry has two ways to react to a
   pristine checkout — fail, which step 5 catches, or skip, which nothing
   catches. A skipped test is green at the exit code, green in the summary
   line, and provides no evidence. **Both trees exit 0 and the count line is
   what every reader quotes.**

   `pytest -rs` is the obvious flag and it is the wrong one for this: it
   prints `SKIPPED [1] tests/test_x.py:12: reason`, keyed by FILE AND LINE,
   so inserting an import above the test reports a phantom evaporation.
   `--junitxml` carries `classname` + `name`, which is the node identity,
   and it costs nothing on top of a run you are already paying for:

   ```
   pytest -q --junitxml=/tmp/live.xml <suite>          # outside BOTH trees
   ( cd "$WT" && pytest -q --junitxml=/tmp/pris.xml <suite> )
   ```

   ```python
   import xml.etree.ElementTree as ET
   def outcomes(path):
       out = {}
       for tc in ET.parse(path).iter("testcase"):
           key = (tc.get("classname"), tc.get("name"))
           sk = tc.find("skipped")
           # An xfail is `<skipped type="pytest.xfail">`. It is a test that
           # ran and behaved as declared — counting it here is a permanent
           # false positive in every report you will ever generate.
           if sk is not None and sk.get("type") != "pytest.xfail":
               out[key] = ("skipped", sk.get("message") or "")
           elif tc.find("failure") is not None or tc.find("error") is not None:
               out[key] = ("failed", "")
           else:
               out[key] = ("passed", "")
       return out

   live, pris = outcomes("/tmp/live.xml"), outcomes("/tmp/pris.xml")
   evaporated = [k for k, (st, _) in pris.items()
                 if st == "skipped" and live.get(k, (None,))[0] == "passed"]
   ```

   Write the reports **outside both trees**. In the live tree the report is
   an untracked file that makes step 1's rule block your next run; in the
   worktree it is dirt handed to `git worktree remove`.

   Three cases that look like the finding and are not, all worth encoding
   before you report anything: skipped in BOTH trees (nothing was lost);
   absent from the live run entirely (a test the pristine ref has and you do
   not — it never had evidence here); and failing live, skipped pristine
   (evidence was already absent, and step 5 owns it).

5. **Sort each difference into one of five verdicts**, and never collapse
   them:
   - `git_incomplete` — fails only in pristine. **This is the finding.**
   - `skip_evaporation` — PASSES live, SKIPS in pristine. The same finding
     with the volume turned off: same cause (git does not carry what the
     test needs), no red, exit 0 on both sides. Rank it directly below
     `git_incomplete` and ABOVE the two below, or you have built a checker
     that rewards defending a test with `pytest.skip`.
   - `untracked_breaks_test` — fails only in the live tree. The mirror case:
     a stray file is breaking a test, equally invisible, equally worth
     knowing.
   - `both_failed` — a plain broken test. Not this class; report separately.
   - `inconclusive` — either run did not complete, OR one of them left no
     junit report. A run that produced no skip evidence has not shown that
     nothing evaporated.

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

- **That fix is how you MANUFACTURE the evaporation class, and this skill
  recommended it for eighteen rounds without saying so.** The pitfall above
  converts a `git_incomplete` — loud, exit 1, named in the report — into a
  skip, which step 4's old wording then told you to ignore as count noise.
  The two halves of this document cancelled out. Measured here: round 409
  introduced the guard at 2 test files, closing 4 reds; at round 427 the
  same guard skips **11 tests across 4 files**, and *the growth was never a
  decision* — each new test reached for the sibling's guard because it was
  there. The conversion is still the right fix. **Doing it without an
  acknowledgement entry (below) in the same change is not.**

- **An acknowledgement registry is the only thing that stops this check
  crying wolf, and it must expire by itself.** Once you difference skips,
  every legitimately-absent fixture reports every run, and a checker that
  cries wolf gets ignored. Do NOT suppress on node id — a test can acquire a
  SECOND, unrelated reason to skip, and a name-only allowlist hides exactly
  that. **Pin the skip REASON TEXT**, and report an expired pin LOUDER than
  an unacknowledged skip: it is a skip nobody adjudicated, wearing a
  signature that says somebody did. Three rules, each earned:
  *per node, never per reason* (a NEW test inheriting an acknowledged reason
  must go red — that is how 4 became 11); *print acknowledged entries every
  run* (silent suppression reads as coverage); *an entry matching nothing is
  DEAD and the checker must say so.*
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
- **A baseline that records only counts cannot be re-read.** Round 426 saw
  `14 skipped` against a live `3 skipped` and had to RE-RUN the whole suite
  by hand to learn which eleven, because its record kept a number. Record
  the skip LIST — node id and reason. One tree cannot difference anything,
  so say that too: a baseline reports what it skipped, `check` decides
  whether any of it evaporated.
- **The check costs a full second suite run.** Budget for it. It is a
  periodic or pre-handoff check, not a per-commit one — but its *recorded
  verdict* is free to display, and that is what keeps it honest.

## Verification

Full transcripts of every run cited above, with the mutation checks on the
checker's own rules:
[references/verification-log.md](references/verification-log.md).

- **Round 355** — first finding. `whence-fast` green in the live tree,
  `1 failed, 1191 passed` in a worktree at the same commit: a `glob`-built
  corpus guarded by `assert len(paths) >= 20` in a directory holding 30
  files of which git tracked 16. **A fresh clone had failed the repo's own
  suite for five rounds.**
- **Round 409** — the ungated `baseline` mode, and the substring pitfall
  that made the instrument structurally incapable of finding the bug in its
  own test double.
- **Round 427** — step 4a. Same commit, both suites green, both trees exit
  0, verdict `skip_evaporation`, and **eleven whence tests provided no
  evidence** (`live 3 skipped / pristine 14 skipped`). The same two runs
  under the pre-427 code: `verdict clean`, exit 0. The eleven are round
  402's `.gitignore`d field corpus, reached through the guard round 409
  added to close four reds — 4 call sites then, 11 tests across 4 files now,
  and none of the growth was a decision.

## Related

- [[copied-mirror-drift]] — the sibling failure where a second copy of a
  rule stops tracking the first. This skill's fix creates exactly such a
  copy on purpose (VCS enumeration in two places), and the differential is
  what makes that safe: divergence surfaces as a pristine-only failure.
- [[carried-claim-rot]] — a floor read off a live directory is a number
  nobody re-derives. Step 8 is that skill's rule applied to a threshold.
- [[deleted-vs-never-written]] — when a pristine-only failure looks like a
  missing file, that skill separates "removed" from "never committed".
- [[skip-reason-is-a-claim]] — the adjacent question, and the boundary is
  sharp. That skill asks whether a skip's REASON is true for the case that
  triggered it. Step 4a asks a question that survives the reason being
  perfectly true: a correct skip is still a test that stopped being
  evidence, and nothing counts it. Route a wrong-reason guard there; route
  a right-reason skip that a fresh clone acquires here.
