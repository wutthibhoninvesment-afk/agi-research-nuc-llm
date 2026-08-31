---
name: replay-scope-is-read-scope
description: Use when replaying a checker, linter, policy or audit script over git history to ask "how long was this broken?" — and the replay's answer must be trusted. A history replay silently substitutes three things for the real question - the commits it selects for the commits that matter, the tree it materializes for the tree the checker reads, and the checkers it happens to run for the checkers that exist. Symptoms - a replay reports a long "STILL OPEN" episode nobody has ever seen live; a live check fails on codes the replay has never once emitted; a replay says green for a round everyone remembers going red; a violation that lives in an untracked or gitignored file. Covers deriving the commit filter from the checker's READ-set rather than its home directory, quarantining codes whose inputs version control cannot supply as ungovernable rather than red, joining a replay against an append-only live log, and checking a declared input list against the thing that generates it instead of re-listing its members.
---

# A replay measures the tree it can rebuild, not the one that failed

## Trigger conditions

Trigger on any of these:

- You are about to answer **"how long has this been broken?"** by replaying a
  checker over `git log`, and the number will be used to justify work.
- A history replay reports an **episode nobody recognises** — a long run of
  red commits, often reaching HEAD and rendered "STILL OPEN", that no live
  run has ever reproduced.
- A **live check and a history replay disagree**, in either direction, and
  nobody has computed the intersection of what they report.
- The checker reads inputs that are **gitignored, untracked, or generated** —
  probe reports, caches, build outputs, credentials, anything under a
  `.gitignore` line.
- A replay's commit filter is a **directory** (`git log -- tools/`,
  `-- lint/`) and you have not checked that the directory is where the
  checker's *inputs* live.
- You inherited a replay tool and want to know whether its headline number
  is still true.

Do NOT reach for this when the checker is cheap to run live on the current
tree and history is not the question — just run it. This skill is about the
honesty of a **historical** number.

## The three substitutions

A replay never answers "was this broken at commit C". It answers "is the
checker I chose to run, red on the tree I could rebuild, at the commits I
chose to look at". Three substitutions, each silent:

| you asked about | the replay used | fails when |
| --- | --- | --- |
| the commits that matter | commits touching the checker's **home directory** | inputs live elsewhere |
| the tree the checker reads | the paths `git archive` was asked for | an input path is omitted or ignored |
| the checkers that exist | the ones hard-coded when the tool was written | a checker is added later |

Each substitution has a signature. The first makes episodes **invisible**.
The second and third make findings **wrong in both directions** — a missing
input reads as a violation, and a missing checker reads as green.

The direction that gets shipped is the dangerous one: **an absent input does
not report as `absent`, it reports as a violation.** A checker asked "does
this bank exist?" against a tree that never contained the bank says *no*, and
*no* is its failure verdict.

## Steps

1. **Get the checker's read-set from the checker, not from memory.** Grep it
   for path construction — `os.path.join(root, ...)`, module constants
   ending `_FILE`/`_DIR`, glob roots, hard-coded relative paths. Do this for
   *every* checker the replay will run.

   ```sh
   grep -n 'os.path.join(root\|_FILE = \|_DIR = \|glob.glob' checker.py
   ```

2. **Compare the read-set against the replay's commit filter, numerically.**
   Not "does it look right" — count.

   ```sh
   git log --oneline | wc -l                      # all commits
   git log --oneline -- tools/ | wc -l            # the replay's filter
   comm -13 <(git log --format=%H -- tools/ | sort) \
            <(git log --format=%H -- data/ | sort) | wc -l   # missed
   ```

   If the third number is not ~0, the filter is wrong. Widen it to the union
   of the read-set.

3. **Compare the read-set against what the replay materializes.** Every
   read-set root must be in the `git archive` pathspec. A root that is in the
   filter but not the archive is worse than one in neither: you select the
   commit and then judge it on a tree that is missing the file.

4. **Find the inputs version control cannot supply.** For each read-set path,
   ask git directly — do not read the `.gitignore` and reason about it.

   ```sh
   git check-ignore -v data/reports/*.json     # prints the matching rule
   git ls-files data/reports | wc -l           # what IS tracked
   ```

5. **Quarantine the codes computed from those inputs as a THIRD status.**
   Not red, not green: **ungovernable**. Report the count separately and
   never merge it into the headline. A code here is one the replay is
   structurally unable to judge, which is a different claim from "the corpus
   was clean".

6. **Prove the quarantine by construction, not by argument.** Extract one
   commit, run the checker, count the findings; copy the untracked inputs in
   from the live tree; run again. If the count goes to zero, the findings
   were missing-input.

   ```sh
   T=$(mktemp -d); git archive <sha> -- <read-set> | tar -x -C "$T"
   python3 checker.py --repo-root "$T" | grep -c ERROR   # before
   cp -r data/reports "$T/data/"
   python3 checker.py --repo-root "$T" | grep -c ERROR   # after
   ```

7. **Enumerate the checkers by re-deriving them, not by listing them.** If a
   live runner already owns the authoritative list, import it and compare
   paths in a test. A hand-copied list is a snapshot; the next checker added
   is invisible until someone notices.

8. **Join the replay against the live log and print the code intersection.**
   This is the measurement that tells you whether the two instruments are
   even looking at the same thing. An append-only log of live verdicts is
   usually the only surviving record of a working-tree failure.

