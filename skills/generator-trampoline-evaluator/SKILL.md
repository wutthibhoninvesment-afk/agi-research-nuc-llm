---
name: generator-trampoline-evaluator
description: Converts a recursive tree-walking interpreter in Python into a generator-driven trampoline with an explicit stack, so language-level recursion depth no longer depends on sys.setrecursionlimit and runaway recursion becomes a clean in-language error; includes tail-call elimination on top of the trampoline, a closure-compiled fast path that wins back the trampoline's speed cost (3-5x), and a budgeted host-recursion hybrid (direct mode) that skips generators until a measured frame budget runs out. Use when an interpreter, evaluator, or AST walker hits RecursionError or "maximum recursion depth", when deep or mutual recursion or long tail-recursive loops in the guest language must work, when a trampolined or generator-based interpreter is too slow (microseconds per node, "death by a thousand calls"), when asked to remove sys.setrecursionlimit hacks or add TCO / proper tail calls, or when a trampolined interpreter should recurse natively under a stack budget.
---

# Generator-trampoline evaluator (explicit stack, stdlib Python)

## Trigger conditions
- A tree-walking interpreter fails with `RecursionError` at modest guest
  recursion depth (≈10 Python frames per guest call → ~90 guest frames at the
  default limit, ~1800 with `sys.setrecursionlimit(20000)`).
- The interpreter relies on `sys.setrecursionlimit` and embedders forget it.
- Guest programs need deep or mutual recursion, or higher-order builtins
  (`map`/`fold`) that call back into guest closures recursively.
- A trampolined interpreter is correct but slow: ~15-35µs per guest frame,
  most of it generator creation/`send` and small helper calls.
- Proven on: Whence (`languages/whence/whence/interp.py`, rounds 004 + 007
  + 009 + 024 + 026 + 030): guest depth 1816 → 20000 (tunable), ~30% slowdown on fib(20);
  tail calls (round 007) run 1M-iteration loops in one frame; the fast
  path (round 009) took a tail loop from 17µs to 5µs per iteration and 1M
  iterations from 48s to 9s, 310 tests; direct mode (round 030) took
  fib(20) from 5.8 to 3.7µs/call and cut generator sends in a self-hosted
  interpreter benchmark from 1.1M to 807, 506 tests.

## Steps
1. **Make every compound `eval_X` a generator that *requests* sub-evaluations
   instead of calling `self.eval` directly.** Replace `v = self.eval(node.left,
   env)` with `v = yield (node.left, env)`. The generator receives the result
   via `send`. Return the final Value with a plain `return` (it arrives as
   `StopIteration.value`).
2. **Define exactly three request kinds** and keep them cheap:
   - `(node, env)` tuple → evaluate a node,
   - a `_Call(fn, args, line)` object with `__slots__` → call a guest value,
   - a bare generator → run it (statements, builtin bodies).
3. **Write the driver once**:
   ```python
   def _drive(self, gen):
       stack, result = [gen], None
       while stack:
           try:
               req = stack[-1].send(result)
           except StopIteration as done:
               stack.pop(); result = done.value; continue
           if type(req) is tuple:
               node, env = req
               m = self._DISPATCH[node.__class__.__name__]
               if m in self._LEAF:            # literals/names: no generator
                   result = m(self, node, env); continue
               stack.append(m(self, node, env))
           elif type(req) is _Call:
               stack.append(self._call_gen(req.fn, req.args, req.line))
           else:
               stack.append(req)
           result = None
       return result
   ```
   `send(None)` primes a fresh generator, so `result = None` after every push
   is the whole protocol.
4. **Keep leaf nodes as plain methods.** Build `_LEAF = {m for m in
   _DISPATCH.values() if not inspect.isgeneratorfunction(m)}` once at class
   creation; the driver evaluates them inline. This removes most generator
   allocations (literals dominate node counts).
