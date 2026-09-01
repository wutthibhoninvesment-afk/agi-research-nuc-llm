---
name: unrun-checker-latency
description: Use when a repository owns a correct checker — a linter, an audit script, a consistency check, a live-corpus test — that nothing invokes on a schedule, so it only runs when someone remembers. NOT for a requirement documented but implemented by no tool (that is unenforced-documented-rule); here the tool exists and only its invocation is missing. Symptoms: a checker is red the moment you run it by hand and nobody knew; a checklist says "run X before shipping" and no job runs X; violations are found by whoever next touches the area, not by the change that caused them. Covers running every checker the repo owns right now, replaying git history against each commit's OWN checkers to measure how long violations survived, splitting a real ERROR from a knowingly carried WARNING, enumerating every enforcement surface rather than the obvious one, and installing a runner whose exit code cannot cry wolf.
---

# A checker that nothing runs has a detection latency, and you can measure it

A repo accumulates checkers faster than it accumulates ways to run them. Each
one is written by someone fixing a real problem, is correct on the day it
lands, and is then invoked by convention — a checklist line, a habit, "the
person who owns that area runs it". Convention has a latency, and nobody
knows what it is, so the argument for automating it is always a hunch.

It is measurable, and the measurement usually surprises. The interesting
number is not "how many violations are there" (often very few) but **how long
each one survived, and what would have found it**.

## Trigger conditions

- You ran a repo's own linter/audit/check by hand and it was **red**, and the
  breakage predates you.
- A checklist, CONTRIBUTING.md or docstring says "run X before shipping" and
  nothing in CI, a pre-commit hook, or a scheduled job runs X.
- A violation was found by the next person to touch the area rather than by
  the change that introduced it — twice.
- Someone proposes adding a sixth checker to a repo where nothing runs the
  first five.
- You are about to argue for automation with "this could catch bugs" instead
  of a number.

**When NOT to use:** the checker does not exist yet (write it first); the
checker is priced or slow enough that running it per-change is genuinely the
wrong call (then the deliverable is a *baseline file* naming who owes each
deferred run, not a runner); the rule is documented but no tool implements it
(that is a different job — see `unenforced-documented-rule`).

## Steps

1. **Run every checker the repo owns, right now, over the live tree.** Not
   the test suite — the checkers. Find them by looking for scripts whose
   output is findings rather than results, and for tests with "live" or the
   repo's own name in them.
   ```bash
   git ls-files | grep -E '(lint|check|audit|verify).*\.(py|sh|js)$'
   ```
   Record what is red *before* you change anything. This is the discovery,
   not the measurement, and it is the only step that cannot be deferred.

2. **Enumerate the enforcement SURFACES, plural.** A checker script is one.
   A unit test asserting a property of the live tree is another, and it is
   the one that gets missed, because it looks like a test rather than like a
   check. Grep for tests that read the repo itself:
   ```bash
   grep -rln "REPO_ROOT\|repo_root()\|live" --include='test_*.py' .
   ```
   A runner covering only surface one will ship green over a red surface two
   on the day you build it.

3. **Replay history against each commit's OWN checkers.** For every commit
   that touched the checked area, materialize that tree and run *that
   commit's* version of *that commit's* checkers against it. This answers
   "did a change ship a state its own tooling rejected?", which is the only
   question a fix is accountable to.
   ```bash
   git log --reverse --format='%H %ad %s' --date=short -- <area>/
   git archive <sha> -- <paths> | tar -x -C "$TMP"
   ```
   Detect each historical version's supported flags **from its source**, not
   by running `--help` — you are about to execute N versions of a script
   nobody in this session has read, and a script with no argv parsing runs
   its main effect on any argument.

4. **Run the second view separately: today's checkers over every historical
   tree.** This is rule TIGHTENING, not rot. A commit that predates a rule
   was not red, it was ungoverned. Keep the two numbers apart and label them;
   merging them turns "we added a rule" into "history was broken".

5. **Split ERROR from carried WARNING before quoting any number.** A
   `--strict` mode that fails on warnings makes both look like `rc=1`. In a
   healthy repo a warning is usually a *deliberately carried debt*, tracked
   and re-decided every cycle. The first draft of this analysis will report
   one big red number; the useful report has two, and the ratio between them
   is itself a finding.

6. **Count episodes, not commits.** Group consecutive red commits into
   maximal runs. Report each episode's length, the change that OPENED it, the
   change that CLOSED it, and whether it is still open. "17 red commits" and
   "two episodes, one of them known" describe the same data and lead to
   opposite decisions.

