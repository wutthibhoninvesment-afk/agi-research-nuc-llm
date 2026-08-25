---
name: fuzz-mutate-kill-loop
description: Use when asked to find bugs in an evaluator, parser, compiler or pure library (crashes or wrong answers, not style), to harden such code before it ships, to measure or improve how much a green test suite actually proves, to generate tests automatically, to make a model prove its review claims, or to benchmark a model as a bug finder or fixer against known answers. Symptoms: "all tests pass but they prove little"; a fuzzer reports 0 crashes yet semantic bugs are suspected (fast vs reference path); fuzz-campaign timeouts nobody triaged; survivors must be split into test gaps vs equivalents; a reviewing model reads or greps for its whole budget and never runs a reproducer; a long pipeline keeps dying before it reports. Method: totality-oracle fuzzing with a shrinker, self-differential oracles, AST mutation testing with coverage triage, killer search that pins survivors as tests, a repair benchmark from killed mutants, oracle-gated model review with enforced read budgets, and a resumable checkpointed campaign.
---

# Fuzz → mutate → kill: a self-improvement loop for interpreters

## When to use (triggers)
- A language implementation, parser, or pure library claims an invariant like
  "never raises" / "every error is a value" / "total" — fuzz it.
- A test suite is green and you need to know what it *doesn't* check —
  mutation-test it; survivors are the gaps.
- Tests must be generated without a model in the loop (CI, offline) — use
  differential killer search against the surviving mutants.
- A model *is* available and you want it to review a crasher — hand it the
  minimized reproducer, not the 12-line fuzz program.

**When NOT to use:** code whose behaviour is dominated by I/O or wall clock
(mutants that only change logging, timeouts or retries survive for the wrong
reason), or suites slower than ~10s per run (mutation cost is `mutants ×
suite time`; shard or sample first).

## Steps

(`harness/swe/*.py` paths named below live in the workspace this skill was
distilled from — **not bundled with this skill**; don't try to open them.
The steps are self-contained.)

0. **Check that the last round's fixes are in the checkout, not a copy.**
   `grep` the checkout for the exception names / regex constants the
   previous round claims to have added, and run its regression test file
   by path. Round 5 of this program hardened a temp copy
   (`/tmp/whence-copy`) and every fix silently vanished; round 11 re-found
   the whole family. Checkable outcome: each claimed fix has a test in
   `tests/` that fails when the fix is reverted.

1. **State the oracle before writing the generator.** The strongest oracles
   are invariants the code already promises: "no Python exception escapes
   `run()` except `ParseError`", "`v.prov.value is v.payload`", "output of
   `f(x)` equals reference `g(x)`". Write it as one function
   `run_program(src) -> Outcome(kind=ok|expected_error|crash|timeout)`.
   Checkable outcome: the oracle classifies a hand-written crasher as
   `crash` and a syntax error as `expected_error`.

2. **Generate grammar-directed programs, plus stress templates.** A
   recursive `expr(depth)` over the language's grammar (literals, names,
   calls with correct arities, operators, conditionals) gets ~90% of
   programs parsing. Add *templates* the grammar walk would never hit:
   deep nesting built by recursion (`nest(1500)`), long literal chains
   (`((((1))))`, `- - - 1`), values that overflow the host
   (`fold(fn(a, x) { a * 2 }, 1, range(1200))`), tricky strings for parsers
   (`"1_000"`, `"nan"`, `"١٢"`). Append *probes* on bound names (`x == x`,
   `print(why x)`, `contains([x], x)`) — probes reach code paths (equality,
   rendering, walkers) a random expression rarely does.
   Checkable outcome: ≥80% of `stress_rate=0` programs parse.

3. **Run in-process with a wall-clock budget.** Subprocess-per-program is
   10–50× slower. Use `signal.setitimer(ITIMER_REAL, t)` with a handler
   that raises a private exception; classify it as `timeout`, never as a
   crash. Reset the timer in `finally`.
   ```python
   signal.setitimer(signal.ITIMER_REAL, 3.0)
   try: ... except FuzzTimeout: kind = "timeout"
   finally: signal.setitimer(signal.ITIMER_REAL, 0)
   ```

4. **Group crashes by a signature that survives re-running.** `(exception
   type, innermost function in your package, message[:40])` — except for
   `RecursionError`, where the innermost frame is wherever the cycle
   happened to be cut and changes with the caller's stack depth. Key those on
   the *set of functions that appear ≥2 times* in the traceback (the cycle);
   single-occurrence frames are entry path or the leaf helper the cut landed
   in. Checkable outcome: `signature(run(src))` is equal when called from 25
   extra Python frames deep.