5. **Higher-order builtins become generators too** (`map`, `filter`, `fold`):
   `out.append((yield _Call(fn, [x], line)))`. In the call path, detect a
   generator result with `inspect.isgenerator(r)` and `r = yield r`. A builtin
   that returns early on a bad argument still works — `return value` inside a
   generator function is a StopIteration with that value.
6. **Move the depth limit into the language.** In the closure-call generator:
   `if self.depth >= self.max_depth: return <error value naming fn and
   depth>`; then `self.depth += 1; try: result = yield (body, env) finally:
   self.depth -= 1`. The `finally` unwinds the counter on normal completion
   because the driver runs generators to exhaustion.
7. **Delete `sys.setrecursionlimit` and the `except RecursionError`** at the
   call boundary. Keep an eye on the *other* recursive paths (rendering,
   structural equality, snapshotting nested data) — they now become the
   binding constraint; cap their nesting explicitly.
8. **Expose the tunable**: constructor `max_depth=`, CLI `--max-depth N`, and
   record `peak_depth` for tests/reporting.

9. **Tail-call elimination on top of the trampoline (optional, ~40 lines).**
   - *Mark tails at parse time*: after parsing a function body, walk it
     iteratively and set `call.tail = True` on the body block's final
     expression, recursing only through `if` branches and nested blocks.
     Nothing under `let`, an operator, an argument, or a wrapping operator is
     a tail — those need the result back. Mark only inside function bodies
     (a top-level `if` must never produce a pending call).
   - *Return the call instead of making it*: in `eval_Call`, `if node.tail:
     return _TailCall(fn, args, line)` — a plain object that flows up as the
     body's *result* through the `Block`/`If` generators.
   - *Loop in the frame*: the closure branch of `_call_gen` becomes `while
     True: bind params; result = yield (body, env); if type(result) is not
     _TailCall: break; rebind from result.fn/args and continue` — no depth
     increment, no new generator on the driver stack. Route a tail call to a
     builtin / non-callable / wrong arity through the ordinary `_Call`
     request and break.
   - *Keep what wrapping nodes would have recorded*: any generator that
     normally wraps its result (Whence's `if` records the condition) must,
     when it receives a `_TailCall`, attach its pending record to the object
     (`tc.ifs.append(...)`) and pass it up; the loop completes those records
     with the final value. Whence merges the whole loop into ONE `call f`
     node with `count=N` and those records as inputs — so the trace is
     lossless but flat.
   - *Expose `max_iter`*: a tail loop is now unbounded (that is the point),
     so the depth miss no longer catches `fn spin(n) { spin(n + 1) }`. Offer
     an optional iteration cap and rewrite runaway-recursion *tests* to use a
     non-tail form (`1 + spin(n + 1)`), otherwise the suite hangs.

10. **Fast path: compile the call-free fragment to closures (round 009).**
    The trampoline exists only because guest *calls* can nest unboundedly.
    A subtree with no call node in it cannot recurse into guest code, so it
    may run on the host stack — as a tree of plain closures, no generator.
    - `compile_fast(node)`: returns `f(env) -> value`, or `False` if the
      subtree contains a call (or is taller than a cap, see pitfalls). Cache
      the result on the AST node (`node.fast`; `None` = not compiled yet).
      Compile children even when the parent is not compilable, so every
      call-free fragment (each argument of a call, each condition) still
      runs inline. Do the walk in iterative post-order — the compiler must
      not recurse on the host stack either (a 3000-term `1 + 1 + …` chain
      parses iteratively and crashed the first recursive compiler).
    - In the driver: on a `(node, env)` request, `f = node.fast or
      compile_fast(node); if f: result = f(env); continue`. Two more
      inline cases pay off: an `if` whose condition is fast (decide inline;
      evaluate the taken branch inline if it is fast, else push the `if`
      generator *with the already-evaluated condition* so nothing runs
      twice), and a tail call whose callee and arguments are all fast
      (build the `_TailCall` directly; cache the compiled `(callee, args)`
      tuple on the call node). A tail-loop iteration then needs zero
      generators.
    - **One semantics, two paths**: every operator's logic lives in a plain
      helper (`binop`, `_unary`, `_index`, `_field`, `_if_bad`, …) called
      by both the closure and the generator. Add `Interpreter(fast=False)`
      and a differential test: a corpus of ~40 expressions (every operator,
      every error path, short-circuits, blocks with lets/checks, nested
      literals) must give identical values AND identical provenance/why
      renderings both ways.
    - Expect ~2x from this alone; the rest of a 3-5x comes from step 11.
    - *Extend the compilable region to builtin calls (Whence v0.7).* A call
      to a builtin that cannot re-enter guest code (not higher-order) is as
      safe to compile as an operator — and unlocks compiling every subtree
      and function body that only calls such builtins (then calls TO those
      functions can skip their generator frame entirely: bind args, run the
      compiled body, wrap the result — same nodes, same error paths, same
      depth accounting). Gate it on a *static* never-shadowed check (collect
      every name the program binds before executing each statement; skip
      inlining for names in that set) plus a *runtime* identity check in the
      compiled call (`resolved value is the builtin`) that falls back to the
      full dynamic path — the static gate is then performance-only and can
      never change semantics, even for embedders who feed statements
      incrementally and shadow a builtin after a call site compiled.
      Measured: 15–25% on call-leaf-heavy shapes, ~0% on interpreter-style
      recursion (bodies with user calls never compile) — profile which
      shape dominates before bothering.
    - *Walk else-if chains inline (Whence v0.8).* An interpreter written IN
      the guest language dispatches on node kind with an else-if chain
      whose branches contain calls: the chain never compiles, and the
      driver pushes one `if` generator per level per dispatch (~6 for a
      6-arm chain). Instead, when an `if`'s taken branch is itself an `if`
      with a fast condition, loop down the chain in the driver, collecting
      (node, branch-taken, cond) triples outermost-first; wrap the final
      result innermost-out (or, for a tail call, append the triples
      innermost-first to the pending record). Fall back to a single "chain
      generator" only at an innermost branch that needs the trampoline.
      Keep level 1 on the pre-existing straight-line path so single-`if`
      code (fib) pays zero — the first version cost fib(20) 3–5% from loop
      setup alone. Measured: generator sends −41%, wall −8–9% on a
      self-hosted interpreter benchmark, 0% elsewhere.
11. **Then profile function-call counts, not just time.** After the fast
    path, `cProfile` showed 81 Python calls per loop iteration in Whence:
    `derived()` wrapping a constructor, `_is_num()` ×6, `env.get()` ×5, a
    fast-arg list rebuilt on every tail call. Fixes that each removed a
    class of calls: a numeric hot path in `binop` using exact `type()`
    tests and an operator table (`_NUM_OPS[op](l, r)`) ahead of the
    isinstance chain; the name-lookup loop inlined into the name closure;
    the constructor called directly instead of through a wrapper; per-node
    caches for anything recomputed per evaluation. 81 → 43 calls, another
    1.6x. Delete the general-path branches the hot path made unreachable —
    they are dead code and, for mutation testing, equivalent mutants.
12. **Check the collector.** A long guest run builds a large long-lived
    (nearly acyclic) object graph; CPython's generational GC rescans it
    every 700 allocations. Measure with `gc.disable()`: Whence lost ~50%
    of wall time to it (0.76s vs 0.50s per 100k iterations). Do not change
    GC globally in a library: raise the gen-0 threshold *scoped to the run*
    (`gc.set_threshold(50000, …)` in a try/finally that restores the old
    values), off by default (`gc_relief=False`), on in the CLI. Test that
    thresholds are restored even when the run raises.
    A second effect appears across runs in ONE process: a completed run's
    retained result graph (env + full provenance DAG) is rescanned by every
    later gen-2 pass, so run 2 of the same program measured 60%+ slower
    than run 1. `del` the old interpreter/env + `gc.collect()` between runs
    restores full speed; `gc.collect(); gc.freeze()` does when results must
    stay alive (benchmark harnesses, REPLs).

13. **Direct mode: budgeted host recursion for the calls too (round 030).**
    The fast path stops at the first call; the trampoline still charges
    every non-tail call ~3 generators and ~8 sends, and steps 10–11 leave
    that as the dominant cost. Compile subtrees WITH calls to closures as
    well (`compile_direct`, cached in a second slot next to `fast`; a fast
    closure is a valid direct closure), and give calls a generator-free
    twin of the call generator (`_call_direct`) that shares the tail-loop
    bookkeeping helpers so semantics stay single-sourced. Bound the host
    stack by a FRAME BUDGET, not by hope: at every top-level entry measure
    `sys.getrecursionlimit() − frames on the stack now − reserve` (walk
    `sys._getframe().f_back`; reserve = the fast-closure height cap + one
    fallback driver, times ~2 — Whence: bound ≈ 110, measured 94, reserve
    250; the original 350 was a guess, see step 16). Charge each direct entry the
    frames it can consume before the next call frame — `cdepth`, the
    direct-closure frames on the deepest path from the node to a call,
    computed in the same post-order pass as the fast-path height — plus one
    for the call function. When a body does not fit, run it through a
    nested driver; inside it nothing goes direct until the budget is back,
    so host depth is bounded by construction while guest depth stays a
    language tunable. Verify the charge with `sys.setprofile` counting
    call/return events at two guest depths (Whence: 4.00 frames per level
    measured, 4 charged); prove the guard is load-bearing with a subclass
    that fakes an infinite budget and must raise RecursionError. Keep the
    old mode as a flag (`direct=False`) and run a THREE-way differential
    (direct / compiled-only / pure trampoline): the third leg found a
    provenance-shape bug that the two-way differential had missed for
    four versions.
14–16. **Value-model floor, ceiling, frame-charge oracle** — once direct mode
    (step 13) exists, the remaining wins are in the per-node value model, in
    knowing the ceiling before optimising, and in an oracle that catches
    budget-arithmetic bugs no value-comparing oracle sees. Read
    [references/floor-ceiling-oracle.md](references/floor-ceiling-oracle.md)
    before starting an optimisation round beyond step 13; it holds the three
    numbered steps with their measurements.

## Exact commands
The copy-pasteable one-liners for steps 10–16 (fast-path differential,
call-count profile, three-way differential, frames-per-level measurement,
decoupling proof under `sys.setrecursionlimit(200)`) are in
[references/commands.md](references/commands.md); run them, don't retype them.

```bash
python3 -m pytest tests/ -q
```

## Pitfalls
- **Public entry points must still be synchronous**: `eval`, `exec_stmt`,
  `call_value` wrap `_drive`. Nested `_drive` calls from a builtin would
  reintroduce host recursion — that is why callback builtins yield `_Call`
  instead of calling `interp.call_value`.
- **Per-frame memory is the new ceiling, not stack.** Measure it:
  `resource.getrusage(...).ru_maxrss` at depth N. Whence: ~6KB/frame (≈4KB of
  which the retained provenance DAG), so the default cap (20000 ≈ 125MB) is
  chosen from that number, not from a round figure.
- **Snapshot/render helpers that recurse over nested data** blow up as soon
  as guest recursion builds deep structures (a 2500-deep nested list crashed
  `show_payload`). Cap nesting depth in every helper that walks values.
- **GC thrash**: building a large long-lived object graph makes CPython's
  generational GC rescan it repeatedly; `gc.disable()` halved deep-recursion
  wall time in measurement. Do not silently change GC settings in a library;
  note it for embedders.
- Expect a 20–35% slowdown from generator creation/`send`. Inline the most
  common single-statement path (`Block` with an `ExprStmt`: yield the
  expression directly instead of a statement generator) to claw some back.
- `type(req) is tuple` must come before the generator check; generators are
  iterable and a loose `isinstance` test would misroute them.

- **TCO changes test semantics silently**: every existing test/example that
  relied on "runaway recursion is caught by the depth cap" hangs if the
  runaway is a tail call. Grep for self-calls in tail position before
  enabling it; run the suite with a wall-clock alarm (`perl -e 'alarm 60;
  exec @ARGV' python3 -m pytest`) the first time.
- **Order of pending records**: wrappers attach their record while unwinding
  (innermost first); reverse per tail call to get evaluation order.
- **The fast path re-introduces host recursion, bounded by source shape.**
  Closures nest as deep as the expression tree (1-3 frames per level). A
  recursive-descent parser bounds parenthesised nesting (~11 frames per
  level, so guard it: a nesting counter that raises a parse error at ~60),
  but left-associative chains parse iteratively and can be thousands deep:
  cap the compiled tree height (`FAST_MAX_DEPTH = 100`; taller subtrees
  stay on the trampoline, their shallow children still compile) and record
  the height on the node so the cap is O(1) per node.
- **The compiled path is a differential oracle for the reference path —
  run it both ways before trusting either.** When a value carries history
  (provenance, traces, effects), the compiled path must reproduce that
  history node for node; a divergence can indict the *reference* path.
  Whence v0.7's fast/slow differential exposed that the trampoline had
  silently DROPPED deferred tail-position `if` records whenever the tail
  loop resolved in a single frame (tail call to a builtin) since v0.4 —
  430 tests had never pinned the lossy shape. Decide which side is the
  intended semantics explicitly (lossless history won), fix that side, and
  pin the recovered shape with a regression test.
- **`cumtime` under `generator.send` is not the cost of the generators.**
  Nearly all evaluation flows through `send`, so its cumulative time is
  close to total runtime; only its `tottime` (plus generator allocation in
  the pushers) is what removing generators can win. Whence round 26
  predicted 19–33% from cutting sends 41% because the plan was priced off
  cumtime; actual wall win was 8–9% (tottime said so in advance). Price an
  optimization off `tottime` of what it removes, never off `cumtime`.
- **A shared helper on the hot path is one more Python call per guest
  step.** Round 030 factored the call-wrap into `_finish_call` for both
  call paths and the trampoline mode lost ~5–8% on fib(20) — call counts
  showed why. Inline the common case (`if runs is None: return derived(…)`)
  and keep the helper for the rare merged path; re-measure the mode you
  did NOT change too.
- **Benchmark ratios taken under load are not merely noisy, they are
  biased.** With a mutation campaign at load 20, direct mode measured 2×
  faster than the trampoline on meta.lang (17 s vs 34 s); idle it was
  1.24× (4.2 s vs 5.2 s) — the generator-heavy path degrades far more
  under contention. Never publish a ratio from a loaded machine, even a
  paired one; wait for idle and use min-of-N fresh processes.
- **The budget must be re-measured per entry, not cached.** Embedders call
  from arbitrary stack depths and tests change the recursion limit between
  statements; a cached headroom would over-spend. A negative budget just
  means "trampoline only" — no special casing.
- **Do not double-count counters across paths.** A direct call is not a
  driver entry: `fast_hits` counts driver entries into compiled closures,
  `direct_hits` counts direct calls; a test asserting `fast_hits >=
  direct_hits` encoded an accident, not a semantics.
- **A list comprehension is a host frame (CPython < 3.12) and the frame
  charge did not know.** Direct closures evaluated call arguments and
  list items in comprehensions; `cdepth` counted closures only, so a
  recursion through a list literal or an argument used one frame per
  level more than it was charged. Invisible at the default recursion
  limit (~160 levels × 1 < the 350 reserve), fatal at the CLI's 6000
  (~1400 levels): `run.py` died with a RecursionError on the fuzzer's own
  deep-nesting template a full version after direct mode shipped. Two
  rules: no comprehensions (or generator expressions, or nested defs) on
  any path the charge covers — list displays for 1–2 items, explicit
  loops otherwise — and measure frames per level for EVERY shape that
  recurses (call in argument position, list literal, record field, 3+
  arguments), not just the plain `count` shape. Run the totality fuzz at
  the CLI's limit as well as the default: the reference differential
  with `--fuzz` at limit 6000 found it in 300 programs.
- **A test that keeps three big histories alive pays the collector for
  all of them.** The three-way differential over meta.lang took 27 s when
  the test held (interp, env) for every mode and 12 s when it reduced
  each run to plain data (why-tree strings, checks, counters) before the
  next mode ran; and it took 16 s for self_eval.lang when the PREVIOUS
  test's million-node cyclic garbage (Env ↔ Closure ↔ Prov) was still
  uncollected — `gc.collect()` before each run made it 1.7 s. Raising the
  gen-0 threshold (`gc_relief`) does not help with either: gen-2 passes
  still traverse everything live.
- **A differential script without the CLI's GC setting measures the
  collector, not the interpreter.** `ref_diff.py` took 9.7 s on two runs
  of a 100 k-iteration loop that the bench runs in 0.4 s each until it
  passed `gc_relief=True` like `run.py` does. Any new driver must copy
  the CLI's constructor arguments.
- **Timing tests must not measure the collector.** A relative test (fast
  vs `fast=False` in-process) that ran second inherited a bigger heap and
  lost to GC; `gc.collect(); gc.disable()` around both timings made it
  stable (`fast * 1.4 < slow`). Absolute numbers belong in a bench script
  run in a fresh process, not in the suite.

## Verification
- A guest recursion of depth ≥ 3000 succeeds with `sys.setrecursionlimit(200)`
  in the test process.
- Runaway recursion returns the language's error value with the depth in the
  message, and `interp.depth == 0` afterwards; the program continues.
- Recursion *through* a higher-order builtin (`fn t(n) { map(t, [n-1]) }`)
  succeeds at depth ≥ 2000 under the same tiny host limit.
- The original test suite passes unchanged (the trampoline is a refactor of
  control flow, not semantics).
- With TCO: a 100000-iteration tail loop succeeds with `max_depth=50` and
  `peak_depth == 1`; mutual tail recursion (`even`/`odd`) likewise; a call
  under `let`/`rescue` still counts a frame (`tail_calls == 0`).
- With the fast path: the differential corpus passes both ways;
  `interp.fast_hits > 0` on any call-free expression and `== 0` under
  `fast=False`; a 3000-term chain evaluates (tall part on the trampoline);
  the fuzzer's totality oracle still reports 0 crash signatures; a tail
  loop is ≥1.4x faster than `fast=False` with GC paused.
- With direct mode: the three-way differential (direct / `direct=False` /
  `fast=False`) is byte-identical on why-trees, output, check records and
  depth counters; a 15000-deep non-tail recursion under the DEFAULT
  recursion limit succeeds with `direct_fallbacks ≥ 1`, and the same
  program with the budget faked to infinity raises RecursionError; running
  from inside a 650-frame-deep host stack still succeeds with
  `direct_hits == 0`; measured frames per guest level equals the charge;
  the budget is restored after every statement (`host_budget() > 0`);
  the fuzz oracles gain a `direct` leg and report 0 mismatches.
- With the ceiling measured (steps 15–16): the hand-transpiled hot body
  and the ablated call function are both timed BEFORE any build and the
  numbers are in the spec; the frames oracle is silent on the corpus,
  reports its maximum in every outcome, fires on an injected uncharged
  frame per call and is skipped (ok) on packages without direct mode; the
  reserve probe's corpus maximum is below the configured reserve with
  margin; the fuzz campaigns run at the CLI's recursion limit as well as
  the default.
- With the value-model floor (step 14): the reference differential
  (working tree vs `git show HEAD:` package) reports 0 differing
  (example, mode) pairs with `--counters`; a corpus of every operator ×
  operand kind (int/float/mixed/bool/str/list/record/miss/function, zero
  divisors, int-meets-float overflow) is three-way identical; a
  sabotaged reference copy (one wording changed) makes the differential
  exit 1 on the examples that contain that construct and SAME on those
  that do not; retention per iteration is unchanged to the byte; the
  Python-call count of the big example drops (≥ 30 %) while every node
  count stays the same.
