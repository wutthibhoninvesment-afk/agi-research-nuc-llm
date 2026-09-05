# Round 515 (SWE-loop D) — the instrument that was opt-in

**Date:** 2026-09-05 · **Track:** D (autonomous SWE — the harness ON our own code)
**Predictions banked before measuring:** `state/swe/predictions-d-round515.md`,
committed at `0e6458d` before a single number below was measured.

---

## 0. The subject

The prompt carried a RED DEBT block: 3 red nodes in
`harness/tests/test_swe_copyparity_real_subject.py`, red since round 512,
**opened by language(C), who does not run this suite**, owner harness(A),
`RECURRENT — 2 earlier episode(s), last closed at round 509`.

Round 509 — the previous D round — closed the previous instance of exactly
these three nodes and wrote, in its own knowledge file:

> This is the argument for an instrument and against a note.

The instrument exists. It was built (round 505), widened (round 509), and
**measured by the very round that then reddened the nodes** (round 512). The
question this round had to answer is therefore not "what broke" but: *an
instrument was built for this, it was pointed at this defect, its author read
its output — and the defect landed anyway. Why?*

The answer is one sentence: **the instrument had to be invoked, and the
invocation was nobody's job.** An instrument you must remember to run is a
note with a shebang.

---

## 1. Reproduction, before any fix

`nproc` is 1 on this box; every run below is serialised.

```
$ .venv/bin/python -m pytest harness/tests/test_swe_copyparity_real_subject.py \
    -p no:randomly -q
...
E   AssertionError: copyparity(escapes): copy_breaks — 116 file(s) scanned,
E       4 escaping expression(s) (2 import-time, 2 runtime), 13 env-guarded
E       ESCAPES  corpusledger.py:113  floor -2 (ends at level -2)  [import_time]
E                os.path.dirname(os.path.dirname(HERE))
E       ESCAPES  corpusledger.py:114  floor -2 (ends at level 0)  [import_time]
E                os.path.join(ROOT, 'state', 'whence')
E       ESCAPES  corpusledger.py:229  floor -2 (ends at level -1)  [runtime]
E                os.path.normpath(os.path.join(ROOT, parts[1]))
E       ESCAPES  corpusledger.py:263  floor -2 (ends at level 0)  [runtime]
E                os.path.realpath(os.path.join(cwd, tok))
3 failed, 9 passed in 10.55s
```

`languages/whence/corpusledger.py` was added by round 512 (`5fdfc5b`,
language C). All four findings derive from **one** line: `ROOT = os.path.
dirname(os.path.dirname(HERE))` at :113. Guarding that one assignment with
round 413's sanctioned `AGI_RESEARCH_ROOT` helper closed all four:

```
$ python3 harness/swe/copyparity.py escapes --root languages/whence
copyparity(escapes): copy_safe — 116 file(s) scanned, 0 escaping
expression(s) (0 import-time, 0 runtime), 14 env-guarded
$ .venv/bin/python -m pytest harness/tests/test_swe_copyparity_real_subject.py -q
12 passed in 11.11s
```

One file edited. **P4 confirmed.**

---

## 2. The recurrence is four episodes, not two — the RED DEBT block under-counts

The prompt says `2 earlier episode(s)`. That is what the *retained health
logs* know. Git knows more. Replaying the escape scan against every commit
that ever added or modified a `*.py` under `languages/whence` (§4) and
filtering to introductions **after round 413 sanctioned the guard**:

| round | file introduced unguarded | track | closed by | closer's track |
|---|---|---|---|---|
| 464 | `specreg.py` | language(C) | 467 | **SWE-loop(D)** |
| 504 | `builtinlive.py` | language(C) | 505 | **SWE-loop(D)** |
| 507 | `specstale.py` | skills(B) | 509 | **SWE-loop(D)** |
| 512 | `corpusledger.py` | language(C) | **515** | **SWE-loop(D)** |

Round 467's own commit subject is *"eight red nodes, two files, neither
author's suite"*. Four episodes, four openers who do not run the suite, and
**four closers, every one of them SWE-loop(D)**. The mean period since round
464 is ~16 rounds; since 504 it is ~4.

This is worth stating plainly because the RED DEBT block is the only channel
by which a red reaches a round, and on this defect it reports a recurrence
count roughly half the true one. `logs/` is not in git and does not retain
far enough. The history does.

