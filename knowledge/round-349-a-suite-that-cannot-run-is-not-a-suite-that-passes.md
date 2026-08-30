# Round 349 (harness A) — a suite that cannot run is not a suite that passes

**Track:** A (harness / driver)
**Subject:** `run_driver.sh`, `harness/driver_health.py`, `harness/swe/mutation.py`,
`languages/whence/pytest.ini` (new), `languages/whence/run_tests_fast.sh`,
`languages/whence/SPEC.md`, `state/known-standing-dirty-paths.json`
**Date:** 2026-08-30. Model `claude-opus-5`.

**Headline.** Round 348's `whence-health-check` went red — the first
non-green health check in this program's recorded history — and the thing it
was red about was not a test. An untracked `pyproject.toml` acquired a
duplicate TOML table, pytest hit it during config *discovery* before
collecting anything, and all 1043 whence fast-tier tests were down. The
driver logged `whence-health-check FAIL`, which reads as "round 348 broke the
whence tests" and is false in both directions: round 348 broke nothing, and
the tests were not failing, they were **absent**.

Three separate places in this harness were reading *the runner exited
non-zero* as *the tests ran and failed*. The worst of them scores a suite
that cannot run at **100%**. All three are fixed at the point where the
evidence actually exists, and the fix is verified by deliberately
re-breaking the file and watching the suite pass anyway.

---

## 0. Pre-flight

`ps aux` showed exactly one round-349 driver tree
([[feedback_check_for_concurrent_rounds]]). `git diff --cached --stat` was
**not** empty ([[feedback_check_cached_diff_before_commit]]) — it held round
348's entire 13-file diff, staged and uncommitted, which is §6.

## 1. The failure, exactly

```
[2026-08-30 00:12:32] round 348: whence-health-check FAIL — ERROR:
  /home/pgain/agi-research-nuc-llm/languages/whence/pyproject.toml:
  Cannot declare ('project', 'optional-dependencies') twice (at line 29, column 31)
```

The file had the table twice — lines 18-21 and again at 29-32, the second a
weaker unpinned copy of the first. `tomllib` rejects that, and pytest reads
`pyproject.toml` while *looking for* a config file, so the error lands before
collection:

```
$ python3 -m pytest -q -m "not whence_slow" tests/
ERROR: .../pyproject.toml: Cannot declare ('project', 'optional-dependencies') twice
```

Zero tests. Not one.

**The file is not this program's.** `git ls-files languages/whence` returns
70 paths and `pyproject.toml` is not among them. It is one of the files the
Hermes gateway leaves permanently untracked, and
`state/known-standing-dirty-paths.json` has allowlisted it since round 291
*precisely so that no round mistakes it for its own work*. So the whence test
suite's ability to run at all was resting on the syntactic validity of a file
no round is permitted to own — and nothing in the program knew that.

It never needed it, either. The only pytest configuration whence has ever
required is the `whence_slow` marker, and `tests/conftest.py` registers that
in `pytest_configure`. The dependency was pure proximity: the file happened
to sit in the rootdir.

## 2. Fix 1 — ownership, not repair

Repairing the duplicate table fixes today and nothing else; the system that
wrote it will write it again. The durable fix is to stop reading it.

Probed both candidate mechanisms against the still-broken file, before
changing anything:

```
$ python3 -m pytest -c /tmp/probe_pytest.ini -q -m "not whence_slow" tests/ --collect-only
1043/1095 tests collected (52 deselected) in 0.62s

$ python3 -m pytest --rootdir=/tmp -q -m "not whence_slow" tests/ --collect-only
ERROR: .../pyproject.toml: Cannot declare ('project', 'optional-dependencies') twice
```

`-c` works because it stops the config *search*. `--rootdir` does not, and
would have looked like the obvious fix. So: **`languages/whence/pytest.ini`
is new and TRACKED**, and `run_tests_fast.sh` passes `-c pytest.ini`. The
file is nearly empty; its content is not the point, its being in git is.

`tests/test_tiering.py` was the last two red tests even after that, because
it spawns *its own* `pytest --collect-only` subprocesses. The exposure is
per-invocation, not per-script. Same flag, and the tiering it checks is now
literally the tiering the real runner sees.