5. **Shrink with the signature as the predicate.** Line-level ddmin first,
   then per-line binary search of integer literals toward 0 and of repeated
   runs (`(((`, `- - -`) toward 1 — shrink bracket runs as balanced pairs or
   every candidate is a syntax error. Expect the shrinker to change
   semantics while preserving the crash (`nest(n - 1)` → `nest(n - 0)`,
   which hits the depth cap and nests 2000 deep): that is a *valid*
   reproducer, not a bug in the shrinker. If the predicate is false on the
   input, return `None` (flaky) — never assert.

5b. **When totality reaches 0 findings, switch to self-differential
   oracles** — compare the interpreter against itself so findings are still
   zero-false-positive but semantic: (a) *fast vs slow*: every optimised
   path (`compile_fast`, inline tail calls, merged decisions) must give
   byte-identical output, checks, values AND provenance renderings to the
   reference path (`Interpreter(fast=False)`); (b) *determinism*: the same
   AST executed twice by fresh interpreters, then once from a fresh parse,
   must agree — this catches state cached on AST nodes leaking between
   runs; (c) *render identities*: for every binding `diverge(v, v) == []`,
   `contrast(v, v) == "no divergence"`, `diverge(a, b)` mirrors
   `diverge(b, a)`, and rendering never raises. Key crash signatures WITHOUT
   the oracle name (the same crash trips every oracle; one finding per
   cause) and key mismatches on the first differing why-line. Also read
   the *timeouts*: a 3s budget blown by `diverge` on a 200-deep value was
   a quadratic walker (26s → 0.3s after an identity shortcut and a shared
   pair memo), not a slow program. Implementation:
   `harness/swe/oracles.py` (`python3 -m swe.oracles -n 500 --seed 3 --show`).

6. **Mutation-test the module against the suite.** Enumerate sites with
   `ast.walk`: swap comparison operators with neighbours, `and↔or`, drop
   `not`, flip booleans, `n → n+1`, `+↔-`, negate `if` conditions. Skip
   docstrings. Apply one mutation to a deep copy of the tree, `ast.unparse`,
   write the file into a *temporary copy of the whole project*, run
   `pytest -q -x -p no:cacheprovider tests` with a timeout; non-zero exit or
   timeout = killed. Run mutants in a thread pool (the work is subprocesses).
   Checkable outcome: the original checkout is byte-identical afterwards;
   `score = killed / total` printed with the survivor list.

7. **Kill survivors by differential search, not by hand.** Load original and
   mutant as *separately named packages* (`importlib.util.spec_from_file_location`
   with `submodule_search_locations`; relative imports resolve to the new
   name) so both live in one process. Define canonical behaviour ONCE as
   source text — `{kind, printed lines, check results, rendering of every
   top-level binding}` — `exec` it in the generator and write it verbatim
   into the generated test file, so generator and tests cannot disagree.
   Diff a corpus (checked-in examples + a few hundred light fuzz programs);
   the first differing program is a killer; shrink it with predicate
   "original ≠ mutant"; emit `assert run(src) == <original behaviour>`.
   Report `no_killer` mutants explicitly: they are equivalent mutants or
   corpus gaps, and hiding them inflates the score.

8. **Verify by re-running mutation on the same code with the new tests**
   (apples to apples) *before* fixing bugs — fixing shifts line numbers and
   changes the mutant set. Then fix the crashers, add hand-written
   regression tests for each signature, and run mutation once more as the
   final number.

9. **Drive it through the agent harness.** Expose each engine as a tool
   returning a short summary (JSON goes to disk under an `outdir`), and run
   the plan as a scripted policy LLM (`steps: (last_observation, state) →
   turn`) so the whole loop is one traced, reproducible agent run. Swap in
   the real model only for the judgement step: hand it a *minimized*
   crasher and ask for root cause + diff + "other places with this defect
   class".

