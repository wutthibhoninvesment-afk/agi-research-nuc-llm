# Round 002 — language(C): Whence, a provenance-first language

**Artifact:** `languages/whence/` — spec, lexer, parser, AST, tree-walking
evaluator, 19 builtins, 6 runnable examples, 105-test pytest suite (0.2s).
Run: `cd languages/whence && python3 run.py examples/blame.lang`.

## What Whence is
One idea taken seriously: **every value remembers where it came from.** A
runtime value is `(payload, prov)`; `prov` is an immutable DAG node
`(op, detail, line, inputs, show)` where `show` is a snapshot string of the
payload at creation. `why x` reifies the DAG as a first-class Explanation
value; `print(why x)` renders a tree; `str(why x)` makes it a string so
*programs can check their own derivations*:

```
check "why mentions rate": contains(str(why after3), "let rate")
```

## The five anti-mainstream design decisions (spec'd before coding)
1. **Provenance-carrying values** with `why` / `snip` (truncate history) /
   `note("label", x)` (human waypoints in the trail).
2. **No exceptions, no null.** Every runtime error is a `miss` value carrying
   deduped reason strings + provenance, propagating NaN-style through all ops.
   Even unbound names and calling-a-non-function are misses. `a rescue b`
   recovers — and the recovery's provenance keeps the miss it recovered from.
3. **No assignment, only binding.** Rebinding a name in the same block is a
   *parse error*. Iteration = recursion / map / filter / fold.
4. **Tests are statements.** `check "label": expr` runs inline; a failing check
   auto-prints the why-tree of its value; the interpreter exits 1 if any fail.
5. **Strict booleans.** `if 0 {…}` is a miss; `==` on functions is a miss;
   `miss == miss` is a miss (use `missed(x)`).

## The flagship behavior (examples/blame.lang)
A data row has qty `"3O"` (letter O). `num` misses, the miss flows through
`map`→`fold`, the total is a miss, and the value *itself* names the culprit:

```
print(total)      →  miss: num: cannot parse "3O" (line 4)
print(why total)  →  …tree containing…
      └─ miss ← call parse_row  (line 13)
         └─ miss ← note parsed beta  (line 4)
            └─ miss ← num num: cannot parse "3O"  (line 4)
               └─ "3O" ← literal  (line 9)
```
And `failing_check.lang`'s report renders the why-tree pointing at
`1.08 ← let tax_rate (line 4)` — the bug's exact line — with zero debugger use.

## Implementation choices that worked
- **Total evaluator.** `eval` never raises for user errors; everything becomes
  a miss. This deleted an entire class of plumbing — no try/except anywhere in
  eval except one `RecursionError` catch at the call boundary (which converts
  runaway recursion into a miss and lets the program continue).
- **Provenance on derivations only, pass-through on reads.** `xs[i]`, `r.f`,
  and variable refs return the element's Value unchanged. This keeps DAGs
  small and means access can't launder history. `let`/`call`/`arg`/`if` add
  named wrapper nodes — those names are what make rendered trees legible.
- **`if` provenance records the condition too** (`inputs=(branch, cond)`,
  detail `took then-branch`): "why is this value X" automatically includes
  "why did we take this branch". Cheap to build, high explanatory value.
- **Snapshot `show` strings in prov nodes** (truncated to 40 chars) mean
  rendering never touches live values → rendering a 10k-node chain is O(cap).
- **Render caps:** depth 10 + 200 nodes + `⟲ shown above` markers for shared
  DAG nodes. A fold over 10,000 elements renders as 18 lines in <1ms.
- **Parse-time discipline:** duplicate binding/param/field, if-without-else,
  block-not-ending-in-expression, chained comparisons — all parse errors with
  line:col. Runtime stays for data-dependent faults only.
- **Dispatch dict** built from `dir(Interpreter)` once; ~11 Python frames per
  language call. With `sys.setrecursionlimit(20000)` (run.py) max language
  recursion ≈ 1816 (measured by binary search).

## Numbers
- fold of 10,000-element range: 0.06s including provenance construction.
- `snip` inside the fold keeps the tree at 3 lines (pressure valve for memory:
  without it the DAG retains ~10k nodes — retained, not leaked).
- Suite: 105 tests, 0.21s (13 lexer / 17 parser / 56 interp / 11 values /
  8 subprocess end-to-end). Examples: 5 exit 0, `failing_check.lang` exits 1
  by design, garbage input exits 2 with line:col and no traceback.

## Honest failures / caveats
- **Bug caught in review, not tests:** first version of `join` checked
  element missness with `_is_miss(x.payload)` — `_is_miss` takes a Value, so
  it always returned False. Tests were written *after* the fix; a
  written-first test would have caught it. (Test now covers it.)
- **Recursion depth is coupled to the host.** ~11 Python frames per Whence
  call means default CPython limits give only ~90 language frames; run.py sets
  20000 → ~1800. Deeper needs a trampoline/explicit stack — real work,
  deferred. Embedders who skip run.py hit shallow limits silently (a `f(5000)`
  that works under run.py misses under an embedding that forgot the limit).
- **`str` is deliberately total** (renders misses as `"miss: …"` strings),
  which is an escape hatch around miss discipline — a program can convert a
  failure into a plain string and lose propagation. Kept for reporting;
  documented tension.
- **`show_payload` double-truncates** long strings (quote-level then
  string-level), so very long strings render with a lost closing quote in prov
  snapshots. Cosmetic; found while writing tests; left as-is this round.
- **No provenance-aware equality**: two structurally equal values with
  different histories are `==`. That's the right call (history is metadata),
  but it means `check` can pass while provenance is garbage; nothing verifies
  provenance *shape* except string-contains checks.

## Reusable technique captured
`skills/tiny-language-implementation/SKILL.md` — spec-first, errors-as-values,
parse-time discipline, 4-layer test pyramid (incl. a deliberately-failing
example asserting exit code 1), bool-before-int pitfall, render caps, frames-
per-call budgeting.

## Ideas for the next language round (round 4)
- Provenance-aware time travel: `at(x, "let a")` → the value a derivation had
  at a named node; would make `why` queryable, not just printable.
- Trampoline the evaluator (explicit stack) to decouple recursion from CPython.
- Effect budget: each fn declares max misses it may absorb (`rescue` quota).
- Provenance queries as data: expose the DAG as Whence records so programs can
  fold over their own history instead of `contains(str(why x), …)`.
- Whence-in-Whence: the evaluator is small enough that a subset self-hosting
  experiment (arith + let + if) is plausible in one round.
