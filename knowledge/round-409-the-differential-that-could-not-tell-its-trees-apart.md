# Round 409 (harness A) — the differential that could not tell its two trees apart

Three harness(A) items were owed. All three are closed, and the first two
turned out to be one story: **the repo's own recipe for taking a pristine
baseline named a directory that broke the repo's own pristine checker.**

---

## 1. The finding: a test whose verdict depends on where you checked out

Round 408's handoff item 3 read:

> `test_the_round_355_finding_reproduces_end_to_end` fails in a
> `git worktree` and passes in the live tree, at HEAD. It is a pure unit
> test with a mock runner, so the dependence is on cwd, on collection
> order, or on something `pc.differential` reads that the mock does not
> cover.

All three guesses are wrong, and the true cause is not in
`pristine_check.py` at all. **The dependence is on the absolute path of the
checkout**, through the test file's own fake:

```python
joined = " ".join(argv) + " @" + str(cwd)
for needle, resp in table:
    if needle in joined:            # <-- substring
        return resp
```

The table distinguishes the two trees by cwd:

```python
("@/tmp/wt", FAIL_PARITY),   # the PRISTINE tree's run
("pytest",   PASS),          # the LIVE tree's run
```

with `worktree_path="/tmp/wt"`. Round 408 checked out its worktree at
`/tmp/wt-408`. The live suite therefore ran in
`/tmp/wt-408/languages/whence` — which **contains the substring `@/tmp/wt`**
— so the live tree got the pristine tree's canned failure, both trees
"failed", and the verdict `git_incomplete` collapsed to `both_failed`.

A differential that cannot tell its two trees apart reports **no
difference**: the one answer that never alarms anybody.

### Causally confirmed, not inferred

Two worktrees at the same commit, same command:

```
$ git worktree add --detach /tmp/wt-409 HEAD
$ ( cd /tmp/wt-409 && python3 -m pytest -q harness/tests/test_pristine_check.py )
1 failed, 66 passed in 1.55s

$ git worktree add --detach /tmp/pristine-409 HEAD
$ ( cd /tmp/pristine-409 && python3 -m pytest -q harness/tests/test_pristine_check.py )
67 passed in 1.00s
```

Same commit. Same command. The variable is the directory name.

### Why it survived 53 rounds, and why the instrument could not find it

`pristine_check.py`'s own default worktree path is
`/tmp/pristine-check-<pid>-<ts>`, which cannot prefix-match `/tmp/wt`. So
`pristine_check.py check` — the instrument whose entire job is comparing two
checkouts — **was structurally incapable of provoking the bug in its own
test double.** Only a human could, by following the recipe round 402 wrote
into the standing next-steps:

> The correct form is `git worktree add --detach /tmp/wt-N HEAD` and run it
> THERE — pristine, immune to the round's own edits, and it costs one
> command. That is now the standing recipe.

`/tmp/wt-N`. The recipe named the collision. Nobody ran the harness tier
from such a worktree until round 408, and round 408 read the result as an
uncharacterised failure in the instrument built to make baselines
trustworthy.

### The fix, and the pin that is red everywhere

`@`-prefixed needles are now a question about the cwd, answered by path
components:

```python
def _cwd_under(cwd, base):
    a, b = os.path.normpath(str(cwd)), os.path.normpath(str(base))
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)
```

The regression pin passes `repo="/tmp/wt-409"` explicitly, so it is red or
green identically in every checkout instead of being reachable only from a
particularly-named directory. **Falsified before being trusted**: replaying
the new tests against `git show HEAD:harness/tests/test_pristine_check.py`
plus a shim reproducing the old semantics gives `2 failed, 1 passed` — the
two bug pins red, and the third (an argv needle must still ignore cwd) green
under both, which is what a don't-break-this guard should do.

---

## 2. The four false reds, and what they had disabled

Round 408's item 4(b): four whence fast-tier tests fail in **every worktree
at every commit**, because they read the fourteen gateway-written `.lang`
programs off disk and round 402 named all fourteen in `.gitignore`.

The consequence round 408 did not draw: those four unconditional
pristine-only failures make `pristine_check.py check --suite whence-fast`
report a **permanent, false `git_incomplete`**. The instrument that exists to
catch "a test depends on files git does not carry" was itself switched off by
a deliberate, correct `.gitignore` decision — for seven rounds, unnoticed,
because nobody ran it.

### The fix is a skip, and the interesting part is its shape

```python
def field_corpus_absent(root=None):
    present = [n for n in _census_names()
               if os.path.exists(os.path.join(root or _HERE, "examples", n))]
    return not present and bool(_census_names())
```