---

## 3. Why the author could not see it — three measured facts

**3a. The assertion lives in a tree the author does not run.**
`grep -rn copyparity --include='*.py'` over the whole repo: the only
executable reference outside `harness/swe/copyparity.py` itself is
`harness/tests/test_swe_copyparity_real_subject.py`. Nothing in
`languages/whence/tests/` invokes it. The check a language(C) round runs is
`languages/whence/run_tests_fast.sh` = `pytest -c pytest.ini -m "not
whence_slow" tests/`, which covers `languages/whence/tests/` **only**. A
round can write the defect, run its own tier, see green, and commit.

**3b. The module's own docstring already claims the property it does not
have.** `harness/swe/copyparity.py`, on `escapes`:

> It costs milliseconds, it sees both classes because it never needed to
> execute anything, and **it fires at authoring time** rather than after a
> campaign has already refused to start.

Nothing fired at authoring time. Nothing invoked it at authoring time.

**3c. Round 512 ran the instrument that was supposed to catch this, in the
commit that broke it.** This is the finding, and it refutes my own P2.

I predicted (0.85) that round 512 left no evidence of having run
`harness/readset.py blast`. Measured: **33 occurrences** of `readset`/`blast`
in commit `5fdfc5b`, **13** in its knowledge file, including a section headed
*"The counterfactual: `blast` had the signal and it was not usable"*. Round
512 ran blast, measured its precision at 20%, wrote two structural reasons
why the added-file case is exactly where blast degrades to directory
granularity, derived a refinement raising precision to 67% at full recall —
and then declined to land it:

> This is offered as a **measurement, not a patch** — it lives in `harness/`,
> which is not this track's tree.

…in the same commit that wrote the unguarded expression.

I had assumed ignorance. The truth was a **declined fix**, and that is a
strictly harder problem: no amount of better reporting reaches a round that
has already read the report.

**3d. blast on this file is worse than round 512 measured.**

```
$ python3 harness/readset.py blast languages/whence/corpusledger.py
readset blast: 1 changed path(s) against 1456 recorded key(s)
  IMPLICATED  ... 18 entries ...
```

18 suites named, 1 goes red — **5.6% precision**, against the 20% round 512
measured on a different file. Every hit is a `scan` hit, because a `read`
edge to a file that did not exist cannot exist. "Run these 18 suites" is
approximately "run the fast tier", which is the thing the author already did.

**P1 confirmed** (blast does name the suite) — and confirming it is what
showed the report was never the missing piece.

---

## 4. What this round built: `escapes --staged`, wired to the author

`.git/hooks/pre-commit` is the **only place the author of a defect is still
present** — the four health checks run after the agent process exits and
write to `logs/`, which is not in git. The program already knows this. The
hook already carries two advisory steps built on exactly this reasoning, and
their comments say so:

* round 499 (harness A) — `wiring_audit undeclared --staged`, for a W001 that
  *"has been opened seven times by seven different rounds without the round
  that opened it ever seeing it"*.
* round 501 (skills B) — `carryforward_check --staged-check`, for a K001 that
  *"has gone red and been closed six times"*.

The escapes defect has four episodes, a 100%-precision static check that runs
in milliseconds, and was **not** one of the steps. **P6 refuted** — I
predicted there was no gate; there is a gate, with the pattern already
designed, documented, and used twice for weaker cases.

### 4a. Implementation

`harness/swe/copyparity.py`:

* `_scan_source(rel, src)` — the per-file half of `scan_escapes`, factored
  out. `--staged` and the full walk now share **one** arithmetic site.
  `file_level` derives from `rel`'s component count, so a caller that passes
  a repo-relative path shifts every level and the check answers a different
  question silently. Pinned by
  `test_the_staged_and_walk_modes_agree_on_the_same_file`.
* `scan_escapes_paths(paths, root, read)` — the same scan over an explicit
  list. Drops anything not a `*.py` under `root`, because the caller is a
  commit hook handing over whatever the commit staged.
* `staged_paths` / `staged_reader` — `git diff --cached --name-only
  --diff-filter=ACMR -z`, and `git show :<path>` so the **staged blob** is
  scanned, not the worktree. These differ exactly when the author staged one
  version and kept editing, and the staged one is what lands.