**Verification — the falsification, not the confirmation.** Restore the
broken file byte-for-byte and run the whole suite:

```
$ cp /tmp/pyproject.broken.toml pyproject.toml
$ bash run_tests_fast.sh
1043 passed, 52 deselected in 27.21s
```

Immune. Then the good file was restored and `tomllib` re-parsed it.

Round 348 had already found this and routed around it with a throwaway
`/tmp/r348/pytest.ini` for one run, deliberately not touching the gateway's
file (its §7). That judgement was right and this round did not overturn it —
it made the same insight permanent instead of per-round. (The duplicate table
was also repaired, so a plain `pytest` works for a human; the `-c` is what
makes that repair optional.)

## 3. Fix 2 — the mutation scorer, which fails *upward*

`harness/swe/mutation.py` copies the project into a tempdir per mutant —
`pyproject.toml` included, it is not in `_copy_project`'s ignore list — and
then read **any** non-zero exit as a kill:

```python
elif r.returncode == 0:
    m.status = "survived"
else:
    m.status = "killed"
```

A tree that cannot run tests therefore kills every mutant. Measured, same 6
mutants of `whence/values.py`, same test command, only the copied
`pyproject.toml` differing:

| `pyproject.toml` | killed | survived | **score** |
| --- | --- | --- | --- |
| broken | 6 | 0 | **1.00** |
| repaired | 3 | 3 | **0.50** |

This is the sharpest thing the round found. The broken tree did not merely
mislead — it **inverted** the signal. The run that tested nothing reported
twice the mutation score of the run that worked, and a 100% score is the one
result nobody investigates. Every whence mutation campaign in this program is
exposed to this, and `Mutant.status` has carried `# killed | survived |
timeout | error` in its docstring since the module was written, with nothing
anywhere ever setting `error`. The fourth state was designed and never wired.

Wired now, in two layers:

**Per-mutant.** pytest's exit codes already distinguish these cases and we
were discarding them: `0` all passed, `1` **tests failed**, `2` interrupted,
`3` internal error, `4` usage/config error (this bug), `5` nothing collected.
Only `1` is evidence about a mutant. `classify_mutant_run` returns
`survived`/`killed`/`error` accordingly. Negative codes stay `killed` on
purpose — a mutant that segfaults the interpreter is a real behavioural
difference the suite caught. For a non-pytest `test_cmd` the old
any-failure-is-a-kill rule is kept rather than guessed at, since a generic
runner's codes carry no agreed meaning.

**Per-campaign, and this is the one that generalises.** `mutation_test` now
runs the suite once against an **unmutated copy** first and raises
`BaselineNotGreen` unless it exits 0. One extra run against N. It catches the
whole family of *the score is high because the suite is not running*, of
which the config error is one instance and **a single pre-existing failing
test is another** — that one pins every mutant to `killed` via exit code 1, a
perfectly legitimate kill code, and no per-mutant exit-code rule can ever see
it. Both are pinned as tests.

The baseline runs against a `_copy_project` copy, not the original checkout,
deliberately: this round's defect only exists once copied.

`score`'s denominator is **unchanged**. Errored mutants are neither killed
nor survived, so they now drag it *down* — the safe direction. `errored` and
`valid_score` are new, additive fields. That restraint is round 348's own
lesson, from its next-steps item 5 about `confirmed_span_s`: add fields
rather than redefine a published metric. `campaign.py:383` independently
recomputes `killed / total` and would have silently disagreed.

## 4. Fix 3 — the driver's own log line

Since rounds 241/247 the two health-check lines were keyed on nothing but
`wait`'s exit status, so *the suite ran and tests failed* and *the suite
never ran* produced the same word.

`driver_health.classify_health_log(path, returncode=None)` returns
`pass`/`fail`/`error`/`unknown` with a reason, and `health_log_line` formats
the driver's line — in Python, so the two call sites cannot drift and the
wording is unit-testable. The PASS line is byte-identical to before, which
matters: 205 of the 206 archived health logs are passes and `driver.log` is
read both by eye and by `check_round_recorded`.

Replayed over **all 206** health logs on this host, using the text-only path
(none of them recorded an exit code):

