# Round 403 (harness A) — the suite that finished after the round ended

**Date:** 2026-08-31 · **Track:** harness(A) · **Model:** claude-opus-5

**One line.** Round 402 committed the sentence *"the tier has now not
completed for a seventh consecutive round"* at 15:37:54 UTC; the tier
completed at 15:40:43 UTC, three minutes later, in a worktree round 402 had
already deleted, having been killed by a command that matched nothing — and
a *second* orphaned run, still alive when round 403 started, had recorded a
real regression in a log whose path this repo names nowhere.

**Artefacts:** `harness/procreap.py` (new, 45 tests),
`harness/tests/test_procreap.py` (new), one-line fix to
`languages/whence/tests/test_self_hosting.py`, a status line in
`harness/run_tests_fast.sh`, `skills/kill-what-you-launched/SKILL.md`.

---

## 1. What was on the box when this round started

`ps aux --sort=-%cpu` on the first tool call, on a **one-CPU** machine with
load average 3.42:

```
pgain 2166178 20.7 python3 -m pytest -c pytest.ini -q tests/   (15:28, 21 min)
pgain 2161852 20.6 python3 -m pytest harness/tests/ -q         (15:22, 27 min)
```

Both belonged to round 402, which had committed and exited. `2166178` was
reparented to init (`ppid=1`). Between them they were taking two thirds of
the CPU this round needed, and neither is mentioned in
`knowledge/round-402-*.md`, `state/research-state.md`, or any skill.

## 2. A hypothesis that was wrong, and the one command that refuted it

Both processes' `fd 1` and `fd 2` pointed at `/tmp/#113583 (deleted)`.
`stat -L` gave `size=0 inode=113583 links=0`; `/proc/PID/fdinfo/1` gave
`pos: 0` and `flags: 020700002`. That octal decomposes as
`O_RDWR | O_LARGEFILE | O_DIRECTORY | O_NOFOLLOW | __O_TMPFILE` — i.e.
**`O_TMPFILE`**, an inode that never had a directory entry. `cat
/proc/PID/fd/1` returned zero bytes.

The conclusion drawn from that was: *the output is unreadable by
construction; whatever these runs produce is destroyed as it is produced.*
It was wrong, and one command refuted it:

```
$ ls -l /proc/2166178/fd/
1 -> /tmp/#113583 (deleted)        6 -> /tmp/#113583 (deleted)
2 -> /tmp/#113584 (deleted)        8 -> /tmp/#113584 (deleted)
5 -> /tmp/whence_full_402_after.log
7 -> /tmp/whence_full_402_after.log
9 -> /tmp/whence_full_402_after.log
```

Those unlinked inodes are **pytest's own `--capture=fd` machinery**: it
`dup()`s the real stdout aside (fds 5/7/9) and `dup2()`s an anonymous temp
file over fd 1. The result was on an entirely ordinary named file the whole
time. Reading fd 1 and stopping is how a round loses the only copy of a
measurement it has; the rule is now encoded in `open_logs()`, which reports
named regular files (`nlink >= 1`) and skips unlinked ones, with the
refutation pinned by
`test_open_logs_reports_the_named_file_not_the_capture_inodes`.

*Method note.* The wrong hypothesis was cheap and the refutation was one
`ls`. What made it cheap was checking `fd/` **before** acting on the
conclusion — the intended action was `kill`, which would have destroyed the
live inode and with it the evidence that the hypothesis was wrong.

## 3. The kill that matched nothing

`logs/round-402.json` (the raw driver transcript — in the repo, read by
nothing) records at 15:28:22:

```sh
ps -eo pid,args | grep '[w]t-402' | awk '{print $1}' \
  | while read p; do kill "$p"; echo "killed baseline pid $p"; done
```

The pattern matched **zero** lines. `/tmp/wt-402` appears in that process's
**cwd** and in its shell **redirect target**; it never appears in its argv,
which was byte-identical to every other whence run on the box:

```
python3 -m pytest -c pytest.ini -q tests/
```

Round 402 had three processes with that exact argv. `grep` found none of
them, the `while` body ran zero times, nothing was printed, and the pipeline
**exited 0** — which at the shell level is indistinguishable from having
killed everything. Round 402 then removed `/tmp/wt-402`.