10. **Gate every model claim on a tool the model did not write.** Three
   task shapes (`harness/swe/review.py`): *review* — the model reads a
   region and must attach a reproducer program to every claim; the
   harness re-runs the oracles on each program and counts only claims
   whose oracle fires (metric: precision); *kill* — hand the model a
   surviving mutant's diff and a `mutant_diff` tool that runs original and
   mutant on a program; a kill is scored by re-running the final program,
   then shrunk and pinned as a test (metric: kill rate on `no_killer`
   survivors); *fix* — the model edits a scratch COPY of the checkout with
   `edit_file` (unique-match replace only) and is done only when the
   oracle is silent on the reproducer AND the suite is green in the copy;
   the unified diff is the artifact. When the CLI backend is unavailable,
   the same tools work for any agent through the tool-only modes
   (`python3 -m swe.review oracle|mutant-diff|score-kill ...`) — the scorer
   does not care who played the model.

11. **Run the whole pipeline as a resumable, checkpointed campaign.** Each
   stage (mutate → recheck timeouts → corpus-kill → verify pins →
   model-kill → review → report) writes one artifact under `--out` and
   records itself in a manifest (`campaign.json`: status/started/finished/
   info per stage); re-running the same command skips finished stages and
   resumes per-mutant from a `*.partial.jsonl` checkpoint (mutation and
   model kills append one JSON line per mutant as they finish). Adopt an
   existing mutation report with `--adopt-mutation` instead of re-running
   it. Implementation: `harness/swe/campaign.py` —
   `python3 -m swe.campaign --out state/swe/round-NNN --adopt-mutation
   state/mutation/round-NNN.json --extra-programs pins.json --live-kill 8
   --live-review --model claude-sonnet-5`. Checkable outcome: kill the
   process mid-stage, re-run, and the manifest shows the stage resuming
   with `resuming: k of n mutants already checkpointed`. Every suite run
   the campaign spawns (mutant, recheck, verify, repair, the model's
   `pytest` tool, the coverage bootstrap) goes through one helper that
   starts the child in its own session and SIGKILLs the whole process
   group on timeout (`harness/swe/proc.py::run_capped`); the regression
   test spawns a grandchild that inherits stdout and asserts it is dead
   after the cap.

12. **Re-check timeouts serially before calling them kills, and verify
   every pin against only its own test file.** A `timeout` recorded under
   N-worker load is not evidence of an infinite loop; the recheck stage
   re-runs each one alone with a longer budget and records flips
   (`mutation-rechecked.json`). A pinned killer is verified by running the
   mutant against `pytest -x <pinned file>` only — seconds instead of a
   full suite, and a pin that kills there kills in the suite. The report's
   *projected final score* = (corrected kills + verified new pins) / total,
   stated as projected because the full suite was not re-run.

13. **Give a reviewing model region tools, not a whole-file read.** A 65k-char
   source file truncated to the observation cap shows the model the imports
   and nothing else; it then greps one definition at a time and never gets
   to a reproducer (round 23: 17 `search`, 0 `oracle_check`). Provide
   `outline` (AST index: every class/def with `[start-end]` line range),
   `read_file(path, start, end)` capped at ~200 numbered lines with a
   header saying where to continue, and `search` that accepts a FILE as
   well as a directory and returns `context` lines. Say in the prompt:
   outline first, then windows. Implementation: `harness/swe/regiontools.py`.
   Checkable outcome: the review trace's tool histogram has
   `oracle_check ≥ 5` and `outline ≥ 1`.

14. **Triage survivors by line coverage before spending the corpus on
   them — no `coverage` package needed.** Run `pytest.main` in a subprocess
   after installing `sys.settrace` with a global callback that returns a
   line tracer only for code objects whose realpath-normalised
   `co_filename` is a target file (cache the alias: on macOS `/var` is a
   symlink to `/private/var`, so the module's `co_filename` and your
   realpath differ). Executable lines = `dis.findlinestarts` over the
   compiled module *recursively*; drop each `def` line from its function's
   body count (it executes at import and says nothing about calls). Every
   survivor is then `uncovered` (a test gap: write a test that reaches the
   line) or `covered` (a weak assertion or an equivalent mutant: read the
   code). Self-check: **a mutant on an unexecuted line must survive**;
   report `killed_on_uncovered` and treat a non-zero count as an instrument
   error. Implementation: `harness/swe/coverage.py`
   (`python3 -m swe.coverage --files pkg/mod.py --mutation-json m.json`).
   Checkable outcome: `killed_on_uncovered == 0` and the report shows the
   corpus kill rate on each side of the split.