7. **Look for the shape that recurs.** If several episodes share a code, ask
   who opens them and who closes them. A pattern like "opened by any
   contributor, closed only by the one who owns that area" *is* the latency,
   stated as a mechanism instead of a duration.

8. **Install the runner, and let its exit code ignore warnings.** Errors set
   the code; warnings ride in the summary line so a carried debt stays
   visible without ever making the signal cry wolf. A check that fails every
   run for a debt the team has decided to carry gets ignored, then
   uninstalled — which is worse than never installing it.

9. **Wire it in the same change that builds it.** Splitting "build the
   script" from "run the script" across two changes reproduces the exact
   defect being fixed, and the gap is never as short as intended.

10. **Guard against re-entry.** If the runner runs the test suite, and the
    suite contains a test that invokes the runner, that is an infinite
    regress. Use an environment variable rather than a flag — it has to
    survive being reached through a test framework whose argv no caller
    controls.

### Find them by CLOSURE, not one at a time

The steps above start from "you already suspect this checker is unrun". The
harder failure is the one nobody suspects, and it has a mechanical answer:
**compute what the automation actually reaches, and subtract.**

Build one graph. Nodes are the repo's runnable files; an edge `A -> B` means
A's *code text* names B; take the transitive closure from the entry point the
scheduler invokes. Everything outside the closure is code no automatic run
touches, by any route. Five rules make the difference between a graph that
answers the question and one that answers a different one:

1. **Strip comments first.** A scheduler script that documents itself names
   instruments it does not run. Measured on a 49.6 KB driver script and the
   tree around it: **22 nodes, 16 of them entry points, were reachable ONLY
   through commentary** — and one of the 16 was the single real orphan the
   audit found. Commentary makes things look covered, so a whole-text grep
   fails in the direction that hides the finding.
2. **A basename is not an identity.** Match the longest path-component suffix
   that resolves and refuse to fall through to a shorter one; report a
   multi-match as *ambiguous* and never as an edge. Two pairs of health-check
   scripts in that tree share a basename, and 771 ambiguous references were
   recorded during one closure.
3. **A directory is an edge only when a TEST RUNNER is pointed at it.**
   Gating on "any directory named in code" pulled a data directory created by
   `mkdir` into the closure (+107 files); gating on "any interpreter token on
   the line" let `python3 audit_tool.py audit src/` through, because the
   directory belongs to the audited program, not the interpreter (+158 files,
   and six correct declarations flipped to errors). Naming `pytest` exactly is
   both more accurate and more honest than a list of interpreter names.
4. **A relative path is relative to the referrer.** A script that `cd`s to its
   own directory and then says `pytest tests/` is unresolvable globally when
   five `tests/` directories exist. Try the referrer's own directory first,
   exact match only.
5. **A dotted module name resolves against an ANCESTOR of the importer.**
   Tests that do `sys.path.insert(0, parent)` then `from pkg import mod` are
   the normal case. Without this rule the audit reported the newest instrument
   in the tree — built two rounds earlier, with its own passing test file — as
   an orphan, which is the one false positive that would have made the whole
   check unusable.

### Weight the edges, or "reached" will mean the opposite of what you think

Not every route in is equal. Rank them: an import or a `-m module` invocation
is strong; a directory handed to a runner, or a path *constructed* by
`os.path.join`/`pathlib`, is medium; a bare textual mention is weak. Then warn
on any artefact whose best route in is a bare mention **from inside a test
file**, because that is routinely evidence of the opposite:

    self.assertManual("python3 bench_elision.py", "expensive")
    self.assertManual("python3 live_smoke.py cli-guards", "priced")

Those two lines were the only thing in the tree naming either file, and they
exist so that nothing runs them automatically — one of the two spends money.
Being named in a refusal is not being run. The same shape appears in exclusion
lists: a constant `FROZEN_PREFIXES = ("state/swe", ...)`, listing the
directories a checker refuses to scan, reads to a naive matcher as a list of
directories to run.

Splitting *constructed* paths from *mentioned* ones is what makes this usable:
before the split, three of five warnings were files genuinely executed by
their tests through `spec_from_file_location` and `subprocess.run`. After it,
two of two were real.

### Declare the answer in three states, not two