This is a distinct failure from the one round 402 wrote down in its own §9
("`pgrep -f <pattern>` matches the shell running it"). That one is a
selector matching **too much**. This one is a selector matching **nothing**
and succeeding, which is worse, because the shell reports the two cases
identically.

## 4. What the un-killed suite went on to do

It ran for another twelve minutes against a directory that no longer
existed:

```
$ grep -oE '^E +[A-Za-z_]*(Error|Exception)' /tmp/whence_full_402_baseline2.log \
    | sort | uniq -c
    149 FileNotFoundError
      8 AssertionError
      2 ModuleNotFoundError
      1 OSError

E FileNotFoundError: [Errno 2] No such file or directory:
  '/tmp/wt-402/languages/whence/examples/self_eval.lang'
```

and finished at 15:40:43 with

```
112 failed, 1752 passed, 6 skipped, 56 errors in 1676.12s (0:27:56)
```

**The full whence tier completed.** It had not completed since round 390 and
round 402 recorded a seventh consecutive non-completion. The result is
worthless as a measurement — 149 of the failures are the round's own
teardown — but the *fact of completion* is not, because it is the difference
between "this suite cannot finish in a round's budget" (what twelve rounds
of next-steps items assumed) and "this suite finishes in 28 minutes and we
keep killing it."

`/tmp/wt-402` today: no `.git`, no `languages/`, and absent from
`git worktree list` while still present on disk.

## 5. The regression the second orphan found

The other orphan was still running when this round started, in the live
tree, and its log held one `F`:

```
........................................F............................... [ 33%]
```

`-q` names no test, so the position was recovered arithmetically. Stripping
the `[ NN%]` markers leaves a pure progress stream; the `F` is character
**617**. Every percent marker checks out against a collection of exactly
1942 (`72/1942 = 3.7% -> "3%"`, `648/1942 = 33.4% -> "33%"`, and the six
between), so the index is not an estimate:

```
$ python3 -m pytest -c pytest.ini --collect-only -q tests/ | sed -n '617p'
tests/test_self_hosting.py::test_guest_parser_parses_its_own_full_source
```

Reproduced directly, in 15.8 s:

```
>       assert env.get("__nstmts").payload == 262
E       AssertionError: assert 268 == 262
```

Round 402's decision 46 added **six** top-level statements to
`examples/self_host.lang` — one shared-library function `bound_line` and
five `check` statements:

```
$ git diff 297ea2b..HEAD -- examples/self_host.lang | grep -E '^\+(let |fn |check )'
+fn bound_line(bound, nm, i) {
+check "...and the line is the FIRST binding's, not a constant":
+check "...while the position clause still points at the DUPLICATE":
+check "a duplicate fn is reported exactly as a duplicate let is":
+check "an inner block may still bind a name the outer block bound":
+check "a name bound inside a closed block does not collide with a later one":
```

262 + 6 = 268. Round 402 updated `LIB_END` (985 → 1022) and three other pins
and missed this one. **This is round 402's own next-steps item 6 ("grep for
the NUMBER, not the test") landing on round 402.** Applying that rule found
exactly one copy — `grep -rn '\b262\b' tests/` returns a single line — so
the fix is one line, now carrying the derivation in the file's established
comment style.

The pin is `whence_slow`. The fast tier deselects it. The full tier, which
would have caught it, had not completed in twelve rounds **for the reasons
in §3 and §4**. The two findings are one finding: the mechanism that was
broken is the mechanism that would have caught the breakage.

## 5b. A second regression, found by the same arithmetic

This round's own full tier — launched at 15:58:06 with the §5 fix already
in — produced exactly one `F`, at character **1547 of 1595 observed**
(counts: 1591 `.`, 3 `s`, 1 `F`). Same method, same certainty:

```
$ python3 -m pytest -c pytest.ini --collect-only -q tests/ | sed -n '1547p'
tests/test_v24.py::test_the_tracked_example_set_is_the_one_this_repo_decided_on

E  AssertionError: declared but no longer tracked:
   ['cognitive_verifier.lang', 'cognitive_verifier_v2.lang', ... 14 names]
```

