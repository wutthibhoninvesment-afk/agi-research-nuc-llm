# Round 005 — SWE-loop(D): the harness turned on Whence — fuzz, mutate, kill

**Artifacts:** `harness/swe/` (fuzz.py, mutation.py, killers.py, tools.py,
policy.py, loop.py), `harness/agentloop/adapters.py` (ClaudeCLILLM — the
harness's first real-model backend), 5 new harness test files (+30 tests →
102 harness tests, 5s), Whence hardened to v0.2.1 (parser depth bound,
iterative `deep_eq`, OverflowError→miss, strict `num`) with
`tests/test_fuzz_regressions.py` (45 tests) and the generated
`tests/test_generated_killers.py`. New skill `skills/fuzz-mutate-kill-loop/`;
`tiny-language-implementation` gained four pitfalls.

Run: `cd harness && python3 -m swe.loop --out /tmp/swe-run` (full loop through
the agent harness), `python3 -m swe.fuzz -n 1500 --seed 2 --show`.

## The loop
```
pytest (baseline) → fuzz (totality oracle + shrinker) → mutate (511 mutants)
      → kill_survivors (differential search → generated tests) → pytest → report
```
Every engine is an agentloop `Tool`; the plan is a `PolicyLLM` (a list of
`(last_observation, state) -> AssistantTurn` steps), so the whole thing is one
traced agent run (`trace.jsonl`, 6 steps, 5 tool calls, `stop_reason=completed`).
The real model enters through `ClaudeCLILLM` for the judgement task.

## Bugs found (5 crash families, all totality violations — SPEC decision 2 said "never raises")
| # | signature (minimized reproducer) | root cause | fix |
|---|---|---|---|
| 1 | `RecursionError` in parse: `((((1))))` ×100 | recursive descent, ~12 frames per paren level, host limit 1000 | explicit depth counter at expression/unary/not/block/if entry points; `MAX_PARSE_DEPTH=300` → `ParseError("expression nested too deeply")`; `parse()` lifts the host limit to 6000 for its own duration |
| 2 | `RecursionError` in parse: `- - - 1` ×977 (also `why`/`not`/`snip` chains) | `unary()` recurses once per prefix operator | same counter |
| 3 | `RecursionError` in `deep_eq`: `nest(1500) == nest(1500)` | value walker recursive; evaluator trampolined so values nest deeper than the host stack | iterative `deep_eq` with explicit stack; left-to-right, sorted record keys |
| 4 | `RecursionError` in `b_contains` → `deep_eq`: `contains([deep], deep)` | same defect, second call site | same fix |
| 5 | `OverflowError` in `binop` / `b_sqrt`: `huge / 3`, `huge * 1.5`, `huge % 0.5`, `sqrt(huge)` with `huge = 2^1200` | unbounded ints meet bounded floats | `try/except OverflowError` → `miss: number too large for float arithmetic` |

Review findings (not crashes, found by reading `num` while writing the
string pool): Python's `int()`/`float()` accept `"1_000"`, `"nan"`, `"inf"`,
`"infinity"`, `"١٢"` — `num` now uses its own regex; `"1e400"` (→ inf) is a
miss "(out of range)". Written into SPEC as v0.2.1 "Hardening".

Fuzz numbers (in-process, 3s budget per program):
- seed 2, 1500 programs, 53s: 1277 ok / 130 crash / 83 parse_error / 10 timeout → 4 signatures.
- seed 7, 3000 programs: adds the OverflowError family (found without the hand hint).
- after fixes, seed 3, 1500 programs, 51s: **0 crash signatures** (222 parse_error — the depth templates now land as the intended `ParseError`).

## Mutation testing (interp.py + values.py, suite = 148 tests)
- Operators: cmp / bool / not / const / arith / ifneg, `ast.walk` sites, in-place
  mutate + undo, re-unparse only the enclosing top-level statement (1.9s for 388
  mutants; the first version deep-copied the module per site: 47s).
- Baseline (original code, original tests): **511 mutants, 421 killed, 90
  survived, score 82.4%**, 765s with 4 workers (9 mutants timed out at 120s —
  counted as killed). By operator: ifneg 149/153, not 33/34, cmp 64/77, const
  90/116, arith 70/99, bool 15/32.
- What survives: `%` → `*` on format strings in error paths no test executes
  (23 of 29 arith survivors), `and`→`or` in type guards where both operands are
  always true in tests, render caps (`max_depth=10`, `max_nodes=200`,
  `SHOW_LIMIT=40`), `Interpreter.eval()` (unused by `run()`).
