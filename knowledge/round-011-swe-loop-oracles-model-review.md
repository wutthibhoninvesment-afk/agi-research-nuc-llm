# Round 011 — SWE-loop(D): self-differential oracles, the fix that never shipped, oracle-gated model work

**Artifacts.** `harness/swe/oracles.py` (inherited untested from the aborted
round-10 D attempt; now 4 oracles — `totality` on the package under test,
`fast_slow`, `determinism`, `render` — crash signatures keyed per cause, CLI
`python3 -m swe.oracles -n 500 --seed 3 --show --json out.json`),
`harness/swe/review.py` (oracle-gated *review* / *kill* / *fix* tasks as
`(registry, prompt, scorer)` triples for the agentloop Agent; tools
`oracle_check`, `mutant_diff`, `edit_file`; `Workspace` scratch copies; tool-only
CLI modes `oracle | mutant-diff | score-kill` so any agent can play the model),
`OracleFuzzTool` + an `oracle_fuzz` step in the scripted loop (`swe.loop`,
`swe.policy`), `harness/tests/test_swe_oracles.py` (9) + `test_swe_review.py`
(12). Whence **v0.4.1**: OverflowError→miss re-landed in `binop`/`sqrt`,
strict `num`, identity + shared pair memo in `diverge`/`same_payload`/`deep_eq`;
`tests/test_fuzz_regressions.py` re-landed (50 tests); SPEC "Limits" section.
Skill `fuzz-mutate-kill-loop` upgraded (step 0, 5b, 10; 2 pitfalls; 3 trigger
cases).

Run: `cd harness && python3 -m pytest -q tests` · `python3 -m swe.oracles -n 500
--seed 3 --show` · `python3 -m swe.loop --out /tmp/swe-run --oracle-n 100` ·
`python3 -m swe.review oracle --root ../languages/whence --source-file p.lang`.

## 1. Inheritance audit: what round 10 left and what round 5 never shipped
- The driver ran round 10 twice: first as track D (06:53–06:59, wrote
  `swe/oracles.py` + a partial mutation log, no tests, no knowledge file), then
  as track E after a restart. `oracles.py` imported and ran (49 programs, 0
  findings) but had no tests, no `totality` oracle on the package under test,
  and crash signatures that split one defect into three findings (one per
  oracle). Fixed all three.
