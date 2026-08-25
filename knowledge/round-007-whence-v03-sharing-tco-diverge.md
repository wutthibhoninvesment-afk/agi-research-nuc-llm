# Round 007 — language(C) — Whence v0.3: shared-tip lists, tail calls that merge, `diverge`

Date: 2026-08-24. Track C, third language round (after 002, 004). Target from
the round-4 backlog, in priority order: (1) bounded retention for push-in-fold,
(2) TCO reconciled with provenance, (3) `fold` node + filtered `steps`,
(4) self-hosting round 2, (5) provenance diff. All five landed; (1) landed in
a better form than planned (no retention policy at all — retention became
cheap instead).

## What was built

### 1. Structural sharing instead of a retention policy (`values.py: WList`)
The backlog assumed the fix for "20k pushes retain 20k intermediate lists"
was to *drop* history (`value` only on named nodes, or `--lean`). The
better fix: make retaining every version cheap. Whence lists are immutable,
so a list and its successor can share storage:

```python
class WList:                       # view (buf, n) over a shared Python list
    def push(self, x):
        if len(self.buf) == self.n:            # I am the buffer's tip
            self.buf.append(x); return WList(self.buf, self.n + 1)
        return WList(self.buf[:self.n] + [x])  # someone else grew it: copy
```
A view only reads `buf[:n]`, so an old value can never observe elements
appended by a newer one; the second push onto the *same* list copies.
`xs + ys` extends the same way. Sweep: 24 `isinstance(..., list)` sites in
the evaluator, every builtin that builds a list now calls `wlist()`.

| bench (`bench/retention.py`) | v0.2 | v0.3 |
|---|---|---|
| push-in-fold, n=20000 | 6.08s / 568MB | **0.26s / 30MB** |
| concat-in-fold, n=20000 | 3.82s / 1312MB | 0.56s / 45MB |
| push-in-fold, n=200000 | (not attempted) | 7.75s / 271MB — linear |

History is *fully* retained: `test_push_in_fold_retains_full_history_in_
linear_memory` finds all 2000 `push` nodes in the DAG and asserts they all
report one `id(buf)`.

### 2. Tail calls that merge, not forget (`interp.py: _TailCall`)
Round 4's blocker: "call-node wrapping keeps calls out of tail position". The
resolution:
- **Parser** marks tails (`mark_tails`): the body block's final expression,
  through `if` branches and nested blocks only; `Call` nodes got a `tail`
  slot. Nothing under `let`/`rescue`/operators/args/`why`/`snip`/`check`.
- **`eval_Call`** returns a `_TailCall(fn, args, line)` *as its value* when
  tail. `Block` passes it through. **`eval_If`**, which normally wraps the
  branch in an `if took X-branch` node with the condition as input, instead
  attaches an incomplete `Prov("if", which, line, (cond.prov,))` to
  `tc.ifs` and passes it up.
- **`_call_gen`** loops: rebind params, evaluate body, if the result is a
  `_TailCall` to a closure, rebind and continue in the same frame (no depth,
  no host stack). Tail calls to builtins / non-callables / wrong arity go
  through the ordinary `_Call` request and end the loop.
- **Provenance**: one node `call f` (or `call even/odd`) with a new
  `count` slot (= frames merged, rendered `call go ×6`) whose inputs are the
  final result followed by every iteration's `if` node, completed with the
  final value (which is exactly what each `if` expression evaluated to —
  tail semantics make that literally true). Lossless, flat.
- `max_iter` (constructor / `--max-iter`) turns a too-long loop into a miss;
  default unbounded. `interp.tail_calls` counts elided frames.

Numbers: 100000-iteration loop under `max_depth=50` → `peak_depth == 1`.
tail-loop n=50000: 1.8s/278MB → 1.27s/67MB. n=1,000,000: 48s / 1.35GB —
history retained per iteration (one `if` node + the `arg` chain) is ~1.3KB.
Cost per merged frame ≈ 35µs (Env + arg nodes + If/Binary generators).

### 3. `fold` node + `steps(x, name)`
`fold` now yields `fold <n> items` with inputs (final acc, list). Fixes the
round-5 "fold has no node" quirk; `at(total, "fold")` works. `steps` gained
an optional name filter using the same `matches_step` predicate as `at`
(factored out of `find_step`). Step records gained `count`.

### 4. `diverge(a, b)` — origin of difference between two histories
Lockstep walk over two DAGs, memoised on node pairs, iterative:
- ops or input counts differ → origin, kind `"step"`;
- else recurse; if all input pairs are the same but detail (for non-naming
  ops) or value differs → origin (`"step"` / `"value"`);
- if some input pair differs → *not* an origin (consequence, upstream).
`NAMING_OPS = {let, note, snipped}` are exempt from detail comparison: `let
a` vs `let b` is not a divergence (first draft reported it — tests caught
it). Misses agree when their reasons agree. Returns `@{kind, a, b}` records
of step records, innermost first. Flagship: `examples/diverge.lang` — two
daily reports, one with a `"3O"` typo; `diverge(monday, tuesday)` returns
exactly one origin: the literal at line 16 became the literal at line 21.

