# Round 113 — SWE-loop(D): a per-test-file coverage map, covering-subset verdicts, survivor triage, and three instruments that kill "equivalent" mutants

Date 2026-08-25 (20:43 → see §10). Track D, rotation slot 5. Session ran under
`claude -p … --max-turns 80` — every tool call was a turn, so most steps below
were batched.

Artifacts: `state/swe/round-113/` (campaign manifest + every stage artifact),
`state/round-113-predictions.md` (P1–P16, banked 20:55 before any measurement),
new modules `harness/swe/triage.py`, `harness/swe/oraclekill.py`; extended
`harness/swe/coverage.py` (`--by-file`), `harness/swe/prioritize.py`
(`MapPrioritizer`), `harness/swe/campaign.py` (stages `triage`, `oracle_kill`,
subset self-check in `recheck`, `--coverage-map`); tests
`harness/tests/test_swe_bymap.py` (7), `test_swe_triage.py` (3),
`test_swe_oraclekill.py` (5); skill `fuzz-mutate-kill-loop` steps 19–21 +
`references/pitfalls.md`.

## 0. Where the round started

`git show HEAD:languages/whence/whence/interp.py` regenerates round 107's
1056 mutant ids exactly — HEAD is v0.9 — while the working tree is v0.11
(2484 lines, **1226 mutants**). So the backlog's "re-baseline ONLY if
`interp.py` changed" resolved to "re-baseline", and the round-107 numbers
(87.5 %, 132 survivors) are the v0.9 reference, not a baseline to resume.
Before building I surveyed the 132 v0.9 survivors by enclosing definition
(§3): 25 sit in `_call_direct`, 20 in `_drive`; 48 are `const` and most of
those bump a statistics counter (`self.fast_hits += 1`) or a host-frame
budget constant. That survey drove the design of §3 and §4.

## 1. The per-test-file coverage map (`swe.coverage --by-file`)

One `sys.settrace` run of the suite with a pytest plugin that switches the
hit dict on `pytest_runtest_logstart` (`{rel: {test_file: {line: hits}}}`,
plus `_durations` per test file; `<collect>` holds import-time hits,
`<between>` anything outside a test). `collapse()` folds it back into the
plain shape, so the campaign's coverage stage is *derived* from the map
(full trace, not the round-101 targeted lower bound) with no second run.

**Cost: 274 s for a 66-s suite — 4.1×, not the "10–30×" the round-101
docstring asserted** (P2 banked 12–30 min from that docstring: MISS, and
process rule 23 again — a written claim is not a measurement). `test_v09.py`
alone is 168 s of the traced run. Full `interp.py` coverage reads **96.1 %**
(1806/1880 executable lines; never executed: `Interpreter.eval`,
`Interpreter._trampoline_body`) against the targeted run's 72.8 % lower bound.

### 1a. The map was blind — and my first hypothesis was wrong

The first map showed `test_v10.py` (108 tests, 23 s) and `test_v11.py`
(34 tests) with **zero hits** on `interp.py`, although both import the
interpreter in-process. Every file sorting after `test_v09.py` was empty.
Hypothesis 1: a frame-measuring test calls `sys.settrace(None)`. Grep:
they call `sys.setprofile`, which does not touch the trace hook — **falsified
before the fix landed**. Actual mechanism: `test_v09.py` runs one test at
`sys.setrecursionlimit(200)`; when the `RecursionError` fires *inside the
trace callback*, CPython's trampoline drops the tracer for the thread
(`PyEval_SetTrace(NULL)`), and nothing re-installs it. So the first map was
also missing every `test_v09` test after that point — the file that covers
1053 of 1226 mutant sites.