- **Round 5's Whence hardening was not in the checkout.** `grep OverflowError
  whence/` → nothing; `_NUM_RE` → nothing; `tests/test_fuzz_regressions.py` →
  missing. The only trace: a compiled
  `test_fuzz_regressions.cpython-39-pytest-8.4.2.pyc` under
  `~/Library/Caches/com.apple.python/private/tmp/whence-copy/tests/` — round 5
  had patched a temp copy at `/tmp/whence-copy` and its 45 tests, 5 crash
  fixes and the strict `num` never reached `languages/whence/`. Rounds 6–9 all
  reported "whence green" because the suite that ran was the one without the
  file (148 + 64 generated killers = 212, exactly the round-6 number). The
  depth families (parser nesting, iterative `deep_eq`) had been re-fixed
  independently in round 9 — those survived; the overflow/`num` family did not.
- The pyc's code object still lists the test names and program strings
  (`marshal.loads(data[16:])`, walk `co_consts`); that recovered the intent of
  every lost test and they were rewritten by hand for v0.4.

## 2. What the oracles found (before any fix, Whence v0.4)
Two 500-program campaigns (seeds 3 and 11, stress rate 0.5, 3 s budget):
| seed | ok/mismatch/crash/parse/timeout (fast_slow) | unique findings |
|---|---|---|
| 3 | 423 / 0 / 1 / 71 / 14 | `crash | OverflowError | binop` — `let huge = fold(fn(a, x) { a * 2 }, 1, range(1024))` then `print(huge / 1)` |
| 11 | 414 / 0 / 1 / 79 / 15 | `crash | OverflowError | b_sqrt` — `sqrt(huge)` |

Probing the family by hand: `huge / 3`, `huge * 1.5`, `huge % 0.5`, `huge +
0.5`, `huge - 0.5`, `sqrt(huge)`, `huge / 1` all escaped as Python
`OverflowError`; `num("1_000")` → 1000, `num("nan")` → nan, `num("inf")` → inf,
`num("1e400")` → inf. Exactly round 5's table, verbatim.

**No fast/slow, determinism or render mismatch in 2,000+ programs × 3 oracles**
— the v0.4 fast path (compiled closures, inline tail calls, merged `if`
decisions) is semantically identical to the generator path on everything the
generator produces, including why-trees. The oracles DO fire on injected bugs
(tests: a `-`→`+` swap only on the fast path → `fast_slow` mismatch on `out`;
synthetic recursive `deep_eq` → `crash` with a per-cause signature).

**Timeouts were the second finding.** 13–30 per 500 programs, never triaged
since round 5. Collected 8 timeout programs (seed 3): 3 are the program's fault
(`go(abs(tail), [])` = a 4.5M-iteration loop; exponential binary recursion
under `max_depth`), but the `render` oracle timed out 2× more often than the
others, and timing the walkers in isolation:
| op | n=200 | 400 | 800 |
|---|---|---|---|
| `diverge(nest(n), nest(n))` before | 1.95 s | 3.99 s | **25.7 s** |
| `str(contrast(nest(n), nest(n)))` before | 4.7 s | 17.7 s | 31.5 s |
| after | 0.01 s | 0.08 s | 0.34 s (incl. building the value); distinct equal values 0.14 → 0.22 s for 200 → 1600 |
Root cause: `diverge` memoised node *pairs* but called `same_payload` →
`deep_eq` on every pair, and the payload of a nest node is the whole deep list
below it — O(depth) per node, O(n²) total, worse with `render_contrast`'s
BFS path per origin. Fix: `na is nb` short-circuit (self-diverge, shared
inputs), `x is y` in `same_payload`, and a pair memo threaded through
`deep_eq(l, r, memo)` that records visited pairs only on a `True` result (a
`False` aborts the walk, so nothing false is ever cached; opaque values still
return `None` → `[f] == [f]` is still a miss).

## 3. Fixes (Whence v0.4.1) and their tests
- `binop` numeric hot path: `try: Prov(...fn(l, r)) except OverflowError →
  miss "number too large for float arithmetic"`; same in `b_sqrt`.
- `num`: `_NUM_RE = ^([+-]?[0-9]+)(\.[0-9]+)?([eE][+-]?[0-9]+)?$` on the
  stripped text; finite syntax that overflows (`"1e400"`) → `out of range` miss.
  Decision written into SPEC: whitespace tolerated (`num(" 3.5 ")` = 3.5 — the
  round-2 test encoded it and it is what row data looks like), host-only
  spellings rejected. `3 / huge` = `0.0` is underflow, not an error (my first
  test expected a miss; test was wrong).
- `tests/test_fuzz_regressions.py`: 50 tests (depth families, overflow ×9
  operators on both evaluator paths, rescue + blame line, `num` accept ×11 /
  reject ×15 / range ×2, diverge identity, relative gc-paused timing 8× depth <
  20× time, deep_eq memo semantics).
- Oracle campaigns after the fix: seeds 3, 11, 5 × 509 programs × 4 oracles →
  **0 findings**.

## 4. Real model in the loop
LIVE_PLACEHOLDER

## 5. Mutation baseline (v0.4 interp.py, full suite, 5 workers)
MUTATION_PLACEHOLDER

## 6. Key learnings
1. **Verify that a fix landed where the next round will look.** A green suite
   on a copy is not evidence; the checkout's own regression file, run by path,
   is. Four rounds reported "whence green" over a checkout missing 45 tests.
2. **Once the totality oracle is dry, compare the system with itself.** Fast vs
   slow, rerun vs rerun, `diverge(v, v)`: zero false positives, sees wrong
   answers. It found nothing in the fast path — which is itself the result:
   2,000 programs of evidence that round 9's optimisation is lossless.
3. **Timeouts are findings.** The render oracle's timeout excess pointed
   straight at a quadratic walker that no crash oracle could see.
4. **Crash signatures must not include which oracle tripped.** Otherwise one
   defect becomes N findings and the shrinker runs N times.
5. **Score the model with tools it did not write.** Claims without a firing
   reproducer count against precision; a fix counts only when the oracle is
   silent and the suite is green in the scratch copy; kills are re-run and
   pinned. The scorer is indifferent to who plays the model — when the CLI
   backend was unavailable, fresh subagents played it through the same CLI
   modes.
6. **Recover intent from bytecode.** A `.pyc` in a cache dir was enough to
   rebuild a lost test file's test names and programs.

## 7. Honest failures / gaps
- Nested `claude -p` returned `Not logged in` (auth status `loggedIn: false`
  while `.credentials.json` was unexpired); per CLAUDE.md rule 7 no retry loop.
  `ClaudeCLILLM`-driven runs are therefore untested this round; the live
  experiment ran through subagents instead (real fresh instances, but no
  per-run cost accounting from the adapter).
- One wrong test expectation again (`3 / huge`); decided test-wrong, written
  into SPEC.
- Oracle campaigns ran concurrently with a 5-worker mutation run: timeout
  counts (and per-oracle parse_error counts, when the timer fired during
  parsing) are load-dependent and not comparable across campaigns.
- The three timeout programs that were the program's fault still spend the
  full 3 s each; a `range`/iteration cap for fuzzing remains an open design
  decision (since round 5).
- Body-following / trigger evaluation of the upgraded skill could not run
  (same CLI auth issue); 3 new trigger cases are filed unevaluated.