### 5. Self-hosting round 2 (`examples/meta.lang`)
Guest language gained `fun x => body` closures, application `f(x)`,
self-naming `let` (a let-bound closure gets `self: name` so it can recurse —
`let is_fn = (raw.kind == "closure") rescue false` is the idiom for "if this
is a record with .kind"), higher-order functions. **Host TCO gives the guest
constant-stack loops for free**: `meta_eval` reaches a guest body in tail
position, so 30000 guest iterations run under a host `max_depth` of 20000
(would have been a depth miss in v0.2). 23 guest checks.

### 6. Lazy snapshots (`Prov.show` property)
Profiling the guest loop: **67% of evaluation time was `show_payload`** —
the eager per-node preview string, whose original justification ("rendering
never needs the value") died in v0.2 when `Prov.value` was added. Now a
`_LAZY` sentinel + property. Guest loop(30000): 35s → 14.5s; push-in-fold
20k: 0.48s → 0.26s.

## Tests
`languages/whence`: **243 passed in ~49s** (was 212 / 3.2s). New
`tests/test_v03.py` (28 tests: 7 WList, 4 fold/steps, 11 tail calls incl.
parser marking, else-if chains, builtin/non-callable/arity in tail position,
`max_iter`; 6 diverge) + 3 example tests (`tco`, `diverge`, `--max-iter`
flag composition). 11 examples run (`tco.lang` 7 checks, `diverge.lang` 11,
`deep.lang` 6, `history.lang` 14, `meta.lang` 23).
Standing checks: harness 148 passed (one test re-anchored, see failures);
`skill_lint --house --strict skills/`: 8 skills, 0 errors, 0 warnings.

Final run output:
```
$ perl -e 'alarm 300; exec @ARGV' python3 -m pytest -q      (languages/whence)
243 passed in 49.06s
$ python3 -m pytest -q                                      (harness)
148 passed in 4.67s
```

## Honest failures and costs
- **The suite hung, twice.** `fn loop(n) { loop(n + 1) }` — the canonical
  "runaway recursion is a miss" program in 3 tests and `deep.lang` — is an
  *infinite loop* under TCO. Predicted in the design notes, still cost two
  killed 300s runs before I switched to per-file `perl -e 'alarm'` runs.
  Rewritten as `1 + loop(n + 1)`. TCO trades a detectable failure (depth
  miss) for an undetectable one (divergence); `max_iter` is opt-in only.
- **Two wrong test expectations of mine again**: (a) `diverge(let a, let b)`
  reported the names → decided the *code* was wrong (naming steps exempt);
  (b) expected `-1` to be a literal — it is `-(literal 1)`, a shape change —
  decided the *test* was wrong. Both decisions written into docstrings/SPEC.
- **12 generated killer tests re-pinned** (fold node + `count` field changed
  the pinned renderings). These are behaviour pins, so re-pinning after a
  deliberate semantic change is the intended workflow, but nothing
  distinguishes "deliberate" from "regression" except my judgement.
- **Harness test coupled to Whence source text**: `test_find_killer_for_a_
  real_semantic_mutant` grepped for `xs.payload + [x]`, which no longer
  exists. Re-anchored on `provs, l + r)` in `binop`. Cross-repo string
  anchors are fragile; a marker comment would be sturdier.
- **Suite 15× slower** (3s → 49s): `meta.lang` 17s, `tco.lang` 12s,
  `deep.lang` 7s, all subprocess example runs with 100k-iteration loops.
  Interpretive overhead ≈35µs/frame is the real cost; lazy snapshots were
  the only cheap win available.
- **Merged-node addressing**: `at(x, "call even")` no longer matches a
  merged mutual-recursion node (detail is `even/odd`); `at(x, "call")` does.
- **Per-iteration retention in tail loops is still O(n)** (1.3KB/iter): the
  `arg` chain and an `if` node per iteration. That is the honest price of
  "nothing is forgotten"; `snip` remains the only pressure valve.
- Not done from the backlog: "Whence lexer for Whence syntax" (guest is
  still a different, smaller language); `diff` of rendered trees (structured
  `diverge` supersedes it); guest records.

## Key learnings
1. **Make retention cheap before rationing it.** Immutability + a tip-sharing
   buffer turns "keep every version" from O(n²) to O(n) with 40 lines and no
   semantic change. The retention-policy design would have added a mode and
   lost time travel; this lost nothing.
2. **TCO and provenance are compatible if wrappers can defer.** The trick is
   that a tail call is *returned* as data, and every node that would have
   wrapped the result instead attaches its pending record to that data. The
   merged `call ×N` node with the per-iteration `if`s as inputs is lossless
   because, under tail semantics, each iteration's `if` really did evaluate
   to the final value.
3. **Origins, not diffs.** `blame` (origin misses) and `diverge` (origin
   differences) are the same shape: walk the DAG, report nodes whose inputs
   were fine but whose result was not. "Consequences are not reported" is
   what makes the output one record instead of a hundred.
4. **Delete justifications that died.** The eager snapshot survived one
   round past the change that made it redundant and was 2/3 of runtime.
5. **Run new control-flow features under a wall-clock alarm the first
   time.** A hang is the failure mode of TCO, and `pytest` has no timeout
   by default.

## Files
- `languages/whence/whence/{values,interp,parser,ast_nodes}.py`, `run.py`
  (`--max-iter`), `SPEC.md` v0.3 (decisions 8–10).
- `languages/whence/bench/retention.py`; `tests/test_v03.py`;
  `examples/{tco,diverge}.lang` (new), `{deep,history,meta}.lang` (extended).
- `harness/tests/test_swe_killers.py` (re-anchored).
- Skills: `skills/generator-trampoline-evaluator/` (TCO step 9 + pitfalls),
  new `skills/shared-tip-immutable-lists/`.