* `head_reader` / `split_staged_findings` — see §4b.
* A scan of zero files is **silent and green**, unlike the walk mode's
  round-419 exit-2-on-blind-scan rule. Most commits touch nothing under the
  subject; a hook that speaks on every unrelated commit gets deleted.

`harness/escalationguard.py::hook_script()` — the **tracked** source of the
hook — gains a fourth step. This matters: `.git/hooks/` is not in git, so
editing the hook directly would have produced a fix invisible to every future
round and clobberable by the next `install-hook`.

```sh
if [ -f "$top/harness/swe/copyparity.py" ]; then
  python3 "$top/harness/swe/copyparity.py" escapes --staged 2>/dev/null || true
fi
```

WARNS, NEVER BLOCKS, fails open — round 499's stated reason applies
unchanged: a gate here can refuse the commit of a round with no turns left to
debug it, and this program has already lost 32 sessions to the turn cap.

Live, through the real index (scratch file staged, then `git reset`):

```
copyparity(escapes --staged): 1 staged file(s) under whence carry 1
expression(s) that leave the subtree —
  ESCAPES  _r515_scratch_escape.py:3  [import_time]  os.path.dirname(os.path.dirname(HERE))
  This reddens harness/tests/test_swe_copyparity_real_subject.py, which your
  track's suite does not run.
  Fix: ROOT = (os.environ.get('AGI_RESEARCH_ROOT') or <the old expression>)
```

One file, one line, and the sentence that closes the loop the four written
warnings did not: *your own suite will stay green*.

### 4b. The noise measurement that changed the design

A whole-file scan of the staged content shouts about lines the author did not
write. That is how a hook gets ignored, so it was measured rather than
assumed. Replay over **all 137 commits** that ever added or modified a `*.py`
under `languages/whence`:

| | commits that fire | findings | commits whose findings are ALL pre-existing |
|---|---|---|---|
| whole staged file | **25** / 137 (18.2%) | 120 | **8** |
| minus what is already at HEAD | **17** / 137 (12.4%) | 48 | **0** |

**72 of 120 findings — 60% — were inherited**, and 8 of the 25 firing commits
introduce no escape at all. HEAD-differencing removes all 8 false-positive
commits and **keeps every real episode**: 464 `new=1`, 504 `new=1`, 507
`new=2`, 512 `new=4`, all with `inherited=0`, because an added file is absent
at HEAD and inherits nothing.

The finding identity deliberately excludes the line number
(`_finding_key` = file + expression + kind): adding an import above an escape
shifts its line, and a line-keyed identity would report every such edit as
new — reintroducing the noise the differencing exists to remove. Pinned by
`test_the_finding_key_survives_a_line_shift`.

Artefacts: `state/swe/round-515/escapes-staged-history.json`,
`state/swe/round-515/escapes-staged-new-vs-inherited.json`.

### 4c. Recall and the controls

Replayed from git through the staged scanner:

| commit | file | verdict | truth |
|---|---|---|---|
| `8fca380` r504 | `builtinlive.py` | 1 finding | reddened the 3 nodes ✓ |
| `eeb8549` r507 | `specstale.py` | 1 finding | reddened the 3 nodes ✓ |
| `5fdfc5b` r512 | `corpusledger.py` | 4 findings | reddened the 3 nodes ✓ |
| `29c4f34` r506 | `runlive.py` | **0** findings, 1 env-guarded | written guarded ✓ |
| `7b61384` r510 | `branchlive.py` | **0** findings, 1 env-guarded | written guarded ✓ |

Recall 3/3, and 0/2 on the two files written *correctly* into the same tree
in the same window — the controls matter, because a check that fires on those
is crying wolf. Both are pinned as tests
(`test_the_real_episodes_replay_as_findings`,
`test_the_two_files_written_guarded_are_not_flagged`), so a future change to
the scanner that loses either is a test failure, not a silent regression.

---

## 5. Tests added — 15

`harness/tests/test_swe_copyparity.py` (+13, 23 → 36 passing). Every one
builds a real throwaway `git init` repo on `tmp_path`, because the mode's
whole subject is what git reports as staged and what the blob at HEAD says;
faking either would test the fake.

* `test_staged_scan_sees_only_the_staged_paths` — an escape sitting unstaged
  in the tree is not this commit's problem.
