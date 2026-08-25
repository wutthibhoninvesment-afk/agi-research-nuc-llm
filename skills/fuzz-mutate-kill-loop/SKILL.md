---
name: fuzz-mutate-kill-loop
description: Bug-finding, test-generation and model-benchmarking loop for an interpreter or any pure library: totality-oracle fuzzing with a shrinker, self-differential oracles, AST mutation testing with settrace coverage triage (test gap vs equivalent mutant), differential search that pins surviving mutants as tests, a repair benchmark that injects killed mutants as bugs and scores the model's fix, oracle-gated model review with enforced read budgets, and a resumable checkpointed campaign. Use when asked to find bugs in an evaluator/parser/compiler, measure or improve test-suite strength, generate tests automatically, benchmark a model as a bug finder or fixer against known answers, when a suite is green but proves little, when a fuzzer reports 0 crashes and you need semantic bugs, when survivors must be split into test gaps vs equivalents, when a reviewing model reads or greps for its whole budget and never runs a reproducer, or when a long pipeline keeps dying before it reports.
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
   with `resuming: k of n mutants already checkpointed`.

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

## Pitfalls
- **Fixes applied to a copy never ship.** A round-5 run hardened
  `/tmp/whence-copy` and reported green; the checkout never changed and
  the next fuzz campaign against the checkout was blind because its
  regression file did not exist. Verify fixes by running the checkout's
  own test file by path, and grep the checkout for the fix before
  writing "fixed" anywhere.
- **Fuzz timeouts are findings too.** Left untriaged since round 5, they
  hid a quadratic history walker. Collect the timeout programs, time the
  suspicious builtins in isolation at 2× sizes, and treat superlinear
  growth on a shared DAG as a bug.
- **Non-deterministic RecursionError signature.** Innermost frame varies
  with stack depth → ddmin rejects every subset and the campaign reports
  the same bug under several names. Use the ≥2-occurrence cycle set (step 4).
- **Unbalanced bracket shrinking.** Shrinking `(((` alone yields syntax
  errors for every candidate; the run never shortens. Shrink pairs.
- **Signal timers are main-thread only.** `setitimer` in a worker thread
  raises; keep fuzzing sequential and parallelise *mutants* (subprocesses)
  instead.
- **Mutating the checkout in place.** A crash mid-run leaves a mutated
  file behind. Always copy the project per mutant.
- **`ast.unparse` reflows the file.** Line numbers in the mutant differ from
  the original; keep the ORIGINAL node line in the mutant id, and never diff
  mutant text against the original for reporting.
- **Corpus contamination through the module cache.** Loading a mutant under
  the plain package name replaces the original for the rest of the process.
  Unique names per variant, and delete `sys.modules` entries when done.
- **Timeouts counted as survivors.** An infinite-loop mutant that the suite
  can't finish *is* detected; count `timeout` as killed.
- **Equivalent mutants treated as failures.** `>= 0` vs `> 0` on a length
  that is never 0 cannot be killed; report `no_killer` and move on.
- **Running the suite under CPU contention.** Killer search that takes 0.1s
  idle took 60s with two mutation runs in the background; profile pieces
  before blaming the code.
- **Success removes your fixtures.** Tests of the crash-handling paths
  (oracle classification, signature stability, the run tool's `crash`
  kind) used a real crasher — a 400-deep parenthesised expression. Once
  the interpreter fixed every crash the fuzzer could find (round 009: 0
  signatures), those tests broke. Inject a *synthetic* bug instead: compile
  a self-recursive replacement for a real internal function (`deep_eq`)
  under the package's own path so frame filters and signatures treat it as
  a real bug, patch it into the loaded module, restore in `finally`
  (`harness/tests/synthetic_crash.py`). Never keep a real bug around to
  serve as a fixture.
- **Hot-path refactors manufacture equivalent mutants.** Adding a numeric
  fast path to `binop` left the old numeric branches in the general path
  unreachable; the killer test anchored on that line and could not kill
  its mutant. When a fast path makes general-path code dead, delete the
  dead code the same commit — and re-anchor mutation tests on a live site
  (the string-concat `+`, killed by `let a = "x" + "y"`).
- **Driving a multi-hour pipeline by hand from an agent session.** Rounds
  17 and 23 of this program each spent a full turn budget interleaving
  mutation runs, kill attempts and reviews, died at max-turns, and left an
  incomplete log, an empty output file and unscored predictions. Launch
  the campaign runner with `nohup … < /dev/null &`, write predictions
  first, and read the manifest — the round survives its own death.
- **A `timeout` under parallel load counted as a kill.** Five workers on
  six cores stretch a 20 s suite past 60 s for innocent mutants; the
  recheck stage exists because the baseline number is otherwise inflated
  by the machine, not the tests.
- **"corpus_n=0" is not an empty corpus.** The killer corpus always
  prepends the checked-in examples; two campaign tests assumed no killer
  could be found with `corpus_n=0` and went red the moment a new example
  exercised the fixture mutants' lines. Say which corpus you mean
  (`include_examples=False`) instead of relying on a count.
- **A def line is executed at import time.** Naive per-function coverage
  shows 1/111 for a function that was never called; exclude the `def`
  (and decorator) lines from the body count before calling anything
  "never executed".
- **The CLI backend reads until the budget dies.** One tool per reply and
  200-line windows make "read the whole file" 12+ steps; nothing in the
  prompt stops it. Budget the tools (step 16) and never let the review's
  only `oracle_check` be the one the wrap-up could not run.
- **Escaped newlines through a heredoc.** Patching a source file from a
  `python3 - <<'EOF'` script with a newline escape inside a triple-quoted
  replacement writes a literal newline into the target's string literal
  (`SyntaxError: EOL while scanning string literal`); double the escape
  or use the Edit tool for anything containing escapes.
- **Anchoring a test on a source line of another component.** `"provs, l
  + r)"` matched a different line after the refactor. Anchor on a marker
  comment or a unique string literal, and state in the test what behaviour
  the mutant must change.

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
python3 -m swe.coverage --files whence/interp.py --args "-q -p no:cacheprovider tests/test_interp.py"  # per-def coverage; "never executed:" list
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
- [ ] Review trace tool histogram shows `oracle_check` calls, not only `search`
- [ ] `killed_on_uncovered == 0` in the coverage triage (else the instrument, not the suite, is wrong)
- [ ] Repair records carry `green` / `localized` / `exact` separately, and `cheated` is counted, never folded into green
- [ ] A `max_steps` review still ends with a JSON answer (wrap-up turn traced)