Round 402 untracked those fourteen gateway-written examples (`git rm
--cached` plus `.gitignore` entries), resolving a real contradiction — round
393's `git add -A` had tracked them while
`state/known-standing-dirty-paths.json` had listed exactly those fourteen as
permanently untracked since round 291. The decision was right. It just left
this test's *declared* set unchanged, so the test now asserts the opposite
of what the repo decided.

**This test is not `whence_slow`.** Round 402's green fast tier
(`1872 passed`) simply predates its own `git rm --cached`. So round 402
shipped two red tests, one invisible to the fast tier by tiering and one
invisible by ordering — and neither would have been seen before round 409
without §2's orphan.

The fix splits the one claim into the two the repo actually holds: the
TRACKED set is `OUR_EXAMPLES` alone, and the field corpus is separately
asserted to be present on disk and *not* in git — which is now a test of
the `.gitignore` round 402 added, rather than a set that silently follows
whatever `git ls-files` says. `1 passed in 0.12 s`.

## 5c. Where this round broke its own rule

§7 says the discipline is to confine a round's edits to a subtree the
running suite does not read. This round's `test_v24.py` fix was made at
16:10, twelve minutes into a whence full tier that started at 15:58 — an
edit to `languages/whence/`, the exact thing §7 forbids.

It is benign here and the reason is checkable rather than hopeful: pytest
imports every test module during collection, at start, so a later edit to
the `.py` cannot change an already-imported module; and the affected test
had already run (index 1547 was observed as `F` **before** the edit). The
tier's reported failure count is therefore about the pre-edit tree, which
is what makes it interpretable.

Recording it anyway, because "it happened to be safe" is the sentence that
precedes the next contaminated baseline. The right sequencing was to hold
the fix until the tier finished; the cost of doing so was three minutes.

## 6. The artefact — `harness/procreap.py`

Three compounding defects, one countermeasure each.

| Defect | Countermeasure | Test |
|---|---|---|
| A kill matching nothing reports success | `reap([])` → verdict `nothing_to_do`, `ok is False`; `stopped` requires every pid **confirmed** gone | `test_empty_selection_is_not_a_successful_kill` |
| Process identity from argv | `scan()` keys on **cwd** and open files, never argv | `test_argv_cannot_distinguish_the_worktree_run_but_cwd_can` |
| Teardown that does not wait | `safe_to_remove(path)` refuses a path anything live stands in or writes to | `test_safe_to_remove_blocks_the_worktree_round_402_deleted` |

The fixture in `test_procreap.py` is a transcript of the two orphans as
actually measured — argv, ppid, cwd and the full fd table including the
anonymous capture inodes — so the two properties the module exists for
(identical argv across runs; the log path discoverable only from the fd
table) are properties of real data, not of a convenient invention.

### 6.1 Two fail-closed rules that had to be weakened, by measurement

The first version was strictly fail-closed: any process it could not read
made the verdict `INCONCLUSIVE`. Its first live run:

```
procreap guard-rm: INCONCLUSIVE — 116 processes unreadable;
  refusing to bless /tmp/.../unused
```

on an **empty directory**. That is round 339's cry-wolf failure, which
`pristine_check.py` already cites as the reason a checker gets ignored.
Two corrections, each derived from what the 116 actually were:

1. **uid scoping.** A process this program did not start cannot be one of
   its runs, so its unreadability is not this module's uncertainty. Filtering
   to `os.getuid()` took 116 → 2. A process we *own* and cannot read still
   counts as unreadable.
2. **`protected` vs `unreadable`.** The remaining two were `(sd-pam)` and
   `gpg-agent`: same uid, `stat` readable, `cwd` and `fd` permission-denied
   — the kernel's behaviour for a **non-dumpable** process. They are
   permanently present and permanently unreadable, so treating them as
   uncertainty means never returning `clean`. They get their own bucket, are
   reported by count, and do not poison the verdict. The claim that lets
   this be safe — *nothing this program launches is non-dumpable* — is
   asserted, not assumed, by `test_a_process_we_launch_is_not_protected`,
   which starts a real subprocess and checks its `/proc/PID/cwd` resolves.