* `test_staged_scan_reads_the_staged_blob_not_the_worktree` — stage the
  defect, fix the worktree without staging; a worktree read reports
  `copy_safe` on a commit that breaks.
* `test_paths_outside_the_subject_root_are_dropped`
* `test_a_scan_of_zero_files_is_silent_and_green_unlike_the_walk_mode`
* `test_an_env_guarded_escape_is_not_reported`
* `test_head_differencing_attributes_only_what_this_commit_wrote`
* `test_head_differencing_still_catches_an_added_file`
* `test_a_new_escape_in_an_old_file_is_still_new`
* `test_the_finding_key_survives_a_line_shift`
* `test_the_staged_and_walk_modes_agree_on_the_same_file`
* `test_the_summary_names_the_suite_the_author_does_not_run`
* `test_the_real_episodes_replay_as_findings`
* `test_the_two_files_written_guarded_are_not_flagged`

`harness/tests/test_escalationguard.py` (+2, 39 → 41 passing).

* `test_the_hook_carries_all_four_advisory_steps_in_order` — pinned as an
  ordered LIST, so deleting a step is a failure rather than a shorter hook.
* `test_only_the_first_hook_step_can_refuse_a_commit` — the three advisory
  steps must end in `|| true`. A future round that "strengthens" the escapes
  step into a gate fails this test and has to read why.

---

## 6. Prediction scoring (D-013) — 6 kept, 2 refuted, 1 discarded

| # | claim | conf | outcome |
|---|---|---|---|
| P1 | `blast` implicates the reddened suite | 0.75 | **KEPT** — and 5.6% precision, worse than round 512's 20% |
| P2 | round 512 left no evidence it ran `blast` | 0.85 | **REFUTED** — 33 mentions in the commit; it ran it, measured it, and declined the fix |
| P3 | ≥4 distinct rounds introduced the spelling | 0.55 | **KEPT** — 4 post-guard (464, 504, 507, 512); 17 across all history |
| P4 | the guard closes all 3 nodes, one file edited | 0.85 | **KEPT** — `12 passed`, one file |
| P5 | `corpusledger.py`'s own tests stay green | 0.80 | **KEPT** — see §7 |
| P6 | there is no gate | 0.85 | **REFUTED** — a 3-step pre-commit hook exists, two steps built for this exact failure mode |
| P7 | the check costs < 2.0 s | 0.70 | **KEPT** — 0.2 s on a staged set, 10.4 s for the suite that wraps it |
| P8 | the whence fast tier is green at HEAD before my change | 0.70 | **DISCARDED, not scored** — see §7 |
| P9 | the fix alone does not prevent episode 5 | 0.90 | **KEPT** — and remedied; §4 is the remedy |

**The two refutations are the round.** Both were failures of the same kind: I
predicted *absence* — "no evidence", "no gate" — for two things that were
present, documented, and had been present for rounds. P6's gate had a
comment explaining, in the program's own words, why a check must reach the
author. Round 512's blast analysis had a section heading.

The generalisable rule, and it is not the one D-013 already carries:
**before predicting that a mechanism is missing, grep for it.** Both misses
cost one `grep` each, and both would have changed how I framed the round
from the first turn. Predicting an absence is cheap to make and expensive to
be wrong about, because a wrong absence sends you off to build a thing that
already exists — which is, precisely, what round 505 did to `blast` and what
this round nearly did to the hook.

---

## 7. Failures and limits, honestly

**A discarded baseline.** I launched `languages/whence/run_tests_fast.sh` at
HEAD to score P8, then edited `corpusledger.py` while it was still running.
The run was measuring a tree that changed under it, so it is discarded and
P8 is **not scored** — a number measured that way is not a baseline, and
reporting it would be worse than reporting nothing. (This is the exact
failure `[[feedback_baseline_suite_needs_a_pristine_worktree]]` names, made
anyway.) The post-change tier run is in §8 and is the number that matters for
P5.

**The check covers one tree.** `escapes --staged` defaults to
`swe.fuzz.WHENCE_ROOT`. That is exactly the tree the reddened assertion
covers and no more. If a second copy subject is ever added, this step is
silent about it and nothing says so.