AFTER_TESTS_PLACEHOLDER

## Real model in the loop (ClaudeCLILLM, claude-sonnet-5 via `claude -p --resume`)
Task: minimized crasher #3 + "diagnose, reproduce with `whence_run`, propose a
diff, list other places with the same defect class". Result: `completed` in 8
steps / 7 tool calls (whence_run ×2, read_file, search ×2, bash ×2), 92s,
45.8k input + 6.9k output tokens, $0.12. Diagnosis correct (native recursion in
`deep_eq`, contrasted with the explicit-stack helpers in values.py), a working
iterative diff, and — unprompted — it predicted family #1/#2: "a hand-written
recursive-descent parser recurses on syntactic nesting depth … would hit the
same RecursionError while parsing". The fuzzer had found that independently;
the model's *defect-class generalization* is the thing the fuzzer cannot do.

Adapter design: built-in CLI tools disabled (`--tools ""`), our tool specs
rendered into `--system-prompt`, model emits one fenced ```tool JSON block per
reply, continuity via `--resume <session_id>` so each turn sends only the new
observation. CLAUDE* env vars stripped so it runs nested inside Claude Code.
Malformed tool blocks become a call to `__malformed_tool_block__` so the
registry's "unknown tool" error reaches the model instead of crashing the loop.

## Key learnings
1. **The oracle is the product.** "Never raises except ParseError" turned a
   random-program generator into a bug finder with zero false positives; every
   signature was a real, fixable defect. Property first, generator second.
2. **RecursionError signatures are stack-depth dependent.** The innermost frame
   is wherever the cycle got cut; keyed naively, ddmin rejected every subset
   and the shrinker "failed". Keying on the set of functions occurring ≥2 times
   in the traceback made signatures stable across 25 extra frames.
3. **Shrinkers change semantics and that is fine.** Int minimisation turned
   `nest(n - 1)` into `nest(n - 0)` (infinite recursion → depth cap miss → a
   2000-deep list) — a smaller, *different* program with the same crash.
4. **Templates and probes find what grammar walks don't.** All five families
   came from stress templates (`nest`, paren/unary chains, `2^1200`) combined
   with probes on bound names (`x == x`, `contains([x], x)`, `x / 3`). Pure
   grammar-random expressions found nothing in 1500 programs.
5. **Trampolining moves recursion, it doesn't remove it.** Round 4 predicted
   this ("value-walking helpers"); `deep_eq` and the parser were the two
   walkers nobody had checked. Value depth is now bounded by `max_depth`
   (calls), parser depth by `MAX_PARSE_DEPTH`; every walker must be iterative.
6. **Mutation score is a test-suite metric, not a code metric.** 82% with 148
   green tests; the survivors clustered in error-message paths and render
   caps — the suite tested happy paths and *that* errors are misses, not the
   text of the miss.
7. **Define canonical behaviour once, as text.** `CANONICAL_HELPER_SRC` is
   exec'd by the generator and written verbatim into the generated test file:
   generator and tests cannot drift.
8. **Profile before blaming contention.** 60s killer tests were `generate()`
   deep-copying an 825-line AST per site; the fix (mutate in place, undo,
   re-unparse one statement) is 25× faster and the tests took 1.9s.

## Honest failures / gaps
- The generated killers' *readability* is poor (fuzz-shaped programs, shrunk);
  they pin behaviour without explaining intent. A model pass to rename/comment
  them is future work.
- `no_killer` survivors are not proven equivalent — the corpus is 400
  programs; some are corpus gaps (see list in the report section).
- Fuzz timeouts (6–10 per 1500) are not triaged: likely `range(n)` on large
  arithmetic results or runaway recursion at `max_depth=2000`; a `range` size
  cap is a pending design decision.
- The first `_sites`/`generate` version was 25× too slow and shipped into the
  baseline run (correct output, wasted 47s per `rebuild_mutants` call).
- Two of my own tests had wrong expectations (the shrinker minimised `push([1],
  2)` to `push([0], 0)`; the `not` mutant became `not not x`); fixed after
  seeing them fail — same lesson as round 4.
- `PolicyLLM` is a scripted plan, not intelligence; the loop is autonomous but
  the *judgement* was demonstrated only in one live run (one task, one model).
- Skills(B) backlog item "fresh-instance trigger-rate testing" was not folded
  in: the live runs used explicit tasks, not skill-triggering phrasings.

## Metrics summary
METRICS_PLACEHOLDER