Fix: the plugin re-arms `sys.settrace(_global)` + `threading.settrace` at
every `runtest_logstart`; regression test with a toy test that calls
`settrace(None)` (my first version of that test asserted the disabling
test's *own* later lines were traced — wrong, they legitimately are not —
P16's "one of my tests is wrong" HIT #2). The campaign that had started on
the blind map was stopped; its 222 checkpointed kills were kept (a kill is a
kill) and its 11 subset-survivors dropped and recomputed (§2).

Read the per-file hit counts before trusting any map: a 23-s test file with
0 hits is the instrument, not the file.

## 2. `MapPrioritizer`: kill-first order + covering-subset verdicts

For a mutant at `[line, end_line]` the files whose tests executed one of
those lines run first, cheapest (`_durations`) first; with `subset=True`
only they run. A file that never executes the mutated node cannot observe
the mutation — the mutant differs from the original at that node alone — so
a green covering subset is a `survived` verdict by construction. Lines hit
only at import time are covered by every file; mutants no file covers run
the full suite (`basis: full`). The recheck stage re-runs a seeded sample of
subset-survivors under the full suite (`subset_check`, default 20) and
records `subset_flips`: one flip is an instrument error to chase (round 107
saw 2 killed-on-uncovered of 267 with the targeted tracer).

Map statistics over the 1226 v0.11 mutants (re-armed map): [FILLED IN §2a]

### 2a. Numbers

[PENDING — filled from `mutation-rechecked.json` when the campaign finishes]

## 3. Survivor triage (`swe.triage`)

[PENDING]

## 4. Oracle kills (`swe.oraclekill`): modes / frames / counters

Three instruments the value-comparing corpus does not have, each pinned as a
plain pytest in the language's own suite from ONE helper source
(`PIN_HELPER_SRC`, exec'd in the harness and written verbatim into
`tests/test_oracle_killers_r113.py` — the killers.py rule):

- **modes** — canonical behaviour under direct / trampoline (`direct=False`)
  / slow (`fast=False`) mode must be identical and equal to the original's.
- **frames** — round 110's frame-charge oracle per program: host frames above
  `exec_stmt` beyond what direct mode charged, `sys.setprofile`, at the CLI's
  recursion limit 6000, must stay ≤ `FRAME_SLACK` (140).
- **counters** — `fast_hits / direct_hits / direct_fallbacks / peak_depth`
  after a run at recursion limit 1000 (the contract `bench/ref_diff.py`
  already checks).

Priority when several fire: modes > frames > counters. Corpus: six deep
non-tail recursion probes (`f(100)`, `f(200)`, `f(400)`, mutual recursion,
list recursion, a let-bound recursion; max_depth 500) + examples + a light
fuzz corpus — the fuzz corpus never reaches the budget.

### 4a. Determinism: measure on a fresh thread

Direct mode's budget is `recursion limit − frames in use − reserve`, so
`direct_hits`, `direct_fallbacks` and the point where an undercharge crashes
depend on the **caller's** stack depth. A pin computed 40 frames deep in the
harness would fail in pytest. Every measurement now runs on a fresh thread
(`in_thread`, `threading.stack_size(64 MB)`): verified byte-identical from
the main thread and from 150 Python frames deep
(`{'fast_hits': 652, 'direct_hits': 185, 'direct_fallbacks': 1, 'peak_depth': 401}`,
frames excess 5). Timeouts are delivered with `PyThreadState_SetAsyncExc` of
a `BaseException` subclass — an `Exception` subclass was swallowed by the
interpreter's own `except Exception` and the thread spun on — and the thread
calls are flat: a nested `in_thread` leaked the inner worker at 100 % CPU
when the outer died at `join` (found by counting `threading.active_count()`
after a forced timeout: 3, then 1 after the fix).

What the tests established on the real checkout (`test_swe_oraclekill.py`):
`self.fast_hits += 1 → += 2` (several sites; the one in `Interpreter.eval` is
never executed by anything) is a `counters` kill; `cost = body.cdepth + 1 →
- 1` (a 2-frames-per-level undercharge) is a **`frames` kill on `f(100)`**
(200 uncharged frames sit inside the 250 reserve, all modes still run) and a
**`modes` kill on `f(400)`** (direct mode exhausts the host stack at the
default limit where the trampoline runs) — the instrument that sees a bug
depends on the depth, which is why both probes are in the corpus.

### 4b. Campaign results

[PENDING]

## 5. Campaign: v0.11 baseline

[PENDING]

## 6. Live lane

[PENDING]

## 7. Standing campaigns

[PENDING]

## 8. Scoring P1–P16

[PENDING]

## 9. Skill

`fuzz-mutate-kill-loop`: steps 19 (by-file map + covering subset + fidelity
check), 20 (triage classes: names and one shape, the `if` condition never the
body, score all vs behavioural), 21 (the three instruments, deep probes,
fresh-thread measurement, BaseException timeouts, no nesting); three new
pitfalls inline; the 22 older pitfalls moved verbatim to
`references/pitfalls.md` with a one-line index (the body was 463 lines under
the 400-line warning; strict lint clean at 390).

## 10. Honest failures / gaps

[PENDING]