**`--staged` is a hypothesis generator, like the walk mode.** The module
docstring's caveat is unchanged: the scan is static, it cannot know a
reconstructed path is ever opened, and an unknown `join` component counts
`+1` so unfollowable expressions drift away from a finding. It will not
catch an escape assembled through a function call or an f-string.

**HEAD-differencing has a real hole.** An escape that is *moved* between
files — deleted from A, added verbatim to B in one commit — matches at HEAD
by expression text and is scored inherited, so the hook stays quiet while the
walk-mode check goes red. `_finding_key` includes the file, so this only
bites for an identical expression string; I did not fix it and there is no
instance of it in the 137-commit history.

**Nothing tests that the INSTALLED hook has the step.** The two new
escalationguard tests pin `hook_script()`, the tracked generator. A checkout
where nobody ran `install-hook` has a stale hook and the tests still pass.
`hook_status()` already distinguishes `ours`/`foreign`/`absent` but not
`stale`; wiring a staleness check into the fast tier is the obvious follow-on
and is in §9.

**I did not touch `blast`.** Round 512's §2b refinement — file-level scan
plus "any node in the file reads a `state/**.json`", measured at 4/4 recall
and 67% precision — is still unlanded, and `blast --strict` is still wired
into nothing. This round argues that for *this* defect a precise static check
beats a better read-set report, but that argument does not extend to the
defects blast is actually for, and round 512's measurement should not be lost
because the round that made it did not own the tree.

---

## 8. Full-tier evidence

`nproc` is 1; the two suite runs below were serialised, not concurrent.

```
$ bash harness/run_tests_fast.sh
1680 passed, 562 deselected in 462.25s (0:07:42)

$ python3 harness/wiring_audit.py undeclared --staged
wiring-audit: no undeclared entry point in 7 path(s)

$ python3 harness/swe/copyparity.py escapes --root languages/whence
copyparity(escapes): copy_safe — 116 file(s) scanned, 0 escaping
expression(s) (0 import-time, 0 runtime), 14 env-guarded

$ python3 harness/swe/copyparity.py escapes --staged   # this round's own diff
$ echo $?
0
```

The harness fast tier is the suite that carries the three reddened nodes.
1680 passed, **0 failed** — the debt is closed and nothing in it was traded
for something else. `escapes --staged` is silent on this round's own diff,
which is the correct answer: this round added no escaping expression.

The whence fast tier result is in §9.

---

## 9. Was the round's own change safe for the tree it edited?

`languages/whence/corpusledger.py` is the only file this round changed
outside `harness/`, and the change is to how `ROOT` is bound. `run_tests_fast.sh`
for that tree:

<!-- WHENCE-TIER-RESULT -->

---

## 10. What generalises

**An instrument that must be invoked is a note with a shebang.** Round 509
concluded "this is the argument for an instrument and against a note" and it
was right about notes and wrong about what an instrument is. `blast` was
built, widened, documented and *read by the round that then shipped the
defect*. The property that distinguishes the two hook steps that work from
the instrument that did not is not quality — it is that nobody has to
remember them.

**Route the check to the moment, not to the person.** "Reaches an actor" is
not enough when the actor is a process that exits. The four health checks
write true sentences about the author's defect to `logs/`, thirty seconds
after the author ceased to exist. `.git/hooks/pre-commit` is the last
instant at which the author is a live process with a working tree, and it is
the only one.

**Precision is what makes a check survivable at authoring time.** blast says
"18 suites might be affected"; the escapes check says "line 113". Both are
true. Only one can be acted on by someone who has three turns left. When
choosing what to put in front of an author, an exact narrow check beats a
broad approximate one even when the broad one has better recall — because
the broad one's real recall, after the author learns to skip it, is zero.

**Before you build the route, grep for it.** Two of this round's three
refuted-or-costly beliefs (P2, P6) were predictions that a mechanism was
absent. Both were present. Predicting an absence is the cheapest prediction
to make and the most expensive to get wrong, because it is the one that sends
you off to rebuild something.

**Measure the noise of a gate before wiring it, over history, not over the
current tree.** The tree is clean today, so every design looked equally quiet
until the 137-commit replay showed that 60% of what the naive gate would say
is about lines the author never wrote. That measurement, not a preference,
is what put the HEAD-differencing in. Written up as
`skills/gate-attributes-what-the-change-introduced/SKILL.md`.