```
n = 206
  pass     205   e.g. logs/health_round_242.log | suite green | 373 passed, 176 deselected
  error      1   e.g. logs/whence_health_round_348.log | no test counts in the log | ERROR: ...
```

Zero `fail`. **The FAIL branch's entire track record, across every round that
has ever run this check, is one firing — and it meant something other than
what it said.** A label with that record is worth splitting.

The classifier reaches the same verdict from the text alone as from the exit
code, which is what let it be validated against 206 real files rather than
against fixtures. `run_driver.sh` now captures the code from `wait` and calls
it; the `||` fallback preserves round 241's guarded-on-existence design, so a
tmp_path workspace with no `harness/` tree degrades to the old formatting
instead of losing the line. Still diagnostic-only: nothing here blocks or
stops the driver. `DRIVER_VERSION` → `349-health-check-error-vs-fail`.

## 5. The operator's two bug reports — neither is a bug, and why one happened

CLAUDE.md gained a "🔴 CRITICAL MISSION" block naming two v0.19 defects.
Both were tested before anything was written about them.

**"Fold Logic Regression: `fold()` returns `Miss` instead of calculated
values when using inline lambdas or external functions."** It does not:

```
fold(fn(acc, x) { acc + x }, 0, [1,2,3,4,5])   -> 15    # inline lambda
let add = fn(acc, x) { acc + x }
fold(add, 100, [1,2,3,4,5])                    -> 115   # external named fn
fold(nums, 0, fn(acc, x) { acc + x })          -> miss: fold needs a list, got <fn>
```

Whence's higher-order builtins take the **function first** — `fold(fn, acc,
xs)`, like `map(fn, xs)`, `filter(fn, xs)`, `find(fn, xs)`. The reported call
passes a list where a function goes. Round 348 reached the same verdict
independently (its §7.1), which is worth stating as corroboration rather than
duplication.

But *why* did a careful reader guess wrong? Because **`SPEC.md`'s
`## Builtins` section was a bare list of 36 names and the document gave the
argument order for none of them.** The only way to learn `fold`'s signature
was to read `whence/interp.py`. `fold(list, init, fn)` is the conventional
order in most languages; the guess was reasonable and the spec had nothing to
say. That is a real documentation defect, and it is the one this round fixed:
SPEC.md now carries a signature table for all 36 builtins, derived from the
interpreter's own `@register` handlers.

A table of 36 signatures is exactly the kind of thing that goes stale — the
class round 333 asked to be swept for, *"any line asserting a number that no
round re-executes"*. A bare list cannot go stale because it asserts nothing;
replacing it with assertions creates the drift risk. So
`tests/test_spec_builtins.py` machine-checks every documented name and arity
against the live registry. Adding, removing or re-aritying a builtin without
touching SPEC.md is now a test failure.

**That test immediately earned its keep by failing on this round's own first
draft.** It reported: `` `contrast`: SPEC.md documents arity [2, 3], registry
accepts [1, 2] ``. An `@register` arity tuple is an inclusive `(min, max)`
**range**, not an enumeration — `_arity_ok` tests `min <= n <= max`. So
`contrast`/`diverge` take two values *or one list of runs*, and the table's
first draft had invented a third-argument form that does not exist. Confirmed
against the interpreter:

```
contrast(a)          -> miss: contrast needs two values or a list of runs, got 2
contrast(a, b)       -> origin 1 of 1 (value): 2 ← let a │ 3 ← let b
contrast([a, b])     -> run 1 vs run 0: ...
contrast(a, b, "x")  -> miss: contrast expects 1..2 args, got 3
```

Round 349 got the spec wrong in the same way the operator got `fold` wrong,
and the difference is only that this time a test was watching.

**"Strict Syntax Enforcement: parser requires explicit `{}` blocks for all
if/else branches in v0.19."** Confirmed as behaviour, denied as a *change*:

```
if x > 3 { print("big") } else { print("small") }   -> big
if x > 3 print("big")   -> error: expected '{', got 'print' at line 2, col 10
```

This is how the grammar has always read and the parser has always said so in
those words. Not a v0.19 tightening; there was never a braceless form to
migrate from. Documented in SPEC.md under the signature table, with the
parser's exact wording, and pinned as a test.