15. **Benchmark the model as a fixer with mutants as injected bugs.** Every
   killed mutant is a one-token defect with a failing test and an exact
   answer. Inject it into a scratch copy, capture `pytest -x` (tail + failing
   test ids) as the CI signal, give the model region tools + `edit_file` +
   `pytest` sandboxed to the copy, and score three levels with tools it did
   not write: `green` (suite passes AND nothing under `tests/` changed —
   otherwise `cheated`), `localized` (the diff touches the mutated site in
   the INJECTED file's numbering — `ast.unparse` reflowed it, so find the
   site by diffing the identically-unparsed original against the mutant),
   `exact` (`ast.dump` of repaired == `ast.dump` of original). Sample
   round-robin over operators or the sample is one-third `ifneg`.
   Implementation: `harness/swe/repair.py`; campaign stage `repair`.
   Checkable outcome: a policy that reverts the mutated line scores `exact`;
   one that rewrites `tests/` scores `cheated`.

16. **Enforce the read budget in the tools and make a dead run still
   answer.** A prompt line ("keep half your steps for probes") was ignored:
   with region tools the model read the whole file window by window (23 of
   30 steps) and hit `max_steps` with no answer. Wrap the read tools in a
   shared `CallBudget(n)`: past n calls they return an error naming what to
   do instead, and the last three successful reads carry a `[read budget: k
   left]` footer. Turn on `AgentConfig(wrap_up_on_max_steps=True)`: when the
   step loop ends, one more completion is made with NO tools offered and an
   "answer now" user turn, so `final_text` holds the answer and the scorer
   has something to score (`stop_reason` stays `max_steps`; tool calls the
   model still emits are ignored and traced as `wrap_up.ignored_tool_calls`).
   Implementation: `harness/swe/regiontools.py`, `agentloop/agent.py`;
   `--read-budget N` on `swe.review`, `swe.repair`, `swe.campaign`.
   Checkable outcome: with budget 12 the trace histogram sums
   outline+read_file+search to ≤ 12 and `oracle_check ≥ 5`; a `max_steps`
   run has a non-empty final answer.

17. **Let a second process drive a stage of a running campaign.** Live
   model stages are network-bound and can overlap the CPU-bound mutation
   baseline, but only if the manifest is read-modify-write per stage
   (`_sync()` re-reads `campaign.json` before every mark); two drivers that
   each hold the whole manifest in memory clobber each other's marks.
   Checkable outcome: mark stage A running in process 1, stage B done in
   process 2, A done in 1 → the file shows both done.

18. **Order the suite kill-first from the previous baseline; the verdict
   cannot change under `-x`, only the time to the first failure.** Every
   killed record names the file that failed first (`FAILED
   tests/test_v09.py::…`); for a new mutant run the files that killed the
   k nearest mutated lines (same-op ties first), then the rest in default
   order (`harness/swe/prioritize.py`; campaign flag `--prioritize-from
   PRIOR.json|.jsonl`; checkpoint lines carry `killed_by`/`first_file` so
   each baseline teaches the next). Measured paired, leave-one-out, on 30
   kills: verdicts 30/30 identical, kills by a later file 0.22× aggregate
   (108 s → 1.8 s), kills by the first file unchanged — so judge it by the
   SUM of seconds, not by a median of ratios (23 of 30 kills were already
   fast; the median said "no gain" while the sum said 0.46×). Survivors
   still pay the whole suite; only a smaller suite helps them.

19. **Build a per-test-FILE coverage map once, then run only the files
   that can see each mutant.** One full `sys.settrace` run of the suite
   with a pytest plugin that switches the hit dict on `runtest_logstart`
   (`{rel: {test_file: {line: hits}}}` + seconds per file) costs ~4× the
   untraced suite (274 s for a 66 s suite; the "10–30×" folklore was
   never measured). For a mutant at `[line, end_line]`: the files whose
   tests executed one of those lines run first, cheapest first; with
   `subset=True` ONLY they run — a file that never executes the mutated
   node cannot observe the mutation, so a green covering subset is a
   `survived` verdict by construction. Lines hit only at import time
   (`<collect>` key) are covered by every file. Mutants no file covers
   run the full suite (they are the instrument's blind spot and there are
   few). Keep the instrument honest: the recheck stage re-runs a seeded
   sample of subset-survivors under the full suite and records
   `subset_flips` — one flip is an instrument error to chase, not noise.
   Implementation: `swe.coverage --by-file --out map.json`, then
   `swe.campaign --coverage-map map.json` (`--no-subset` = order only,
   `--subset-check N`). Checkable outcome: every kill's `killed_by` file
   is in the map's covering set for that line (fidelity), `subset_flips`
   is 0 or explained.