9. **Report `absent` for a round with no commit in scope — never `green`.**
   "The replay saw nothing here" and "the replay saw a clean tree here" are
   different observations and merging them manufactures agreement.

10. **Re-run the replay after every scope fix and re-read the findings.** A
    scope change moves the headline number. If it moved a lot, the old
    number was wrong and anything that cited it needs revisiting.

## Pitfalls

- **A hand-made list of an open set's current members.** This is the root
  cause of most of the above and it recurs at every level: a docstring
  naming today's "safe" codes, an archive pathspec naming today's input
  roots, a tuple naming today's checkers. All three are correct when written
  and silently false the first time the set grows. Nothing re-reads a
  docstring. The fix is never a better list — it is a **test that re-derives
  the list from whatever generates it** and fails when they disagree.

- **Trusting a `.gitignore` line number, or a path's ignore status, from
  prose.** Rules move and patterns are subtler than they look:
  `data/reports/*.json` ignores top-level JSON and leaves every
  subdirectory tracked. Ask `git check-ignore -v` about the exact file.

- **Assuming an omission fails safe.** It fails *loud and wrong*. Budget for
  the fact that widening the tree will change findings you already published.

- **Fixing the scope and not re-reading the old conclusions.** The number
  that justified building something is usually quoted in a knowledge file, a
  README and a docstring. Correcting the tool and leaving three copies of the
  old number is the same rot one level out.

- **Silently suppressing the quarantined codes.** A quarantine that hides
  findings is a mute button. Print the count, name the codes, name the
  gitignore rule, and pin that rule in a test so the quarantine dies when its
  justification does.

- **Assuming the live check is the trustworthy one.** It is not automatically
  right either — it just has a *different* blind spot (it sees only now).
  The point of the join is that neither is authoritative alone.

- **A replay that cannot see a violation is not evidence there was none.**
  "0 red commits" from a tool with an empty intersection against live
  failures means *the tool never looked*, and should be written down that
  way.

## Verification

You have applied this correctly when all of the following hold. Each is a
command, not a judgement:

1. The commit filter is the union of the checkers' read-set roots, and a
   test asserts every read-set root is also materialized:

   ```sh
   python3 -m pytest test_replay.py -k read_set -q
   ```

2. Running the replay prints a **third** count beside red and green, naming
   the codes it covers and the ignore rule that justifies them:

   ```
   ungovernable: N/M commit(s) (rc=1 ONLY from P004,P006,P007,P008 — codes
   whose inputs `state/trigger-eval/*.json` keeps out of every archived tree)
   ```

3. A test reads the real `.gitignore` and fails if the rule the quarantine
   rests on is gone — the quarantine cannot outlive its justification.

4. A test re-derives the checker list from the live runner and fails on
   drift. Confirm it bites by deleting one entry and re-running:

   ```sh
   python3 -m pytest test_replay.py -k checker_set -q   # green
   # remove one checker from the replay set, re-run: MUST fail
   ```

5. A test re-derives the input roots from the artifact that names them (the
   ledger, the manifest, the config) rather than re-listing them.

6. The `live` join prints a code intersection, and you have read it. An empty
   intersection is a finding to write down, not a bug to hide.

7. Every headline number the old scope produced has been re-run under the new
   scope, and any document quoting the old one has been corrected in place
   with the reason.

## Worked instance (round 387, this repo)

`corpus_history.py` replayed **2** checkers over commits touching `skills/`.
`run_checks_fast.sh`, shipped by the **same round**, ran **7** over the
working tree, every round.

- Live failures rounds 364-386: **5** (365, 372, 374, 380, 386). Codes:
  `xref_check` ×2, `carryforward` ×3. **Code intersection with the replay's
  ERROR codes: EMPTY.**
- **4 of the 5** produced no commit under `skills/` at all — reported
  `absent`, not green.
- Commit filter `-- skills/` selected **78** of 281 commits; the read-set
  selected **263**.
- The replay's only open ERROR episode — 10 commits, "STILL OPEN" — was
  `P008`, an ERROR code round 375 added that reads the gitignored probe
  reports. Proven artifact by step 6: 2 findings before the overlay, 0 after.
  The live check said PASS for all ten of those rounds.
- Round 363's docstring said the ERROR codes were "computed from tracked
  files only and ARE faithful" and listed them. True when written; falsified
  twelve rounds later by a round that added a code to the family.
- **This skill's own first draft made the same mistake.** The widened archive
  pathspec listed five roots read off four checkers, omitted `nuc/`, and the
  six-checker replay immediately reported 29 of 40 commits ERROR-red on seven
  `K003 no bank on disk` findings — every one of them an E-round bank in the
  omitted directory, not one a real violation. Step 7's test (re-derive the
  roots from the ledger) is what the list should have had from the start.

Related: [[unrun-checker-latency]] measures how long a violation survives
undetected and is what `corpus_history.py` was built for — this skill is the
audit of that instrument. [[policy-replay-over-history]] replays a *policy*
rather than a checker and shares step 1's discipline. [[measured-exemption]]
and [[content-pinned-acknowledgement]] cover the quarantine's other half: an
acknowledgement that outlives its debt. [[carried-claim-rot]] is the
docstring failure in general form.