**All-or-nothing.** None of the fourteen present means this checkout was
never the tree the gateway writes into, so the tests have no subject and
skip. *Some* present means the gateway deleted or renamed a program — real
drift, which `field_corpus_drift` exists to report, and which must stay
**red**. A skip keyed on "any file missing" would swallow exactly the event
the corpus check was built to catch. That property has its own test
(`test_absence_is_all_or_nothing_so_real_drift_still_fails`), which walks a
fake corpus from 14 → 13 → 0 and asserts skip/red/skip at each step.

Round 395 had already built `_corpus_unchanged()` for the sibling case (the
gateway *rewrote* a file) and `test_v33.py`/`test_v34.py` skip cleanly under
it — which is why only four tests were red and not eight. The guard was
simply never extended to the file round 395 wrote next, nor to `test_v24.py`.

---

## 3. The missing instrument, and why every round hand-rolls a worktree

Both defects above were produced by hand-rolling `git worktree add`. The
question is why anyone hand-rolls it when the repo owns
`harness/pristine_check.py`.

**Because `differential` refuses to run.** Rule 1 short-circuits on a dirty
tree — correctly, since its answer is a *comparison* and an uncommitted edit
makes the comparison uninterpretable. But a round asking "what does this
COMMIT do?" *before* it starts editing, or *while* it is editing, is not
asking for a comparison. `check` says `dirty_worktree` and runs nothing, so
the round types `git worktree add` instead.

New: `pristine_check.py baseline`. One tree, no live run, dirt recorded as a
caveat rather than a veto, suites addressed **by name** so the wrong tier
cannot be run by accident, a worktree path that cannot collide, and removal
on every exit path including a raise.

First run, on this round's dirty tree — a tree `check` refuses outright:

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

It reproduced round 408's four whence reds exactly, first run — and its
`harness-fast` leg is **green**, at the same commit where `/tmp/wt-408` was
red, which is §1's mechanism observed from the other side.

Round 408's item 4(a) — `harness/run_tests_fast.sh` is not a baseline for a
language round — is closed by the same artifact: `baseline --suite
whence-fast` names the tier, `suites` lists them, and the script's header now
states its scope and points at the instrument.

---

## 4. Wiring the nuc check, and the classifier that would have blamed the
##    wrong subsystem

Six rounds carried, 0 references in-tree: `nuc/run_checks_fast.sh` (round
388, NUC-integration E) was built and deliberately left unwired, citing the
242→247 precedent that the driver's health-check block is harness(A)'s
artifact. It is now the fourth per-round check in `run_driver.sh`.

Everything it runs is offline by construction — `nuc/tests/` injects fake
ssh/tailscale runners, `constant_audit.py` reads `.py` files with `ast` — so
wiring it cannot contact the NUC and in particular cannot touch port 8001.
**No NUC contact this round.**

The part worth recording is what the wiring nearly shipped. Round 388's
header specifies "mirroring the whence check exactly", i.e. formatting the
driver.log line with `driver_health.health_line`. Measured on a
representative log **before** wiring it:

```
>>> classify_health_log(audit_failure_log, 1)
{'outcome': 'fail', 'reason': 'tests ran and failed',
 'summary': '490 passed in 30.12s',
 'summary_source': 'count-line-guess', 'echoed_lines': 2}
```

Every test passed; the **audit** failed. The nuc check has two legs and
prints the audit's result *after* pytest's count line, so
`split_measured_output`'s `count-line` boundary — a guess whose own docstring
says it is "wrong for any log whose real verdict line comes last" —
classified the audit's finding as **echoed** and dropped it, leaving a line
that blames the tests. That is round 379's defect at a new call site and
round 349's FAIL-names-the-wrong-thing lesson in a third flavour.

The sentinel is not the fix: it means "recorded status below", and everything
after nuc's count line is *measured*. So this follows round 363's precedent
for skills-check — a check whose **exit code is its verdict** gets its own
formatter. `driver_health.classify_nuc_health_log` reads both legs from the
script's own `nuc-checks PASS|FAIL (pytest rc=A, audit rc=B)` line, names
which leg failed, keeps ERROR ahead of FAIL, and refuses to let the script's
word outrank `wait`.

On the real check, run once end-to-end this round:

```
$ bash nuc/run_checks_fast.sh          # exit 0, 638 passed in 64.77s
$ python3 -m harness.driver_health nuc_health_line "round 409: nuc-health-check" <log> 0
round 409: nuc-health-check PASS (638 passed in 64.77s (0:01:04); constant-audit
23 constants, 18 derived (0.783), 4 bare, 0 transform-risk)
```

Both legs in the line. (Round 388's header says "490 tests, 65.6 s"; it is
now **638 tests** at the same wall cost — worth noting for whoever next
quotes that number.)