20. **Classify survivors by the code they sit in before spending anything
   on them.** Key on NAMES and one shape, not on judgement: statistics
   counters (`fast_hits += 1`, `depth > peak_depth`), host-frame budget
   identifiers (`HOST_RESERVE`, `cost = body.cdepth + 1`, `_hleft`),
   `x is None` cache guards, `"..." % args` error-message formatting,
   other. For an `if`, the text is the CONDITION, never the body (a
   counter increment inside the body would mislabel the guard). Report
   the score over all mutants AND over the behavioural set (drop
   `counter` + `budget` mutants — killed and surviving alike — from the
   denominator; the score is a property of the code class). The classes
   are not equivalence verdicts: they say which INSTRUMENT can see the
   mutant (step 21) and which pool the live model should sample from.
   `swe.triage mutation.json --show`.

21. **Kill "equivalent" survivors with instruments that are not the value
   comparison.** Three, in priority order, each pinned as a plain pytest
   from a single helper source written verbatim into the generated file:
   *modes* — behaviour under direct / trampoline / slow mode must agree
   and equal the original's (an undercharged frame budget crashes direct
   mode at the default recursion limit where the trampoline runs: a
   behaviour kill); *frames* — host frames above `exec_stmt` beyond the
   charge, via `sys.setprofile`, at the CLI's recursion limit, must stay
   under the slack (the only instrument that sees an undercharge too
   small to crash); *counters* — `fast_hits/direct_hits/direct_fallbacks/
   peak_depth` after a run (sees counter bumps, flipped cache guards and
   OVERcharges through an earlier fallback). Feed them deep non-tail
   recursion probes (`f(100)`, `f(200)`, `f(400)` at max_depth 500): the
   fuzz corpus never reaches the budget. **Run every measurement on a
   fresh thread**: the budget is `recursion limit − frames in use −
   reserve`, so counters and crash points depend on the CALLER's stack
   depth — a pin computed 40 frames deep in the harness fails in pytest.
   `in_thread(fn, timeout)` with `threading.stack_size(64 MB)`, timeouts
   by `PyThreadState_SetAsyncExc` with a `BaseException` subclass (the
   interpreter's `except Exception` swallows anything less); never nest
   two such threads or the inner one leaks on timeout. `swe.oraclekill
   mutation.json --write tests/test_oracle_killers_rNNN.py`.

## Pitfalls
- **A `RecursionError` inside the trace hook silently removes the tracer.**
  CPython drops `sys.settrace` for the thread when the trace function
  raises; a suite that lowers the recursion limit for one test
  (`setrecursionlimit(200)`) then reports zero coverage for every later
  file (round 113: `test_v10.py`/`test_v11.py` invisible, and the first
  hypothesis — a `settrace(None)` in the tests — was wrong; they use
  `setprofile`). Re-arm `sys.settrace`/`threading.settrace` at every
  `runtest_logstart`, and read the per-file hit counts before trusting a
  map: a 23 s test file with 0 hits is the instrument, not the file.
- **Counter pins that depend on the caller's stack depth.** Direct-mode
  statistics change with the entry depth (budget = limit − frames in
  use − reserve); the same program gave `direct_hits` 186 from the harness
  and a different number from a deeper call site. Measure on a fresh
  thread (step 21) — verified identical from the main thread and from
  150 frames deep.
- **Nested `in_thread` calls leak the inner worker.** An async exception
  kills the outer thread at `join`; the inner one keeps spinning at 100 %
  CPU. One thread per measurement, each with its own timeout.

Older pitfalls (one per failure the program hit, rounds 5–107) are in
[references/pitfalls.md](references/pitfalls.md): Fixes applied to a copy never ship; Fuzz timeouts are findings too; Non-deterministic RecursionError signature; Unbalanced bracket shrinking; Signal timers are main-thread only; Mutating the checkout in place; `ast.unparse` reflows the file; Corpus contamination through the module cache; Timeouts counted as survivors; Equivalent mutants treated as failures; Running the suite under CPU contention; Success removes your fixtures; Hot-path refactors manufacture equivalent mutants; Driving a multi-hour pipeline by hand from an agent session; `subprocess.run(timeout=)` kills the child, not its children; Campaign durations from `time.time()` across a laptop sleep; A `timeout` under parallel load counted as a kill; "corpus_n=0" is not an empty corpus; A def line is executed at import time; The CLI backend reads until the budget dies; Escaped newlines through a heredoc; Anchoring a test on a source line of another component.

## Verification
```bash
cd harness && python3 -m pytest -q tests/test_swe_fuzz.py tests/test_swe_mutation.py \
    tests/test_swe_killers.py tests/test_swe_loop.py       # expected: all passed
python3 -m swe.fuzz -n 300 --seed 1 --show                  # unique crash signatures listed with minimized sources
python3 -m swe.oracles -n 300 --seed 3 --show               # totality/fast_slow/determinism/render: 0 findings expected
python3 -m pytest -q tests/test_swe_oracles.py tests/test_swe_review.py   # oracles fire on injected bugs; review/kill/fix scored offline
python3 -m swe.mutation ../languages/whence whence/interp.py --limit 20   # "mutation: 20 mutants, N killed ..."
python3 -m swe.loop --out /tmp/swe-run --fuzz-n 100 --mutant-limit 30      # ends with metrics JSON, stop_reason completed
python3 -m pytest -q tests/test_swe_regiontools.py tests/test_swe_campaign.py  # region tools + resumable campaign, offline
python3 -m swe.campaign --out /tmp/camp --limit 30 --corpus-n 100 --workers 4   # manifest + report.md; re-run = instant (all stages done)
python3 -m pytest -q tests/test_swe_coverage.py tests/test_swe_repair.py tests/test_round101.py  # coverage triage, repair scoring, read budget + wrap-up
python3 -m pytest -q tests/test_swe_proc.py tests/test_swe_mutation.py -k 'grandchild or group'  # cap kills the whole process group
python3 -m swe.coverage --files whence/interp.py --args "-q -p no:cacheprovider tests/test_interp.py"  # per-def coverage; "never executed:" list
python3 -m swe.coverage --files whence/interp.py --by-file --out /tmp/map.json   # "by-file map: N test files, durations ..."; every in-process test file has hits
python3 -m swe.campaign --out /tmp/camp --coverage-map /tmp/map.json --limit 60 --workers 4  # mutants carry basis=subset/full, first_file, files_run; recheck reports subset_checked/subset_flips
python3 -m swe.triage /tmp/camp/mutation-rechecked.json --show                 # class table + score all vs behavioural
python3 -m swe.oraclekill /tmp/camp/mutation-rechecked.json --corpus 30 --write tests/test_oracle_killers_tmp.py  # KILLER modes|frames|counters lines
python3 -m pytest -q tests/test_swe_bymap.py tests/test_swe_triage.py tests/test_swe_oraclekill.py  # map/prioritizer/triage/instruments offline (real checkout for the instruments)
```
- [ ] Oracle classifies a known crasher as `crash`, a syntax error as expected
- [ ] Every reported signature reproduces from its minimized source
- [ ] Original checkout unchanged after mutation testing (`git status` / diff)
- [ ] Mutation score reported before and after generated tests on the SAME code
- [ ] `no_killer` mutants listed by id in the report
- [ ] Self-differential oracles silent on the checkout AND firing on an injected fast-path bug
- [ ] Every model claim counted has a reproducer the harness re-ran; every model fix has a diff whose copy passes oracle + suite
- [ ] Previous round's regression test file exists in the checkout and runs
- [ ] `campaign.json` lists every stage `done`; a second run of the same command finishes in seconds
- [ ] Timeouts from the parallel run were re-checked serially; flips are in `mutation-rechecked.json`
- [ ] `ps -axo pid,ppid,etime,command | awk '$2==1'` shows no `run.py`/pytest orphans after the campaign; no recorded duration exceeds the cap by more than seconds
- [ ] Review trace tool histogram shows `oracle_check` calls, not only `search`
- [ ] `killed_on_uncovered == 0` in the coverage triage (else the instrument, not the suite, is wrong)
- [ ] Repair records carry `green` / `localized` / `exact` separately, and `cheated` is counted, never folded into green
- [ ] A `max_steps` review still ends with a JSON answer (wrap-up turn traced)
- [ ] By-file map: every test file that imports the interpreter has > 0 hits; `_durations` sums to about the traced wall time
- [ ] Map fidelity: every kill's `killed_by` file covers the mutated line; `subset_flips` is 0 or each flip is explained as an instrument error
- [ ] Triage counts sum to the survivor count; behavioural score reported next to the raw score
- [ ] Oracle pins reproduce from a fresh pytest process (computed on a fresh thread), and `verify` shows each pinned mutant killed by the pinned file alone