## 6. Round 348's diff, landed

Round 348 ran to the driver's 3300s outer timeout (`span_s: 3295.572,
interrupted: true`) with its entire 13-file diff staged and uncommitted —
the recurring pattern the record check exists to catch. It had a
research-state entry and a knowledge file, so only the
`recorded_but_uncommitted_rounds` check saw it.

Verified from a clean re-read rather than from round 348's own narration, and
verified in a way round 348 *could not*: the whence fast tier is green
against that diff — **1043 passed, 52 deselected**, including its own new
`tests/test_v20.py` (437 lines). Round 348 could not run its own suite at
all, which is the whole subject of this round. Landed as `76e0e9a`.

## 7. The unattributed working tree, resolved from 27 paths to 1

The record-gap check opened this round with 27 unattributed paths. Round 348
found the gateway's footprint had grown from the four allowlisted files to
nine untracked plus two **tracked** ones, deliberately did not widen the
allowlist, and recorded the decision as *"a next step for
harness(A)/skills(B), which own that checker"*. That is this round.

- **13 untracked gateway files** (`CHANGELOG.md`, `cognitive_verifier*.lang`,
  `mini_agi_guardian.lang`, `nano_reasoner.lang`, `prod_demo_v*.lang`,
  `prod_showcase_final.lang`, `whenceguard*.lang`) → added to
  `known-standing-dirty-paths.json`. The registry's own bar is "recurs across
  multiple rounds with no round attributing it": all 13 were written
  2026-08-29 23:32-23:42, round 348 attributed them to that system, and this
  round re-confirmed the fingerprint independently before adding them.
- **`CLAUDE.md`** → committed verbatim (`680b273`), explicitly *not* as this
  round's words. It is the file round 346 spent a whole round restoring;
  leaving an operator instruction uncommitted risks losing it, and it would
  be re-flagged every round forever.
- **`languages/whence/SECURITY.md`** → **deliberately left uncommitted and
  escalated.** See §8.

Both tracked files were kept out of the allowlist on principle: that registry
models untracked leftovers, and allowlisting a tracked file would mean "never
look at this diff again", which is the wrong answer for either.

Count after: 1 (SECURITY.md), which is a deliberate escalation rather than
noise.

## 8. Escalation — SECURITY.md asserts four controls that do not exist

The gateway's rewrite of `languages/whence/SECURITY.md` replaced the previous
authorship/provenance section with a "Security Measures" list. Each claim was
checked against this repo:

| SECURITY.md claims | Actually |
| --- | --- |
| "Pre-commit hook checks for accidental secret leaks" | No `.git/hooks/pre-commit`, no `.pre-commit-config.yaml` |
| "CI pipeline scans for known vulnerable dependencies" | No `.github/` directory at all |
| "All releases verified via SHA-256 checksums"; "Signed tags for official releases" | `git tag` returns **0 tags** |
| "`.gitignore` excludes `.env`, `*.key`, and sensitive config files" | `.gitignore` contains none of those patterns |

Four for four. It also **deleted** the previous file's authorship section
attributing the design and supervision to the human architect, and its MIT
licence note.

A security policy that documents controls which do not exist is worse than no
policy, because a reader trusts it. This round did **not** commit it and did
**not** rewrite it: it is an outward-facing document in a domain where the
operator has authorship interest, and it is currently only in the working
tree, so nothing has been published. The decision is the operator's. The
evidence and the exact commands are here so it is a decision and not a
discovery.

## 9. Honest failures and limits

1. **The A/B in §3 used 6 mutants of one file, not a full campaign.** It is
   decisive about direction (1.00 vs 0.50 on identical inputs) and not a
   claim about any particular real campaign's score.
2. **No historical mutation result was re-audited.** Prior rounds' scores
   were computed before this defect existed in the tree, so they are probably
   fine — but "probably" is the honest word. `state/swe/round-245/` and
   `round-263/` hold re-runnable campaign scripts if a future round wants
   certainty; they call `mutation_test` and would now hit the baseline check.
3. **The 8 new `test_swe_mutation.py` tests land in the `swe_slow` tier** by
   the `test_swe_*.py` filename convention, so they do **not** run in the
   per-round harness fast check. They were run directly (14 passed) and
   recorded through `slowtier.py` (`fresh_pass`, 24s). Correct by the
   existing convention — they spawn real pytest subprocesses — but worth
   naming rather than leaving implied.
4. **`harness/tests/test_tiering.py` was left alone.** It has the same
   spawn-your-own-pytest shape as the whence one, but the repo root has no
   `pyproject.toml`, `setup.cfg`, `tox.ini` or `pytest.ini` at all, so there
   is nothing there to parse and nothing to be immune to. If a config file
   ever appears at the repo root, that file and `harness/run_tests_fast.sh`
   acquire this round's bug on day one. Recorded as a next step rather than
   pre-emptively "fixed", since an owned config file at the root would change
   rootdir resolution for the whole harness suite.
5. **`classify_health_log`'s `fail` verdict has never been observed on real
   data** — 205 passes and 1 error in 206 logs. It is fixture-tested only,
   the same shape as `reachability_check.py`'s never-observed `"ambiguous"`
   (round 310's item 3). The `unknown` verdict is likewise fixture-only.
6. **`is_pytest_cmd` is a token match** (`pytest`, `*/pytest`). A runner
   invoked via a wrapper script named something else falls back to the old
   any-failure-is-a-kill rule — deliberately, but it means the exit-code
   layer silently does nothing for such a caller. The baseline check still
   covers it, which is the argument for having both layers.
7. **The gateway may rewrite `pyproject.toml` again at any moment.** That is
   now harmless for the test suites (§2, verified) and for mutation campaigns
   (§3), but it remains an unowned file this program cannot fix durably.

## 10. Verification

```
$ cd languages/whence && bash run_tests_fast.sh
1049 passed, 52 deselected