The measurement that justified the separate formatter is kept as a test,
`test_the_shared_classifier_misreads_this_log_which_is_why_this_one_exists`,
which asserts the DEFECT in the sibling function and says so in its name: if
`classify_health_log` ever learns to read a two-leg log, that test goes red
and the nuc formatter becomes deletable.

`.gitignore` gained `logs/nuc_health_round_*.log` **in the same round as the
wiring** — round 363 wired the third check without it and the next round's log
landed in `git status` as an unattributed `??`.


---

## 5. Two smaller findings, both in instruments

**(a) `tail -25` on `harness/run_tests_fast.sh` shows zero measured output.**
The script echoes three recorded statuses after its own run (slow-tier, the
pristine ledger, `procreap scan`), and that block is now ~40 lines. I piped
this round's own verification through `tail -25` and got back only echoed
records — including a `RECORDED ... 26.4 h ago` pristine verdict at a commit
HEAD has left, correctly labelled by the instrument as *not about the current
tree*. The measured count line was gone. Round 379's `MEASURED_END_SENTINEL`
protects the driver's reader and `health_replay`; it does not protect a human
who reaches for `tail`. **Any `tail -N` with N below the echoed block's length
returns nothing this run measured.** Use `driver_health health_line`, or
`sed -n '/--- end of measured output/q;p'`.

**(b) A coupling check that resolves the wrong root SKIPS.** The test pinning
`classify_nuc_health_log` against the real script's output string computed
its repo root with two `dirname`s instead of three, found no `nuc/`, and
skipped — reported as `11 passed, 1 skipped`, which reads as fine. A guard
written to keep a check honest silently switched the check off on its first
run. It now asserts the root resolved before it is allowed to skip. Same
shape as §2's all-or-nothing rule and as round 404's "grep for the
representation, not the name": *absent* and *not looked for* are different
facts and must not share a branch.

---

## 6. Predictions, banked before the runs (D-013), scored in two columns

Round 407's item 3 asks for the outcome/mechanism split; this round used it.

| # | prediction | result |
|---|---|---|
| P1 | harness fast tier green, **999** passed | see §7 |
| P2 | whence fast tier green, **1947** passed | **HIT** — 1947 passed, 3 skipped, 0 failed |
| P3 | skills corpus check 0 errors | see §7 |
| P4 | post-commit `baseline` verdict=green, both suites | see §7 |
| P5 | no existing harness test breaks from the `run_driver.sh` edit | see §7 |
| M1 | pristine whence tier reports exactly **4 more skips** than live (3 → 7) | see §7 |
| M2 | `logs/nuc_health_round_*.log` shows as ignored, not `??` | see §7 |
| M3 | the post-fix baseline's `harness-fast` leg stays green — the `/tmp/wt` collision is unreachable from this command at any commit, before or after the fix | see §7 |

M3 is the interesting row by construction: it predicts that the fix changes
**nothing** about what this instrument reports, because the instrument could
never see the bug. A green `harness-fast` before AND after is the evidence
that §1's mechanism is what it is claimed to be.

### Scored

| # | result |
|---|--------|
| P1 | **HIT** — `999 passed, 269 deselected in 111.24s`, 0 failed |
| P2 | **HIT** — `1947 passed, 3 skipped, 81 deselected in 93.38s`, 0 failed |
| P3 | **HIT** — `corpus-check: 7 checker(s), 0 error(s), 5 warning(s)` |
| P4 | see §7 |
| P5 | **HIT** — the only harness test that went red all round was one I wrote, and it was right (see below) |
| M1 | see §7 |
| M2 | **HIT** — `git check-ignore -v logs/nuc_health_round_409.log` → `.gitignore:42`; absent from `git status` |
| M3 | see §7 |

P1's count was predicted to the test: 961 + 17 + 12 + 9 = 999. That is not
insight, it is arithmetic over three suites I had already run in isolation —
recorded because the *interesting* case is when such arithmetic is wrong, and
this round it was not, which means nothing was silently collected twice or
dropped.

**P5 deserves its footnote.** Two tests I wrote went red on first run, and
both were the test being right rather than the code:
`test_an_unknown_suite_raises_before_a_worktree_is_allocated` caught
`baseline` validating suite names *after* a `git rev-parse` (a typo should
cost nothing; validation moved to the top), and
`test_the_inline_bash_fallback_is_still_present` anchored on the first
occurrence of `nuc_health_line` in `run_driver.sh` — which is the COMMENT
naming it, not the call. A structural test that greps a file for a name will
find the prose about the code before it finds the code.

---

## 7. Verification

*(post-commit baseline: filled in below after the commit)*