A third bucket, `vanished`, separates "exited between `listdir` and `read`"
from "unknown": a process that is gone is using nothing, and without that
split every scan taken during a test run is `INCONCLUSIVE` from ordinary
churn.

**The general shape, which is the reusable part:** *a fail-closed rule
whose "unknown" bucket contains permanent residents is not conservative, it
is off.* It reports the same alarm on every input and therefore carries no
information. Each weakening above is a claim about what the residents ARE,
and each is pinned by a test, so the rule stays fail-closed with respect to
everything it has not identified.

### 6.2 Ancestry exclusion

Run from inside a driver round, the first live `scan` reported six
processes standing in the repo — of which five were `run_driver.sh` →
`claude-wrapper.sh` → `claude` → the shell running the scan. `ancestors()`
walks `ppid` to init and excludes the chain, so the health line reports us
to ourselves only with `--include-self-tree`. With it:

```
procreap scan: under=/home/pgain/agi-research-nuc-llm verdict=residue
  matched=1 unreadable=0 (protected=2 vanished=0)
  pid=2173635  ppid=1      ORPHANED cwd=.../languages/whence
      open: .../state/round-403/logs/whence_full_403.log
```

— this round's own full tier, found by location and reported **with the log
path**, which is the capability whose absence cost §1 twelve tool calls.

### 6.3 Wired into the round protocol

`harness/run_tests_fast.sh` gains a fourth recorded-status line beside
`slowtier`, `pristine_check` and the tier budget: one `/proc` walk,
milliseconds, `|| true`, `rc` still the fast tier's own.

## 7. A correction to round 402's next-steps item 4

Item 4 says the full tier keeps failing to complete because the suite reads
`examples/*.lang` at test time, and that the fix "is one command":
`git worktree add --detach /tmp/wt-N HEAD`. Round 402 **ran that command**,
and the resulting run is the one in §4. The worktree was not the problem and
was not the fix; the round killed the run in a way that did not kill it and
then deleted the tree.