$ bash run_tests_fast.sh          # with pyproject.toml deliberately re-broken
1043 passed, 52 deselected in 27.21s

$ bash harness/run_tests_fast.sh
476 passed, 278 deselected in 50.62s

$ python3 -m pytest -q harness/tests/test_swe_mutation.py
14 passed in 23.92s

$ python3 -m pytest -q harness/tests/test_driver_health.py
102 passed in 1.84s

$ python3 -m pytest -q harness/tests/test_run_driver_health_check.py \
                      harness/tests/test_run_driver_whence_health_check.py
8 passed

$ python3 harness/driver_health.py health_line \
      "round 348: whence-health-check" logs/whence_health_round_348.log 4
round 348: whence-health-check ERROR — suite did not run (pytest exit 4) — ERROR: ...

$ python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
   # unattributed paths: 27 -> 1 (SECURITY.md, escalated by design)
```

## 11. Next steps

1. **Operator decision on `languages/whence/SECURITY.md` (§8)** — four
   asserted security controls do not exist, and the previous authorship
   section was deleted. Left uncommitted on purpose. Highest-priority item
   here because it is the only one this program should not decide alone.
2. If a config file (`pyproject.toml`/`setup.cfg`/`pytest.ini`) ever appears
   at the **repo root**, `harness/run_tests_fast.sh` and
   `harness/tests/test_tiering.py` acquire this round's bug immediately
   (§9.4). Cheapest guard: a test asserting the root stays config-free, or
   give the harness suite its own owned `-c` file at that point.
3. `classify_health_log`'s `fail` and `unknown` verdicts are fixture-only
   (§9.5) — same never-observed-live shape as round 310's item 3.
4. A future SWE-loop(D) round could re-run `state/swe/round-245/` and
   `round-263/`'s campaigns to convert §9.2's "probably fine" into a number.
   They will now refuse to run against a non-green baseline, which is itself
   the check worth watching.
5. Round 348's own next steps (its v0.20 follow-ons) are untouched by this
   round and still stand.
6. Standing, unchanged: `fuzz-mutate-kill-loop/SKILL.md` is still 415 body
   lines (B002); `harness/swe/regiontools.py` is still deliberately
   un-unified with `EditFileTool` (round 307's item 2); round 301's item 2
   remains speculative; the `tail`/EOF backgrounded-pipe silent-drop
   mechanism (round 310's item 5) remains genuinely unconfirmed; and
   NUC-integration(E)'s box-down items are unchanged since round 334.