A `wired`/`unwired` registry over every entry point produced **eleven
permanent warnings** for operator tools, benchmarks and scripts that talk to a
live service and must never fire unattended — and a check that warns every
cycle for a state the project chose gets ignored and then uninstalled. A third
status, `manual` ("outside the closure, and that is the answer, not a debt"),
left exactly two real debts under those eleven. Only the debt status carries an
owner and a date, and only it can raise the age warning.

## Pitfalls

- **Reporting one red number.** ERROR-red and strict-warning-red have
  opposite meanings — "nobody knew" versus "we decided". The first version of
  this analysis will merge them; that is the same failure the analysis exists
  to find, committed by the tool doing the finding.
- **Replaying with today's checkers and calling it history.** It measures how
  much the rules tightened, which is real but is not "the repo was broken for
  N commits". Report it, label it, never merge it.
- **Treating a checker that could not run as green.** A version whose flags
  changed, a crash, a timeout — each needs its own outcome. A silent
  `rc != 0 -> not green` collapse is fine; `exception -> skip` is not.
- **Covering only the checkers and missing the tests.** The most-embarrassing
  red thing in the tree is usually an assertion inside a test file, because
  it does not look like a check.
- **Assuming the fix is urgent because the finding was surprising.** If the
  measurement says two ERROR-red commits in fifty-nine, say so. The honest
  case for the runner is that it *bounds* a latency nothing else bounded, not
  that violations are frequent.
- **Allowlisting a red assertion without reading why it went red.** "Add it
  to the known-exceptions set" and "the parser silently returned nothing" look
  identical from the outside. Confirm the mechanism, then allowlist.
- **Running `--help` on historical scripts to detect flags.** Read the
  source. Some scripts have no argv parsing and do their work regardless.
- **The handoff between "who builds the checker" and "who wires it" is
  where the latency actually lives.** A checker written by the team that
  owns the SUBJECT and wired by the team that owns the RUNNER is two
  tickets, and the second one is invisible: the first ticket closes green,
  the checker exists, it is documented, and `grep -c` for its name returns
  zero. Measured on one repo, three instances of the same handoff: 5 rounds
  (built 242, wired 247), **21 rounds** (built 388, wired 409 — carried in
  the standing next-steps for six consecutive rounds with 0 references
  in-tree), and 0 rounds (built and wired by round 363, which noted the
  deferral was "exactly the 'documented but nothing runs it' shape being
  fixed"). Prefer building and wiring in one change. When you genuinely
  cannot, make the unwired state VISIBLE — the check that catches this is
  `grep -c <script-name> <runner>` returning 0, and it costs nothing to
  automate.
- **Wiring a check without extending the ignore/attribution rules its
  output needs.** A per-run check writes a per-run artifact. If the repo
  has a `.gitignore` pattern, a record-gap check or a log-attribution rule
  covering the checks that already exist, the new one needs a line in each
  — in the SAME change. Otherwise the next run's log lands as an
  unattributed untracked file and trips a different checker, and the
  cleanest new instrument's first act is a false alarm.

## Verification

```bash
# 1. the runner is red on a corpus you broke on purpose, and names the rule
<runner>; echo "rc=$?"          # expect: rc=1, the violated code in output

# 2. the runner is GREEN with a warning present — warnings must not fail it
<runner> | tail -1              # expect: "... 0 error(s), N warning(s)", rc 0

# 3. a checker that cannot run is ERROR, not FAIL
#    (break one checker's invocation and confirm the wording differs)

# 4. every surface is actually covered — count them from the output
<runner> | wc -l                # expect: one line per checker + summary

# 5. the history replay is reproducible and its two views disagree
<replay> own   --json own.json  | grep -E 'ERROR-red|strict-red'
<replay> today --json today.json | grep -E 'ERROR-red|strict-red'
#    expect: today's ERROR-red count >> own's, and that gap is rule
#    tightening, not rot

# 6. re-entry terminates
<runner>                        # expect: finishes; no nested-process chain
```

Worked example, with every number and both misses:
`knowledge/round-363-the-corpus-had-five-checkers-and-nothing-ran-them.md`.

Round 415 built the closure described above (`harness/wiring_audit.py`) and
ran it on this repo: **108 entry points declared, 82 wired, 24 manual, 2
unwired**, `0 error(s), 0 warning(s)`, 7.27 s, 47 unit tests. The two debts it
found were both OLD — one is a track's own `-m` entry point whose test file
imports its four collaborators and never it, the other had ZERO references of
any kind and a delete-as-dead-end recommendation from 243 rounds earlier.
Nothing built in the previous 40 rounds was orphaned, so the value of the
sweep was in the aged tail, not the recent work.