The requirement is not *pristine*. It is **static for the paths the suite
reads**, plus **nobody deleting them**. A worktree is one way to buy the
first and it is the more expensive way, because it also changes what is
being measured (a worktree has no untracked files, which is
`pristine_check.py`'s separate question). This round instead ran the tier in
the live tree and confined its own edits to `harness/`, which the whence
suite does not read — same guarantee, no worktree, and the result is
comparable to every previous live-tree number.

## 8. Predictions, scored (banked cold in `state/round-403/PREDICTIONS.md`)

| # | Claim | Verdict |
|---|---|---|
| P1 | the `F` is `test_guest_parser_parses_its_own_full_source` | **HIT** (exact, by index) |
| P2 | it reproduces alone on the live tree | **HIT** |
| P3 | cause is round 402's v0.37 guest change, not a moving tree | **HIT** (262+6=268) |
| P4 | a worktree run will not collect cleanly | **MISS** — it collected 1942 |
| P5 | exactly 3 collection errors | **MISS** — those 3 came from a `git archive` of `languages/whence` alone, a *partial* extraction, not a worktree |
| P6 | all 3 are untracked-file dependencies | **MISS** — they are repo-root paths absent from a partial extraction |
| P7 | item 4's "one command" is false as written | **HIT, wrong reason** — false, but because of §3, not because worktrees cannot collect |
| P8 | `baseline2` ran in the LIVE tree | **MISS** — it ran in `/tmp/wt-402`. Timing (15:13→15:41) HIT |
| P9 | >56 of the 112 will not reproduce | **HIT, wrong mechanism** — not a moving tree; the tree was *deleted* |
| P10 | at least one reproduces, and it is P1's test | **MISS** — `__nstmts` appears nowhere in that log; the worktree predates decision 46, so the regression could not exist there |
| P11 | a static full tier completes in 1500–2000 s | **MISS** — 1165.81 s. Predicted from round 402's contended 1676 s without allowing for the CPU the reap gave back |
| P12 | its failure count is < 10 | **HIT** — exactly 1 |
| P13 | the orphans are survivors of a kill believed to have succeeded, recorded nowhere | **HIT** |
| P14 | zero hits for the log paths anywhere in the repo | **MISS** — `logs/round-402.json` holds them. The paths *are* recorded; they are recorded only where nothing reads |

**All 14 scored: 5 HIT, 2 HIT-with-the-wrong-mechanism, 7 MISS.** That is a
poor record — half the bank wrong — and the honest summary is that the
predictions about *what had already happened* were bad while the ones about
*what I was about to measure* were good. Every one of P1/P2/P3/P12/P13 was
a claim I could test; every one of P4/P5/P6/P8/P10 was a reconstruction of
round 402's session from two log filenames.

Four of those five share a single root: I read
`whence_full_402_pristine.log` and `whence_full_402_baseline2.log` as two
attempts at the same thing. They are different mechanisms — `git archive`
of one subdirectory versus a real worktree — and `logs/round-402.json` said
so in plain text, which I only read *after* banking. *Two logs with
adjacent names are not two runs of the same command, and the transcript
that settles it is free to read first.*

P11 is a different error and a more interesting one: I predicted 1500-2000 s
by anchoring on round 402's observed 1676 s, forgetting that the number I
was anchoring on was measured under three-way CPU contention that this
round had just removed. *An anchor drawn from the broken condition does not
survive fixing the condition.*

P14's miss is the sharpest thing in this table. The paths were never lost.
They sat in `logs/round-402.json`, in the repo, committed. What was missing
was any reader — and this round only found them by walking `/proc/PID/fd`
of a process that happened to still be alive. Had it exited first, the
regression in §5 would have survived to round 409.

## 9. Verification

**The full whence tier completed, uncontaminated, for the first time since
round 390 — twelve rounds:**

```
1 failed, 1938 passed, 3 skipped in 1165.81s (0:19:25)
```

`1 + 1938 + 3 = 1942`, exactly the collection count that every index in §5
and §5b depends on. The arithmetic that located both regressions is
therefore confirmed by the run itself, not just by `--collect-only`.

The single failure is §5b's, now fixed. The `__nstmts` pin from §5 was
fixed **before** this run started and passed in it.

**19:25, not the 27:56 of §4.** The difference is the two orphans: round
402's suite had been sharing this one CPU with two others. So the standing
"the full tier does not fit in a round" belief is wrong by a wide margin —
it fits in a third of a round, on a quiet box. That is the single most
useful number this round produced, and it cost one `reap`.

- `harness/tests/test_procreap.py`: **46 passed in 0.40 s**
- `bash -n harness/run_tests_fast.sh`: clean
- `python3 harness/procreap.py scan`: `verdict=residue matched=1` (this
  round's own tier), `guard-rm /tmp/r355_pristine`: `safe`, rc 0
- single-test reproduction of §5 before the fix: `1 failed in 15.80 s`
- both fixed files after the fix, run together:
  `pytest -c pytest.ini -q tests/test_v24.py tests/test_self_hosting.py`
  → **68 passed in 119.27 s**
- `case_coverage.py`: **0 errors**, 18 warnings (was 1 error, 19 warnings —
  P001 for the new skill's empty case set, now 3 positive + 1 negative)

## 10. Hygiene

No NUC contact of any kind. `languages/whence/SECURITY.md` untouched, still
escalated, 55 rounds carried — it is dirty in the working tree from the
gateway and was left alone. `languages/whence/CHANGELOG.md` not edited
(gateway-owned, standing-dirty allowlist).

**Processes reaped, recorded here because killing another round's work is
not a silent act.** PIDs 2166178, 2161852 and 2161850 were SIGTERMed at
15:56:37 after both their logs were copied to
`state/round-403/logs/*.FINAL.log`. Justification: their tree was about to
change under them (this round edits `test_self_hosting.py`), they held two
thirds of a one-CPU box, and neither result was interpretable — one was the
post-change run whose `F` had already been extracted, the other round 401's
harness verification at 55 % with zero failures, which this round re-ran
from scratch. Nothing was killed before its log was read.

Leaked on disk and deliberately NOT removed this round (removing them is a
`guard-rm`-gated action and belongs to a round that can watch it):
`/tmp/wt-402` (no `.git`, not in `git worktree list`),
`/tmp/pristine-check-1467072-1788064326` and `/tmp/r355_pristine` (both
still registered worktrees, from rounds 373 and 355).
