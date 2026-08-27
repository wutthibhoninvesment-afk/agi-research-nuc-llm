# Whence — a provenance-first language (spec v0.15, rounds 009/011/014/020/024/026/030/108/110/122/128/132/146/164/168)

**One idea:** every value remembers where it came from. `why x` returns the
derivation tree of `x` as a first-class value. Failures are values too, so a
failed computation can be asked to explain itself. **v0.2:** history is
*data* — you can fold over it, travel back into it, and ask a failure for its
origins as records — and recursion depth is a language tunable, not a host
limit. **v0.3:** keeping *all* history is cheap (lists share storage, so
growing one in a loop retains every intermediate in O(n) memory), tail
calls run in one frame and leave one merged history node, and two
histories can be diffed to find the origin of a difference. **v0.4:** a
value *is* its history node (one object, not two), a source literal is one
node however often it runs, a tail loop's repeated decisions merge into one
node per run, call-free code runs as compiled closures (3–5× faster), and
`contrast` shows two histories side by side.

## Anti-mainstream design decisions
1. **Provenance-carrying values.** Every runtime value is `(payload, prov)`;
   `prov` is a DAG node `(op, detail, line, inputs, show, value)` recording
   how the value was made — and, since values are immutable, *the value
   itself* (one pointer). `why x` reifies it; `snip x` truncates history;
   `note("label", x)` inserts a human waypoint.
2. **No exceptions, no null.** Every runtime error (division by zero, unbound
   name, bad index, arity mismatch, parse failure in `num`, non-callable call,
   negative `sqrt`, recursion past `max_depth`, …) yields a `miss` value
   carrying *reason strings* plus provenance. `miss` propagates through every
   operator like NaN — but unlike NaN it can tell you *why*. Recover with
   `a rescue b` (the recovery's provenance keeps the miss it recovered from).
   Test with `missed(x)`, inspect with `reasons(x)`, locate with `blame(x)`.
3. **No assignment, only binding.** `let` binds once; rebinding a name in the
   same block is a **parse error** (shadowing in inner blocks is fine). All
   iteration is recursion / `map` / `filter` / `fold`.
4. **Tests are statements.** `check "label": expr` runs inline; a failing check
   automatically prints the why-tree of its value. The interpreter prints a
   check report and exits nonzero if any check failed.
5. **Strict booleans.** Only `true`/`false` are conditions. `if 0 {…}` is a
   miss, not "falsy". `==` on functions is a miss (identity lies, structure is
   undecidable). `miss == miss` is a miss (like NaN — use `missed`).
6. **History is queryable data, not a printout (v0.2).** `steps(x)` is the
   whole derivation as a list of step records; `at(x, "let a")` is the real
   value a named step had — live, computable, with its own history;
   `blame(x)` is the list of steps that *created* a failure (misses with no
   missing input). Programs check their own provenance structurally instead
   of grepping `str(why x)` (which is render-capped and can silently miss).
7. **Recursion is trampolined (v0.2).** Whence calls do not consume host
   stack; depth is capped by `max_depth` (default 20000; `run.py --max-depth
   N`) and exceeding it is an ordinary miss naming the function and depth.
   **v0.9:** the first few hundred levels of a recursion run by plain host
   recursion under a frame *budget* measured from the live recursion limit
   (direct mode); deeper levels fall back to the trampoline. Depth is still
   a language tunable, host stack depth is still bounded by construction —
   the budget only decides which levels pay for a generator.
8. **Tail calls merge, they do not forget (v0.3).** A call in tail position
   of a function body (the body's final expression, through `if` branches
   and nested blocks) re-enters the current frame: no depth, no host stack.
   Its provenance is ONE node `call f` with `count` = frames merged (rendered
   `call f ×N`; mutual recursion renders `call even/odd ×N`) whose inputs
   are the final result followed by the `if` decision of every iteration —
   so `why` still explains every branch taken. Tail loops are unbounded by
   default; `max_iter` (`run.py --max-iter N`) turns a too-long one into a
   miss. A call under `let`, `rescue`, an operator, an argument, `why`,
   `snip` or `check` is not a tail and still costs a frame.
9. **Full history is the default, and it is affordable (v0.3).** Lists are
   immutable views over a shared append-only buffer: `push(xs, x)` and
   `xs + ys` extend in place when `xs` is the buffer's tip and copy
   otherwise, so a list grown inside a fold keeps every intermediate list
   reachable from the history in O(n) total memory (v0.2: O(n²)). No
   retention policy, no `snip` required; the old values can never see the
   new elements because a view only reads its own prefix.
10. **Histories can be diffed (v0.3).** `diverge(a, b)` walks two histories
   in lockstep and returns the *origins* of their difference: steps whose
   inputs agree but whose result differs (kind `"value"`, e.g. the literal
   that changed between two runs) or where the computations have different
   shapes (kind `"step"`). Consequences downstream of an origin are not
   reported; naming steps (`let x` vs `let y`, `note`) never count as
   divergence. **v0.4:** `diverge([r0, r1, …])` compares every run with the
   first and tags each origin with `which` run diverged; `contrast(a, b)`
   renders the lockstep paths from the roots to each origin side by side.
11. **A value is its provenance node (v0.4).** There is no separate
   "value" object: the node that records how a value was made *is* the
   value (`v.prov` is `v`, `v.payload` is `v.value`). Retaining full
   history therefore costs no extra objects, and every step of a history
   is a real value for free. A source literal evaluates to the same node
   every time (`steps(x, "literal")` counts source literals, not
   evaluations); everything derived is a fresh node.
12. **Repeated decisions merge (v0.4).** Within a tail loop, consecutive
   identical branch decisions (same `if`, same branch) become ONE node
   `if took else-branch ×N` whose inputs are the N individual conditions —
   the same trick as `call f ×N`, and just as lossless. A tail loop that
   always takes the same branch leaves a flat history: `call f ×N` → its
   result, plus one merged `if` holding every condition. Decisions that
   alternate (or come from different `if`s) stay separate.
13. **Call-free code runs compiled (v0.4).** A subtree with no call in it
   cannot recurse into Whence code, so it is compiled once into Python
   closures and evaluated inline; only calls (and what contains them) run
   on the trampoline. Semantics are shared, not duplicated:
   `Interpreter(fast=False)` runs everything on the trampoline and must
   produce identical values and identical why-trees (the test suite checks
   a corpus both ways). Subtrees taller than 100 levels stay on the
   trampoline so host stack depth is never a function of program shape.

## Syntax (statements are newline-separated; `#` comments)
```
let x = 12                        fn add(a, b) { a + b }
check "adds": add(x, 3) == 15     print(why add(x, 3))
let v = num("3O") rescue 0        # rescue: use 0 if miss
let r = @{name: "Ada", age: 36}   # record; r.name, merge(r1, r2), keys(r)
let xs = [1, 2, 3]                # xs[0], len, map, filter, fold, push, range
let y = if x > 5 { "big" } else { "small" }
let f = fn(a) { a * 2 }           # anonymous fn; blocks end with an expression
check "long":                     # newline after ':' / an operator / and / or /
  x > 5 and                       #   rescue continues the line (v0.2)
  x < 20
```
Precedence (low→high): `rescue`, `or`, `and`, `not`, comparisons (non-chaining),
`+ -`, `* / %`, unary (`-`, `why`, `snip`, `miss <string>`), calls/index/field.
`if` requires `else`; blocks/fn bodies must end with an expression. Newlines are
statement separators except inside `( ) [ ] @{ }` and directly after a token
that cannot end a statement.

## Semantics notes
- Numbers are ints/floats; `/` is float division; `+` also concatenates strings
  and lists. Mixed-type arithmetic → miss.
- Element access (`xs[i]`, `r.f`) passes the element's provenance through
  unchanged: access does not launder history.
- `let` and `fn` wrap provenance in a `let <name>` node; calls wrap in a
  `call <name>` node (one per tail loop, see 8); `if` results record both
  the branch and the condition's provenance (so "why this result" includes
  "why this branch was taken"). `fold` (v0.3) adds a `fold <n> items` node
  whose inputs are the final accumulator and the list.
- Binop over misses merges reason lists (deduped, order kept). Builtins with
  a miss argument propagate it *before* looking at the argument — so a `fold`
  seeded with a miss is a miss regardless of the list.
- `print(x)` writes a rendering and *returns x* (pass-through — chainable).
- `str(why x)` renders the tree (depth ≤10, ≤200 nodes) as a string.

## Provenance as data (v0.2)
- **Step record**: `@{op, detail, line, show, depth, inputs, count, value}`
  where `value` is the historic value with that step as its provenance (so
  `why s.value` / `at(s.value, …)` keep working), `inputs` is a count and
  `count` (v0.3) is the number of frames a merged tail-call node stands for.
- `steps(x)` — all steps, root first, depth-first, each shared node once.
  Accepts a value or `why value`. Uncapped; `snip` is the pressure valve.
  `steps(x, name)` (v0.3) keeps only the steps whose label, op or detail
  equals `name` (same matching as `at`).
- `at(x, name)` — breadth-first from the root (most recent history first),
  the first step whose label (`"let a"`, `"note year 1"`, `"call grow"`),
  op (`"call"`) or detail (`"year 1"`) equals `name`. Miss if none.
- `blame(x)` — step records of every origin miss reachable from `x`
  (miss-valued nodes none of whose inputs is a miss). Empty list for a
  healthy value. `at(blame(x)[0].value, "literal")` reaches the bad input.
- `diverge(a, b)` (v0.3) — list of `@{kind, a, b}` records, `a`/`b` being
  step records of the paired steps; innermost origins first. Empty when the
  histories agree step for step. Accepts values or `why` values; works on
  misses (two failures diverge at the inputs that made them differ).
- **Cost:** every step keeps its value, so a history keeps every
  intermediate value alive — but intermediates *share* storage (decision 9):
  20k pushes in a fold retain everything in 28MB / 0.14s (v0.2: 568MB /
  6s). A tail loop retains ~770 bytes per iteration (v0.4; v0.3: ~1.3KB):
  the five nodes that are genuinely new facts about that iteration (`==`,
  `-`, `+`, `arg i`, `arg acc`) plus one pointer in the merged `if`. 1M
  iterations: 9s / 840MB (v0.3: 48s / 1.35GB). `snip` remains the
  pressure valve.
- **Speed (v0.4):** ~5–6µs per tail-loop iteration (v0.3: ~17µs) with the
  fast path; CPython's cyclic GC adds ~50% on long runs because it rescans
  the growing history, so `run.py` raises the gen-0 threshold for the
  duration of a run (`Interpreter(gc_relief=True)`; library default off).
- **Snapshots are lazy (v0.3):** a step's `show` string is rendered on first
  use, not at creation (eager snapshots were 2/3 of evaluation time).

- `contrast(a, b)` (v0.4) — a string: for each origin, the lockstep path
  from the two roots down to it, `a` left, `b` right, origin marked `▶`;
  `"no divergence"` when the histories agree.
- `at`/`steps` name matching (v0.4): a merged mutual-recursion node
  `call even/odd` also answers to `"call even"`, `"call odd"`, `"even"`.

## Records as data / self-hosting (v0.5, round 014)
- `get(r, name)` — dynamic field access with exactly `.field` semantics:
  same pass-through (no new node), same miss wordings for absent fields /
  non-records; a non-string `name` is its own miss. `get(r, "a")` and `r.a`
  are indistinguishable, node for node.
- `put(r, name, v)` — a new record with field `name` set to `v` (add or
  replace); the original is unchanged. Equivalent to `merge(r, @{name: v})`
  with a dynamic key; provenance node `put <name>` with inputs `(r, v)`.
  `v` may be a miss (records hold misses); only `r` and the key propagate.
- `find(fn, xs)` — the first element of `xs` for which `fn` returns `true`,
  passed through like `xs[i]` (access does not launder history). No match /
  empty list is a miss `find: no element matched`; a predicate miss or
  non-bool is a miss like `filter`'s.
- These exist because a metacircular evaluator needs an environment keyed
  by names it only knows at runtime. **Self-hosting round 4**
  (`examples/self_eval.lang`): a full Whence evaluator written in Whence —
  source → tokens → AST → value one level down. The host's mutable
  environments are modeled by store-passing (`eval(node, env, st) →
  @{v, st}`; a closure captures frame IDs, the store is an immutable record
  threaded through evaluation), which reproduces the host's call-time late
  binding exactly: `fn a() { b() }  fn b() { 1 }  a()` is 1, and calling
  `a()` *before* `b`'s definition has executed is an unbound-name miss.
  Guest values are host values, so host operator semantics (strictness,
  propagation, overflow) hold one level down, and a guest failure's blame
  trail reaches through both levels. Differentially tested against the host
  on a 50-program corpus (`tests/test_self_eval.py`); payloads must agree,
  miss *wordings* may differ (arity/callable messages), `==` on records
  containing closures compares structurally in the guest, and a guest
  record with a `__tag` field can spoof a callable (open-record leak).

## v0.6 (round 020)
- `has(r, name)` — presence, not readability: `true` when the field exists
  even if its *value* is a miss (`get` would pass that miss through),
  `false` only when the name is absent. The O(1) form of
  `contains(keys(r), name)`; a self-hosted evaluator asks it once per
  variable reference. Non-record / non-string-name are misses; argument
  misses propagate. Node `has <name>`, inputs `(r, name)`.
- `contrast([r0, r1, …])` — n-way: each run rendered against run 0, one
  block per *diverging* run (`run 2 vs run 0:` …); agreeing runs are
  skipped; `"no divergence"` when every run agrees or there are <2 runs.
- **Failing `==` checks auto-contrast.** A `check` that fails on a direct
  `==` records `contrast(left, right)` in its report; `run.py` prints it
  under `where the two sides diverge:`. Only `==`: a failing `!=` means
  the sides agree. A miss-valued comparison gets no contrast (the miss
  explanation already blames the origin).
- **String fast path:** `== != < <= > >=` and `+` on two strings skip the
  structural-equality machinery; node shapes are unchanged. `str % str`
  stays a miss (the host's `%` would silently *format*).
- **Calls got cheaper, invisibly:** a `Call` whose callee and arguments are
  all call-free compiles them once and skips its evaluator generator; a
  plain (non-higher-order) builtin call runs with no trampoline frame at
  all. `fast=False` still forces the generator path — the two paths are
  differentially tested.
- **Slimmer nodes:** `count` is a class attribute (1) on ordinary nodes and
  a real slot only on merged `call ×N` / `if ×N` nodes (`MergedProv`); a
  single input is stored unboxed (no 1-element tuple) and re-wrapped on
  read. Tail-loop retention 772 → 636 B/iteration, lossless.

## v0.7 (round 024)
- **Builtin calls compile (F1):** a direct call to a builtin name that is
  never shadowed anywhere in the program — and whose builtin does not
  re-enter guest code (`map`/`filter`/`fold`/`find` are excluded) —
  compiles inline, so the *enclosing* expression compiles too. The
  compiled call still resolves the name at runtime and verifies it is that
  exact builtin; any shadowing (including one introduced by a later
  `exec_stmt` in embedding code) falls back to full dynamic call
  semantics. Node shapes are unchanged.
- **Frameless closure calls (F2):** a non-tail call to a function whose
  whole body compiled (which F1 makes common: bodies that only call plain
  builtins) runs without a trampoline frame — same `call` node, same
  `arg` nodes, same arity/depth misses, same `peak_depth`.
- **Deferred `if` decisions are never dropped:** in v0.4–v0.6, a
  tail-position `if` whose taken branch tail-called a builtin (or a
  non-callable, or a miss) lost its `if` node when the tail loop ended
  after a single frame. The decision is now re-wrapped innermost-first, so
  the history reads `call → if → result` exactly like the compiled path.
  (Found by the v0.7 fast/slow differential; the whole 430-test suite had
  never pinned the lossy shape.)

## v0.8 (round 026)
- **Else-if chains walk inline (F3):** when an `if`'s taken branch is
  itself an `if` whose condition compiled fast — the shape of every
  interpreter's kind dispatch — the driver walks the whole chain in one
  step instead of pushing one generator per level. The walked decisions
  are wrapped innermost-out (or handed to the tail loop innermost-first),
  so histories are node-for-node identical to the nested path. A single
  `if` (no chain) takes the same straight-line path as before.
- **Statements run inline in blocks (F3b):** `let`/`check`/`fn` statements
  inside a block no longer push a per-statement generator; the block's own
  generator executes them directly. Same `let` nodes, same check records.

## v0.9 (round 030)
- **Direct mode: calls run by host recursion under a frame budget.**
  v0.4–v0.8 compiled only *call-free* subtrees; every subtree with a call
  in it — and every non-tail closure call — went through the generator
  trampoline (three generators and ~8 `send`s per `fib` call). Now every
  subtree compiles (`compile_direct`, cached in `node.direct` next to
  `node.fast`), calls included: a call node evaluates its callee and
  arguments and calls `_call_direct`, which is `_call_gen` without the
  generator — same arity / depth / tail-loop-too-long misses byte for
  byte, same `arg` / `call` / merged `call f ×N` / `if ×N` nodes (the
  bookkeeping is shared code), same `depth` / `peak_depth` / `tail_calls`.
  Tail calls still hand a pending `_TailCall` back to the enclosing loop,
  so tail loops stay frameless and merge exactly as before.
- **The budget.** Each top-level statement measures the host headroom:
  `sys.getrecursionlimit() − frames already on the stack − 350` (reserve
  for transient fast-closure recursion, one trampoline fallback and
  rendering). Every direct entry charges the frames it can use before the
  next `_call_direct`: `node.cdepth`, the number of direct-closure frames
  on the deepest path from the node to a call (a one-expression block is
  unwrapped and charges nothing), plus one for `_call_direct` itself. The
  charge is exact — `count`-shaped recursion measures 4.00 host frames per
  guest level and is charged 4. A call whose body does not fit (or is
  taller than `FAST_MAX_DEPTH`) runs on the trampoline through a nested
  driver, and inside it nothing goes direct until the budget is back, so
  host depth is bounded whatever the program does: a 15000-deep `count`
  under the default limit of 1000 runs direct for ~150 levels and
  trampolined for the rest (`direct_fallbacks` counts these); with the
  budget faked to infinity the same program raises RecursionError (a test
  proves the guard is load-bearing). Under `sys.setrecursionlimit(200)`
  the budget is negative and direct mode is simply dormant. Mutual
  recursion switching to a taller body mid tail loop re-charges the
  difference or runs that body on the trampoline. `run.py` raises the
  limit to 6000 (the CLI owns the main thread's 8 MB stack; plain closures
  recurse 30000 deep here); the library never touches the limit.
- **Three-way differential.** `Interpreter(direct=False)` is the v0.8
  evaluator (fast path on, every call on the trampoline); `fast=False`
  implies `direct=False`. The suite pins `render_why` byte-equality, output,
  check records and depth counters across direct / fast-only / slow on a
  corpus of call shapes, and the fuzz oracles gained a `direct` leg.
- **Bug found by the third leg (fast=False vs the rest, pre-existing since
  v0.7):** a multi-frame tail loop whose *final* iteration tail-called a
  builtin (`push(acc, eof)` in self_host.lang's lexer) merged that
  iteration's `if` into the loop's `if ×N` runs on the trampoline but
  wrapped the result with it on the compiled path (F1 inlines the builtin
  call) — one extra `if ×1` input in `fast=False`. v0.7 had reconciled the
  single-frame case only. Decided shape, every mode: a tail call that
  resolves to a builtin / non-callable / miss ends the loop as an ordinary
  call and the decisions of that final iteration wrap its result.
- **Counters:** `direct_hits` (direct entries + direct closure calls),
  `direct_fallbacks` (calls the budget sent to the trampoline),
  `host_budget()` (frames still available; ≤0 = dormant). `fast_hits`
  counts driver-level entries into any compiled closure.
- **Determinism:** direct closures are cached on shared AST nodes, so a
  call node resolves the interpreter acting NOW from the env chain (call
  envs and globals carry it) — and `check` statements inside compiled
  blocks now record on that interpreter too (a latent v0.4 hole).
- **Numbers (idle machine, fresh process, min of 3):** fib(20) 5.83 →
  3.72 µs/call (1.58×), meta.lang 5.16 → 4.17 s (−19 %), tail loop 6.66
  → 5.64 µs/iter, self_eval.lang −13 % (281 budget fallbacks: the guest's
  recursion outruns a 646-frame budget), generator sends in meta.lang
  1.10 M → 807, retention 634 B/iter unchanged.

## v0.10 (round 108)
- **The value-model floor.** The number of provenance nodes a program
  builds is fixed by the semantics (one per operation, argument, binding,
  decision, call: 2.77 M for one meta.lang run), so v0.10 removes the
  Python frames AROUND each node instead of the nodes:
  - `Prov.__init__` is a raw slot store. Its `ins` argument is stored as
    given — a tuple of input nodes, or ONE node unboxed (the v0.6 layout;
    a 1-tuple is accepted and simply not unboxed). Normalisation (lists,
    unboxing) lives in `derived` / `leaf` / `mk_miss` / `merge_miss`; the
    hot paths build `Prov(...)` directly. `MergedProv.__init__` is one
    frame, not a delegation.
  - Every binary operator compiles to its own closure with the numeric
    case inline (exact type test — `bool` excluded — the native operator,
    one node); `==`, `!=`, `+` and the orderings take the string case
    inline too. Every other case (misses, lists, mixed kinds, zero
    divisors, int-meets-float overflow) is decided by `binop`, so a miss
    has exactly one wording wherever it is produced.
  - Field access and list indexing compile to closures that return the
    pass-through element directly (present field of a record; in-range
    integer index of a list); every other case goes to the shared helper.
  - The `if` guard is `c is True` / `c is False`; only a non-boolean pays
    the `_if_bad` frame that builds the miss.
  - A run of ONE merged decision in a tail loop is a plain `if` node whose
    single input is the condition — the shape `MergedProv(count=1)` had,
    minus the second class and two lists. Runs of ≥ 2 decisions remain
    `MergedProv`. 99.99 % of the runs in meta.lang and self_host.lang are
    one decision long (a loop through an else-if chain alternates between
    `if` nodes, and only CONSECUTIVE identical decisions merge). Nothing
    renders differently: `×N` appears for `count > 1` only.
  - `Env(parent, interp)` takes the acting interpreter positionally.
- **Bug found by the reference differential (pre-existing since v0.9):
  comprehensions are frames.** `cdepth` charged one host frame per
  direct closure, but the list literal closure, the call-argument
  evaluation and the builtin-argument evaluation used list
  comprehensions — a real frame each in CPython < 3.12 — so every level
  of `fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }` used 5
  frames and was charged 4. Under the default limit (~160 direct levels)
  the 350-frame reserve absorbed the difference; at the CLI's limit of
  6000 (~1400 levels) `run.py` died with a RecursionError traceback on
  `nest(1500)` — the fuzzer's own deep-nesting template, never run at
  that limit by the oracle campaigns. v0.10 evaluates arguments and list
  items with list displays (one and two arguments) or explicit loops:
  no comprehension on the direct path, so the charge is exact by
  construction (measured 4.00 frames per level for the list, argument,
  three-argument and record-in-list shapes; pinned). `nest(3000)` at
  6000 now runs direct for ~1400 levels and trampolines the rest.
- **Reference differential.** `bench/ref_diff.py` runs every example under
  the working tree and under a reference copy of the package (git HEAD by
  default, extracted with `git show`) in every mode and compares output,
  check records, every top-level binding's `render_why`, and (with
  `--counters`) the evaluation counters; `--fuzz SEED -n N` does the
  same over the harness fuzzer's random programs at the CLI's recursion
  limit, reporting an exception under the new tree as a finding and one
  under the reference as a note. v0.9 → v0.10: 39/39 (example, mode)
  pairs identical, counters included; 769 random programs × 3 modes, 0
  differing (the reference raised on 5 direct-mode pairs, the tree on
  none). The three-way differential now also covers meta.lang and
  self_eval.lang (suite +16 s).
- **Numbers (idle machine, fresh process, min of 3, paired against v0.9
  on the same day):** meta.lang 3.35 → 2.49 s (−25.5 %; `direct=False`
  4.03 → 3.30 s, −18 %), fib(20) 4.18 → 2.99 µs/call (1.40×; trampoline
  mode 9.61 → 8.04), tail loop 4.74 → 3.96 µs/iter (−16.5 %),
  self_eval.lang −6.7 %, deep.lang −14 %, retention 634 B/iter unchanged;
  Python calls per meta.lang run 30.5 M → 17.5 M (−43 %).

## v0.11 (round 110)
- **The ceiling, measured before building.** Three experiments priced the
  frame-removal strategy that v0.4–v0.10 followed, before any of them was
  built: (1) fusing a `NameRef` or literal operand into the closure above
  it (no `f_name` / constant frame) saves 10–20 ns per operand — the env
  walk is the cost, the call is not — so the 2.28 M name and 0.78 M
  constant frames of a meta.lang run are worth 2–3 %; (2) a
  hand-transpiled `fib` body (all 15 closure frames of the body folded
  into ONE Python function, why-tree byte-identical) through the real
  `_call_direct` is **1.09×**; (3) `_call_direct` with every piece of
  bookkeeping ablated (no depth / peak / counters / try, cached entry,
  unrolled binding) is **1.14×**. `__slots__` on the interpreter (0.3 %
  of a call), static scope-hop hints (0.33 failed probes per lookup in
  meta.lang → ≤ 1.2 %) and `Env` as a dict subclass (walk slower,
  creation faster, net 0) were measured and declined. What remains is
  the value model: one six-slot node per operation, an `Env` and a dict
  per call, and the call bookkeeping. A transpiler would buy ≤ 10 %; the
  evaluator is within ~15 % of what a CPython closure compiler can do for
  this semantics.
- **What was built: the last of the call path.** A function body's
  direct-call entry `(evaluator, frames charged)` is cached on the body
  node (`Node.entry`, `_body_entry`): the fast closure at cost 1, the
  direct closure at `cdepth` + 1, or `False` when the body is too tall to
  compile (then every call of it falls back to the trampoline — as
  before, one lookup instead of four). One- and two-parameter bindings
  are unrolled (no `zip` iterator); `depth` and the frame budget are read
  once and stored back rather than read-modify-written. Trampoline-only
  interpreters never write the entry. Same misses, same nodes, same
  counters — pinned three-way over 0–4 parameter widths, misses as
  arguments, arity misses at every stage of a tail loop, and loops that
  switch between bodies of different widths and heights.
- **The frame-charge oracle** (`harness/swe/oracles.py::oracle_frames`,
  the sixth oracle of the fuzz campaign). Round 108's bug — a host frame
  per guest level that `cdepth` did not know about — was invisible at the
  default recursion limit because the 350-frame reserve absorbed ~160
  uncounted levels; it surfaced only at the CLI's limit. The oracle runs
  a program under `sys.setprofile`, tracking the host frames actually on
  the stack above `exec_stmt` minus the frames direct mode has charged
  against its budget; the maximum of that excess over the run is the
  transient the reserve exists for. It is bounded by construction
  (fast-closure recursion ≤ `FAST_MAX_DEPTH` levels, one nested drive and
  its helpers): measured over 264 fuzz programs and the examples, the
  examples reach ≤ 19 frames, most programs 5–20, the fuzzer's
  `1 + 1 + …` chains 98 and nested list literals 59 — all at guest depth
  0. An uncharged frame per level reaches 161 within 160 levels at the
  default limit (injected, pinned) and ~1400 at 6000, so the slack of
  140 (`FRAME_SLACK`) separates the two; `swe.oracles --limit` and
  `swe.fuzz --limit` run the campaigns at the CLI's limit.
- **`bench/reserve_probe.py`** finds, per program, the smallest
  `HOST_RESERVE` that still completes without a RecursionError at a given
  limit (binary search, fresh process per probe) over ten deep templates,
  the examples and fuzz programs — the reserve's true requirement,
  measured in the limit's own units (which count C-level recursion
  entries the profile hook does not). Measured: deep recursions with
  short bodies need 0–5 (the charge is exact; recursion through `fold`
  even overcharges and falls back early), a 95-term `+` chain in the
  base case of a non-tail recursion 93–94 (reached through a call, a
  list literal or a record field alike), 55-deep nesting 57 (the parser
  caps nesting at 60), a 39-level else-if chain 41, every example and
  fuzz program ≤ 5. The bound by construction is `FAST_MAX_DEPTH` + a
  nested drive ≈ 110, so **`HOST_RESERVE` is 250** (was 350, a guess):
  2.3× the bound, and 100 more frames of direct budget (+17 % at the
  default limit). `bench/minof.py` is the min-of-N fresh-process bench
  driver.
- **Numbers (idle, fresh process, min of 3, paired the same day, limit
  6000):** fib(20) 3.18 → 2.81 µs/call (−11.6 %; trampoline mode 9.50 →
  9.19), meta.lang 2.325 → 2.275 s (−2.2 %; `direct=False` 3.309 → 3.271),
  tail loop 3.81 → 3.71 µs/iter (−2.6 %), deep.lang 1.095 → 1.066 s,
  self_eval.lang 0.421 → 0.424 s (nothing: builtin-call bound), retention
  634 B/iter unchanged. Reference differential v0.9 → v0.11: 39/39
  (example, mode) pairs identical with counters.

## v0.12 (round 122) — structural types
- **A type annotation is erased at parse time, not evaluated at runtime.**
  `fn f(a: num, b: Point) { … }` desugars, in the parser, to one leading
  `let a = typed(a, "num", "parameter 'a' of f")` per annotated parameter,
  prepended to the body's statement list before it is returned — an
  ordinary `Let`/`Call`/`Str` AST, exactly what a Whence programmer could
  have written by hand. No new AST node, no interpreter change, and an
  untyped function's body is byte-identical to v0.11 (the whole existing
  corpus is the regression gate: 654 tests + `run.py` on every example,
  unchanged). A mismatch is an ordinary `miss` (decision 2): it
  propagates through the rest of the body via the SAME operator/builtin
  propagation every other bad input already uses, `rescue` recovers it,
  `blame` finds it. This is the whole feature's design: no new control
  flow, no new failure mode, no exception to the "errors are values"
  discipline — a type is just another thing a value can fail to be.
- **Tail position is unaffected.** The guard only PREPENDS statements to
  the body; `mark_tails` is called once, after prepending, and only ever
  looks at the block's LAST statement — the same node it would have
  found without any annotation. A recursive tail call through a typed
  parameter still merges into one frame (three-way differential +
  `peak_depth` pin in `tests/test_v12.py`). This was the one alternative
  design ruled out: wrapping the body in `if <types ok> {…} else {miss}`
  would have buried a genuine tail call under an `if`'s `then` branch —
  still tail-safe by `mark_tails`'s own rule (`if` branches stay
  candidates) — but a `-> Type` RETURN annotation has no such safe
  shape (checking a value AFTER the body runs inherently needs the
  result back, which costs tail position, decision 8) — so v0.12 ships
  parameter types only; a return annotation is future work, not started.
- **Primitive tags:** `num str bool list record fn any` — `any` always
  matches (even so, a miss argument still propagates first: "any" is not
  "swallow errors", decision 2). `shapeof(x)` returns the tag Whence
  values report their true payload as, including `"miss"` — the same
  classification `typed` uses, exposed directly (and, in a self-hosted
  evaluator, a replacement for the hand-rolled `is_num`/`is_record`
  helpers `self_eval.lang` has needed since round 14).
- **`shape Name = @{field: type, …}` is sugar for `let Name = @{__shape:
  "Name", field: <spec>, …}`** — an ordinary record, bound by an
  ordinary `let`, so it inherits the parser's ALREADY-EXISTING duplicate-
  name rule for free (a `shape` reaches `stmt_list`'s bound-name check as
  an `A.Let`, indistinguishable from a hand-written one) and is itself a
  first-class value (`Point.__shape`, `matches(r, Point)`). A field's
  type is either a primitive tag (a string literal spec) or a
  PREVIOUSLY-DECLARED shape name (a `NameRef` to its own bound record —
  real value reuse, not a copy, so `shape Line = @{a: Point, b: Point}`
  shares the exact `Point` record both `a` and `b` are checked against).
  Shapes can only reference earlier shapes (the parser resolves a
  signature's spec immediately, single-pass, no forward refs — an
  `unknown type` parse error otherwise), so nested `matches` recursion
  is bounded by declaration order and cannot cycle.
- **Structural, not nominal: width subtyping.** A record matches a
  `shape` when every declared field is present with a non-miss value of
  the right (recursively checked) type; EXTRA fields are ignored. A
  record built entirely by hand, with no relation to the shape ever
  declared, matches it exactly as one built from it — real duck typing,
  by design, not the round-18 guest `__tag`-spoofing leak (that was a
  closure impersonating a callable via a magic field one level down in
  `self_eval.lang`; here a record honestly IS what its fields say it is,
  so matching structurally is simply correct, not a hole).
- **`typed(value, spec, label)`** — the builtin the guard calls: pass
  through the value UNCHANGED (no new provenance node, like `get`/
  index) when it matches; propagate an already-miss `value`/`spec`/
  `label` (decision 2's "misses propagate before inspection", same
  convention as `has`/`put`); otherwise a fresh miss `"<label> expected
  <spec-name>, got <shapeof value>"` whose `inputs` is `(value,)` — an
  ORIGIN miss (no input of its own is a miss), so `blame(result)` finds
  it directly and names the call that rejected the value. `matches(x,
  spec)` is the same check as a total predicate (never itself a miss,
  even on a miss `x`, like `missed`) for programs that want to branch on
  shape instead of failing on it.
- **A parameter's own guard can be shadowed, and it is documented, not
  hidden:** `fn f(a: num) { let a = a  a }` still sees the checked value
  (the user's `let a = a` reads the ALREADY-guarded `a`, since the guard
  runs first and both bindings live in the same call env); `fn f(a: num)
  { let a = 5  a }` discards the check for `a` specifically because that
  rebind never reads the original `a` at all — the same as it would
  discard any other prior binding it does not reference. No special-
  casing needed or added; this is exactly what a leading `let` already
  means.
- **`fn` is parseable as a type tag** despite being a keyword everywhere
  else (`fn apply(f: fn, x: num) { f(x) }`): the annotation parser
  accepts the `fn` KEYWORD token as well as a NAME. **`shape` is a
  CONTEXTUAL keyword, not reserved:** only the exact prefix `NAME NAME
  "="` at the start of a statement (mirroring how `fn NAME` already
  disambiguates a named def from an anonymous `fn(...)` literal)
  triggers shape parsing; no other legal Whence statement starts with
  two bare names, so a program that binds something actually called
  `shape` is unaffected — no lexer change, no reservation.

## v0.13 (round 128/132) — return type annotations
- **`fn f(params) -> Type { body }` checks the function's RETURN value
  against `Type`, using the exact same contract `typed()`/a parameter
  guard already uses** — a primitive tag or a previously-declared `shape`,
  structural width subtyping, `any` always matches. Unlike a v0.12
  parameter guard (sugar: one leading `let` statement, re-evaluated every
  call), a return check cannot be sugar the same way — checking a value
  AFTER the body runs needs the settled result back, which costs tail
  position if done as a body-wrapping `if`. So a return type is NOT an
  AST rewrite: the parser stores the spec expression on `FnDef`/`FnExpr`
  (`ret_type`, an `A.Str` or `A.NameRef`, same shape a param spec is),
  resolved to a runtime `(spec, label)` pair ONCE per `Closure` at
  creation time (`_closure_ret`/`_mk_closure` — a choke point for every
  FnDef/FnExpr construction site: fast, direct, and all three generator-
  mode sites), and checked at the ONE point every call path already
  settles to a final `result` Prov before wrapping it in a `call` node
  (`_check_ret`, called from `_call_gen`'s merged-tail-chain exit,
  `_call_direct`, and the call-free-body fast path `_call_no_calls` —
  THREE sites; the third was missing entirely in an early draft and was
  the round-128 bug the three-way differential caught, see below).
- **An untyped function pays for exactly one identity check per call**
  (`ret_spec is None`) — no new provenance node, no guest-visible frame,
  same "no new control flow" discipline v0.12 used. A mismatch is an
  ordinary origin miss (decision 2), same wording/op/single-input shape
  `typed()` itself produces (`"typed"` op, `detail` = the label), so
  `blame`/`rescue` treat a bad return exactly like a bad parameter. A
  `result` that is ALREADY a miss is never re-wrapped — the function's
  own failure is not painted over with a second "wrong return type" gloss.
- **Tail position is exactly as `mark_tails` already computes it, with one
  subtlety: the check runs against the ORIGINALLY CALLED closure's own
  `ret_spec`, captured before a tail loop may reassign which closure `p`
  points to.** `a` tail-calling a differently-typed (or untyped) `b` must
  still check the merged chain's settled result against `a`'s own
  contract, exactly once, not once per bounce and not against whatever
  closure the chain happens to end in
  (`tests/test_v13.py::test_mutual_tail_call_checks_against_the_caller_not_the_callee`).
  A typed tail-recursive function costs nothing extra per bounce: the
  spec is resolved once at closure creation, and the check itself runs
  once, at exit, using `peak_depth 1` regardless of iteration count
  (20000-deep `count_down` tail loop: one check, `peak_depth == 1`).
- **A real crash bug, found by round-128's own exploratory testing (not
  the fuzzer, which does not generate type annotations yet):** a `->
  Shape` naming a shape declared inside ANOTHER function's body parses
  (the parser's `self.shapes` set is not scope-aware — a pre-existing
  v0.12 gap shared by parameter types), but is never bound in the `env`
  chain `_closure_ret` walks at closure-creation time. The naive
  `env.get(name).payload` raised `AttributeError` on the `None` a missing
  lookup returns — a real crash, violating the "never raises" discipline
  every other Whence error path upholds by construction. Parameter types
  don't have this crash because a param guard's spec is an ordinary
  `A.NameRef`, walked by the everyday evaluator, which already turns a
  missing name into a `miss` instead of raising; the return-type path had
  no such protection because it resolves the spec directly in Python, not
  through a Whence expression. Fixed with a `_UnboundRetType` sentinel:
  `_check_ret` turns it into an ordinary `"not in scope"` miss, deterministic
  across repeated calls, and it never leaks to Whence code as a Python
  exception.
- **Three-way differential (fast / direct / trampoline) is the gate**,
  same as every call-path change since v0.9: byte-identical why-trees and
  checks across all three modes for a passing return, a mismatched
  return, a shape return, typed tail recursion, a mutual tail call, non-
  tail recursion (every frame checked independently, no double-wrapping),
  and the out-of-scope-shape crash case (`tests/test_v13.py`, 8
  `assert_three_way` cases + 39 unit/parser/interpreter cases, 47 total).
- **Not done / declined:** the fuzzer's program grammar does not generate
  `-> Type` annotations yet (same gap v0.12 left for parameter types) —
  standing backlog, not blocking (both features are call-boundary checks
  with an identical, already-fuzzed-by-proxy failure shape: a `miss`
  flowing through ordinary propagation). No new example beyond extending
  `examples/shapes.lang` with a return-typed `midpoint`/`broken_midpoint`
  pair (4 new checks, 12 → 16) — a dedicated flagship example was judged
  unnecessary since the feature composes directly with v0.12's existing
  one and the design point (return checks are call-boundary checks like
  parameter checks) is best shown as an addition, not a separate story.

## v0.14 (round 146) — effect system
- **The curriculum's remaining "advanced feature" slot (after v0.12
  structural types and v0.13 return types) is an effect system, not
  AI-native primitives** — decided this round because the language
  already has an observable effect to make interesting (`print`, which
  writes to the host) and because a minimal design falls directly out of
  the v0.12/v0.13 precedent, unlike AI-native primitives, which have no
  settled scope yet. `fn f(params) effects [tag, ...] -> Type { body }` —
  an optional clause after the parameter list, fixed order (effects
  before `-> Type`; the other order is an ordinary out-of-order syntax
  error, "expected '{'"). Anonymous `fn(...) effects [...] { ... }` takes
  the same clause.
- **The whole check is resolved at PARSE time, with zero interpreter
  change** — no new AST field, no `Closure` slot, no runtime cost,
  unlike `: Type`/`-> Type` (v0.12/v0.13), which both check a RUNTIME
  value and therefore have to live in the interpreter. Whether a
  function's own body directly names an effectful builtin is a static
  property of the source text, decidable before the program ever runs —
  the same category of fact that already makes rebinding and "block must
  end in an expression" PARSE errors rather than misses. `_EFFECTFUL_
  BUILTINS = {"print": "io"}` (`parser.py`) is the one place a future
  effectful builtin (randomness, a clock, real I/O) would register its
  tag; nothing else would need to change.
- **Mechanism:** the parser keeps a stack of "the nearest enclosing fn's
  declared effect set" while parsing (`self.effects_stack`, pushed on
  entering any `fn`'s body — `None` for no clause, a `frozenset` for a
  declared one, possibly empty) and checks it at every direct call whose
  callee is literally a builtin name in the effect table
  (`Parser._check_effect_call`, called from `postfix()`'s call-parsing
  site). No clause anywhere in scope (including the module top level,
  which has no enclosing fn at all) means unrestricted — **every program
  written before this feature existed parses identically**, confirmed by
  the full pre-existing suite (779/779) and every `examples/*.lang` file
  running unchanged after the change landed.
- **`effects []` is the interesting case: "this function's own body may
  not directly call an effectful builtin."** Violating it is a
  `ParseError` naming the builtin, the required tag, and the declared
  set (`'print' requires effect 'io', not permitted by the enclosing
  function's 'effects [] (no effects declared)'`). `effects [io]` (or
  any set containing the tag) grants it; an unrelated tag like `effects
  [network]` does NOT grant `"io"` — the check is per-tag, not merely
  "was a clause present" (`test_effects_unrelated_tag_still_blocks_
  print`).
- **Deliberately SHALLOW, not merely incomplete — the same scoping
  discipline v0.13's return-type check already established (one settle
  point, not full call-graph composition):**
  - A declaration vouches ONLY for calls made directly, textually, in
    that function's own body. A nested `fn` defined inside a restricted
    body is a SEPARATE closure with its own (absent, hence unrestricted)
    declaration and may print freely, even lexically inside an `effects
    []` function (`test_nested_undeclared_fn_escapes_outer_purity`,
    `examples/effects.lang`'s `strict_sum`). Calling a DIFFERENT,
    unrestricted function that itself prints is likewise untouched by
    the caller's declaration.
  - Only a literal `name(...)` callee is inspected. `let p = print` then
    `p(1)` is invisible to the check inside an `effects []` function —
    the callee at that call site is the `NameRef` `p`, not `print`
    (`test_indirect_call_via_variable_is_not_checked`).
  - Both gaps are real, tested, and documented rather than hidden; a
    call-graph-aware (transitive) effect system that closes them is
    future work, not this round's scope (see research-state.md's
    language backlog).
- **Zero interpreter change means the three-way differential (fast /
  direct / trampoline) already agrees by construction** — pinned
  explicitly anyway with two `assert_three_way` cases
  (`tests/test_v14.py`), plus the full pre-existing fuzz/oracle/guest/
  ref_diff standing checks (round 146: two fresh fuzz seeds, two oracle
  seeds — one at `--limit 6000` — two guest seeds, `reserve_probe
  --examples -n 30`, `ref_diff` over every example) all ran clean or
  found nothing attributable to this change (`ref_diff` correctly
  reports `examples/effects.lang` as `NEWSYNTAX` against the pre-round
  reference tree, not a diff).
- **New example `examples/effects.lang`** (4 checks): a declared-pure
  `total`, an `effects [io]` `report` that legitimately prints, `effects
  [io] -> num` composing with a return type, and the honest
  `strict_sum` escape-hatch demonstration. No example demonstrates the
  REJECTED case (a `ParseError` aborts the whole file before any `check`
  can run, so a "this should fail" example can't coexist with passing
  checks in one file, unlike a v0.12/v0.13 type mismatch, which is a
  runtime `miss` that keeps the rest of the program running) — the
  rejection path is covered by `tests/test_v14.py` and
  `test_examples.py::test_effects_violation_exits_2` instead.

### v0.14 guest parity (round 164)
- **`examples/self_eval.lang`/`self_host.lang`'s shared parser section now
  recognizes and SKIPS `effects [name, ...]`** (`parse_effects_clause`/
  `skip_effect_names`, inserted between the param list and the optional
  `-> Type`, same fixed order as the host) — closes the PARSING half of
  the guest-parity gap round 162 flagged when it taught the fuzzer to
  generate the clause and had to no-op it for `GuestGen`
  (`harness/swe/guest.py`): before this round the guest choked with
  "unexpected token 'effects'" on any v0.14 program using the feature.
- **The guest does not ENFORCE the declaration.** The host's
  `_check_effect_call` is a parse-time check consulted from
  `self.effects_stack` at every call site the recursive descent visits;
  reproducing it on the guest would mean threading an extra "current
  effects scope" argument through the entire expression grammar (down to
  `parse_postfix_rest`, where a call is actually built) — a materially
  bigger change than return-type erasure was, which only ever touched the
  single point where a function's own param list meets its own body.
  Left as an explicit, documented divergence rather than built partway.
- **Verified safe for the fuzzer without full enforcement**: re-enabled
  `GuestGen.maybe_effects` to inherit the real generator (no longer a
  no-op) after confirming `harness/swe/guest.py`'s `BANNED` line-filter
  already strips every line containing `print` — the ONE effectful
  builtin that exists — from every program this generator emits, on
  both sides of the comparison, regardless of what any `effects [...]`
  clause says. A generated declaration is therefore always vacuously
  satisfied through this generator; there is no live code path by which
  the host's parse-time rejection and the guest's non-enforcement could
  disagree. 300-sample check: 70/300 generated programs now carry an
  `effects` clause (was 0/300 under the round-162 no-op); a 150-program
  guest-differential campaign (seed 900) came back 0 findings.
- **New finding, orthogonal to effects itself**: running
  `examples/effects.lang`'s real, unmodified source through `run_src`
  still reports `parse_error: true` — NOT because of the effects clause
  (isolated single-statement checks of every one of the file's four
  functions, including the `effects [io] -> num` composition and the
  nested nested-fn nested-`print` case, all parse and evaluate correctly
  on the guest), but because of its one stylistically multi-line
  statement, `check "...":\n  expr` (label and expression on separate
  lines). The guest lexer's newline-suppression is deliberately simpler
  than the host's by design (its own header comment: "Newlines are
  suppressed while the top of the stack is `(` `[` or `@{` — NOT inside
  plain `{` blocks") — it has no equivalent of `whence/lexer.py`'s
  `CONTINUES` set (a newline right after `:`/a binary operator/`=`/etc.
  is a continuation on the host, an ordinary statement separator on the
  guest). This was unreachable/untested before this round: `effects.lang`
  is the first real example file with a multi-line `check` that the guest
  has ever had a chance to attempt (every corpus program in
  `tests/test_self_eval.py::CORPUS` is single-line by convention).
  Confirmed by reflowing just that one `check` onto a single line: the
  file then parses and evaluates identically on both sides. Not fixed
  this round — it is a lexer-level design choice, not a two-line parser
  patch, and touches every multi-line-continuation position the host
  supports, not just `check`. Tracked as fresh backlog (see
  research-state.md's language(C) list) rather than rushed behind this
  round's actual deliverable.

## v0.15 (round 168) — AI-native primitives: `guess`/confidence
- **The curriculum's last open "advanced feature" slot** (structural types
  v0.12, return types v0.13, effects v0.14 all shipped; round 146 itself
  flagged AI-native primitives as unscoped). Scope decided this round:
  model **uncertainty** — an LLM's defining property, "an answer, but not
  a guaranteed one" — as a first-class value, symmetric to how `miss`
  already models **absence**. Where a `miss` is "no answer, and here is
  why," a `guess` is "an answer, but here is how sure": `guess(value,
  confidence, source)` wraps any value with a confidence in `[0, 1]` and a
  free-text source label (`"model"`, `"sampled"`, whatever the caller's
  own provenance for the number is — Whence does not itself talk to a
  model; it gives a caller who does somewhere a value shape to report the
  result *in*).
- **New payload type, not a tagged record.** `shape`/structural types
  (v0.12) could have modeled this as `@{__tag: "guess", value: v,
  confidence: c}` with zero interpreter change — and that was seriously
  considered, then rejected: a tagged record is INERT. `record + record`
  is already a miss regardless of tags, so `guess(3, 0.9, "m") + 1` would
  have to be written point-free (`sure(g, 0.5) + 1`) every single time,
  which defeats the actual point of an AI-native primitive — that
  uncertainty should be threadable through ordinary arithmetic like `miss`
  already threads through it, not something you must manually unwrap
  before every use. That threading is the one thing a plain record cannot
  give you without operator overloading Whence does not have, so `Guess`
  is a real `values.py` class (mirroring `Miss`'s own shape exactly:
  `__slots__`, a dedup-and-order constructor for `sources`/`Miss.reasons`)
  and the interpreter's binary/unary op dispatch was extended, in exactly
  the two places that dispatch is centralized (see below).
- **Propagation rule: WEAKEST-LINK confidence (`min`), not an average.**
  `Interpreter._guess_binop` (`interp.py`) unwraps any Guess operand to
  its underlying node, computes the op AS IF both sides were certain via
  a plain recursive `self.binop(...)` call, then rewraps the result in a
  fresh `Guess` at `min()` of every contributing confidence, with sources
  unioned (deduped, ordered, mirrors `Miss.reasons`). A chain of five
  0.9-confidence additions is a 0.9-confidence sum, not a 0.59-confidence
  one (`0.9**5`) or a 0.9-confidence one via averaging that hides how many
  guesses actually went in — `min` is the only combinator under which "an
  answer is only as certain as its LEAST certain input" holds regardless
  of chain length, the same reason a `miss` chain does not need a decay
  function either. `_unary` (`-`/`not`) gets the identical treatment,
  recursing once on the unwrapped node.
- **A genuine type error stays a miss, never becomes an uncertain
  success.** `guess("x", 0.9, "model") + 5` computes `"x" + 5` on the
  unwrapped operands first; that is `mk_miss("cannot add str and num",
  ...)` under ordinary rules, and `_guess_binop` checks for exactly this
  (`isinstance(result.value, Miss)`) and returns it UNCHANGED rather than
  wrapping it in a `Guess` — a confidence score vouches for how sure you
  are of a valid answer, it cannot launder an invalid computation into a
  low-confidence one. Symmetric with `_check_ret` (v0.13) "a result that
  is already a miss propagates unchanged, before any inspection."
- **`==`/`!=` on a bare Guess go through `_guess_binop` too, not
  `deep_eq` — a genuinely different rule from structural equality
  elsewhere.** `1 == guess(1, 0.9, "model")` unwraps, computes `1 == 1`
  (True, certain), then rewraps: the RESULT is `guess(true, 0.9,
  "model")`, a Guess about whether they are equal, not a plain `true`.
  You cannot get a bare boolean out of comparing against an uncertain
  value without resolving the uncertainty first (`sure(...)` — see
  below) — the same discipline that already applies to arithmetic,
  applied to comparison for consistency, not because it was free. This is
  DELIBERATELY asymmetric with what happens when a Guess sits *inside* a
  container: `[guess(1, 0.9, "m")] == [guess(1, 0.9, "m")]` reaches
  `deep_eq` for the outer list-vs-list compare (neither top-level operand
  IS a Guess, both are lists), which recurses into elements and hits a
  new `deep_eq` case comparing two Guesses' underlying values only,
  IGNORING confidence/source — because `deep_eq` backs `contains`/`find`/
  structural-equality-as-a-utility, where "are these the same answer" is
  the useful question, not "how sure was each side." Two different
  questions, two different answers, both documented in `interp.py` at
  their respective call sites (`_guess_binop`'s docstring, `deep_eq`'s new
  `elif isinstance(l, Guess) and isinstance(r, Guess)` branch) precisely
  because the asymmetry is easy to mistake for a bug if it isn't spelled
  out.
- **`sure(v, threshold)` is the one way out, and a universal escape
  hatch, not a guess-only operation.** `sure` on a plain (non-Guess) value
  is a no-op pass-through — ordinary code can call `sure(x, 0.8)`
  defensively without checking `is_guess(x)` first, the same "total,
  works on anything" discipline `missed`/`matches`/`shapeof` already
  have. On a Guess: confidence `>=` threshold returns the ORIGINAL
  underlying node, pass-through, no new provenance step (mirrors `typed`'s
  own "no new node on a match" convention exactly) — so `sure()`ing a
  guess back down to a definite value is truly transparent, not lossy;
  below threshold is `mk_miss("guess confidence C below threshold T
  (sources)", ...)`, an ordinary miss that then propagates like any other.
- **Deliberately shallow, same discipline as v0.12–14 — costs ZERO extra
  code, not merely undocumented:** indexing (`_index`), field access
  (`_field`), and call dispatch do not recognize `Guess` as a
  list/record/callable, so `guess([1,2], 0.9, "m")[0]` is an ordinary
  "cannot index guess 0.9 (\"m\"): [1, 2]" miss — `sure()` first, same as
  any other wrong-shape value — for FREE, because those functions already
  fall through to their existing "unrecognized payload" miss branch via
  `show_payload` (which gained a `Guess` case for exactly this reason,
  `values.py::_show`). `and`/`or`/`if` are equally untouched
  (`_logic_left`, `_logic_right`, `_if_bad`): a Guess is not a `bool`, so
  those already-existing "needs true/false, got %s" misses fire
  unmodified, `show_payload` again doing the rendering work. Only
  arithmetic, comparison, and unary negation/`not` were actually touched;
  everything else "supports" Guess only in the sense that it fails
  helpfully instead of crashing, which every payload type already got for
  free from the total-by-construction interpreter.
- **`shapeof`/`typed`/`matches` integration is one line each.** `_kind`
  (`interp.py`) gained `(Guess, "guess")` in `_KIND_ORDER`, and
  `PRIMITIVE_TYPES` (`parser.py`) gained `"guess"` — so `fn f(a: guess) {
  ... }` is a real, working type contract ("this parameter must still
  carry a confidence score; committing it is the callee's job"), erased
  by the existing v0.12 machinery with no new code path.
- **New builtins** (all in `interp.py`'s builtin table, `guess`/
  `is_guess`/`confidence`/`sure`): `guess(value, confidence, source)`
  (arity 3, propagates a miss `value`/`confidence`/`source`; validates
  confidence is a num in `[0, 1]` and source is a str; a `guess` of an
  already-`Guess` value FLATTENS rather than nests — `min` of the two
  confidences, sources unioned — the same "never wrap a Miss around a
  Miss" discipline `merge_miss` already has for the sibling type);
  `is_guess(v)` (arity 1, total, mirrors `matches`); `confidence(v)`
  (arity 1, a miss "not a guess" on anything else); `sure(v, threshold)`
  (arity 2, described above).
- **New example `examples/guess.lang`** and `tests/test_v15.py`
  (mirroring `test_v14.py`'s structure): weakest-link confidence through
  a chain of arithmetic, a genuine type error staying a miss even with
  guessed operands, `sure()`'s pass-through-on-success/miss-on-shortfall
  both ways, the non-Guess-is-always-sure no-op, `guess`-of-`guess`
  flattening, `is_guess`/`confidence`/`shapeof`/`typed` integration, the
  `==`-vs-`deep_eq` asymmetry pinned explicitly both ways (bare compare
  vs. compare-inside-a-list), and `assert_three_way` cases confirming fast
  /direct/trampoline agree byte-for-byte on Guess-carrying programs (no
  reason to expect disagreement — `_guess_binop`/`_unary` sit in the
  SHARED dispatch both the generator and fast/direct-compiled paths
  eventually call through, the same reason v0.14 needed zero interpreter
  change at all worked out in v0.15's favor here too, just one level
  removed: the compiled `f_add`/`f_sub`/… closures inline only the
  int/float/str hot paths and fall through to `binop()` for anything
  else, so a `Guess` operand reaches the exact same `_guess_binop` call
  regardless of which path evaluated it, with no separate fast-path
  copy to keep in sync).
- **Guest parity: shipped round 176** (was "not started" through round
  168-174; see the subsection below) — the fastest a feature has closed
  its guest-parity gap yet (`: Type`/`-> Type` took from round 122/126 to
  round 158; `effects` from round 146 to round 164).

### v0.15 guest parity (round 176)
- **A guest Guess IS the host's own `Guess` payload, not a hand-rolled
  tagged record.** `self_eval.lang`'s `apply_host_builtin` delegates
  `guess`/`is_guess`/`confidence`/`sure` straight to the real host
  builtins (the guest passes its already-unboxed `.v` payload through),
  so arithmetic/comparison on a guest Guess reuses the host's own
  `_guess_binop`/`_unary` propagation for free — no Whence-source
  reimplementation of weakest-link confidence or source-unioning was
  needed or possible (the guest has no accessor for a Guess's raw
  `.sources`/`.node`).
- **The cost of that shortcut: every "does v look like a T" probe
  (`is_num`/`is_list`/`is_bool`/`is_str`) had to be Guess-guarded first**,
  because Guess arithmetic is transparent by design — `guess(5, .9, "s") +
  0` succeeds, so `is_num` would otherwise misreport a Guess-wrapped
  number as a plain num. `is_guess_val` is checked before all four, and
  `guest_kind` checks it immediately after `missed`.
- **`==`/`!=` on a bare guest Guess bypass the guest's own `guest_eq`
  comparator on purpose** and delegate to the host's real `==`/`!=`
  (which return a NEW Guess wrapping the boolean, per the host's own
  `==`-vs-`deep_eq` asymmetry) — every other operator needs no guest-side
  change at all, since `a.v OP b.v` in `apply_binop` is already real
  top-level Whence source running under the true host interpreter.
  `raw_deep_eq` gained its own separate Guess-vs-Guess case (compares the
  unwrapped answer via `sure(_, 0)` only, ignoring confidence/sources —
  mirroring the host `deep_eq`'s own case, used when a Guess sits inside a
  container rather than at top level).
- **`"guess"` joined `guest_primitive_types`** (both `self_eval.lang` and
  `self_host.lang`, which must stay byte-identical in their shared
  parser section — `test_parser_section_matches_self_host` pins the line
  range) so `fn f(x: guess)` type-checks on the guest exactly as it does
  on the host.
- **`harness/swe/guest.py`'s guest-differential fuzzer/oracle gained
  matching support**: the `BANNED` line-filter no longer strips
  `guess`/`is_guess`/`confidence`/`sure` calls (they were banned
  outright when this feature shipped with zero guest support, round
  168/174), and the `agree()` comparator gained a Guess-vs-Guess case
  that checks confidence/sources exactly (a stronger check than
  `deep_eq`'s answer-only comparison, deliberately — this oracle is
  hunting for guest bugs, not backing a utility function). A 300-sample
  differential fuzz run found 0 mismatches; `test_self_eval.py` gained a
  dedicated `show_payload`-based test confirming confidence/sources
  render identically host-vs-guest (a check `deep_eq`-based agreement
  alone cannot make, since `deep_eq` treats them as pure metadata).

## Builtins
`print len range map filter fold push str num abs sqrt missed reasons note
contains join keys merge get put has find steps at blame diverge contrast
typed matches shapeof guess is_guess confidence sure`

## Limits that are errors, not crashes
- Expression nesting deeper than 60 levels (parentheses, prefix operators,
  `else if` chains) is a parse error (exit 2), not a host RecursionError.
- Runaway non-tail recursion is a `max_depth` miss; a runaway tail loop is
  unbounded unless `--max-iter` is given.
- Structural `==` on arbitrarily deep values is iterative (a 20000-deep
  record compares without touching the host stack).
- **v0.4.1 (round 011):** arithmetic that mixes an unbounded integer with
  a bounded float (`huge / 3`, `huge * 1.5`, `huge % 0.5`, `sqrt(huge)`,
  `huge / 1`) is a `miss: number too large for float arithmetic`, never a
  host OverflowError; `3 / huge` underflows to `0.0` (that is arithmetic,
  not an error). `num(text)` accepts only Whence number syntax — optional
  sign, ASCII digits, optional fraction, optional exponent — with
  surrounding whitespace tolerated (`num(" 3.5 ")` is `3.5`); host-only
  spellings (`"1_000"`, `"nan"`, `"inf"`, `"0x10"`, `"1."`, `".5"`,
  non-ASCII digits) are a `cannot parse` miss and a finite-syntax value
  that overflows a float (`"1e400"`) is an `out of range` miss. (Round 5
  had made these decisions on a temp copy of the checkout that never
  shipped; the round-11 differential oracles re-found the whole family.)

## Running
`python3 run.py [--max-depth N] [--max-iter N] [--no-direct]
examples/<name>.lang` — exit 0 (all checks pass / none), 1 (some check
failed), 2 (lex/parse error). Embedding: `Interpreter(out=...,
max_depth=..., max_iter=..., fast=True, direct=True, gc_relief=False)`; no
`sys.setrecursionlimit` needed — direct mode (v0.9) spends only the host
frames that are demonstrably free and the trampoline takes over beyond
that, so a Whence call never *requires* host stack; a tail call costs zero
Whence frames (`interp.tail_calls` counts them; `interp.fast_hits` counts
driver entries into compiled closures, `interp.direct_hits` /
`direct_fallbacks` the direct calls and the ones the budget refused).


## Time-Travel Debugging — NOT integrated (whence/timetravel.py, round 132 note)
A `TimeTravelDebugger` Python class (checkpoint/rewind/timeline/diff over an
`Env.vars` dict) landed in a commit outside the round process
(`8637795`, "Time-Travel Debugger v0.7 complete!") along with a prior draft
of this section claiming five new Whence-language builtins (`snap`,
`rewind`, `timeline`, `diff_snap`, `trace`). **That draft was wrong: the
builtins are not reachable from any `.lang` program.** `install_timetravel_
builtins(interp)` exists but nothing calls it (`grep -rn install_timetravel
whence/*.py run.py` — zero hits outside `timetravel.py` itself); no example
uses it. Even if wired in, it would not work as written: it writes to
`interp.builtins[...]`, but the real dispatch table is the module-level
`_BUILTIN_TABLE` singleton (`interp.py`, built once by `_install_builtins`
— the exact per-instance-vs-shared split round 25's oracle-caught bug was
about); `snap_builtin` never forwards its own `name` argument to
`ttd.snapshot()`, which instead reads a variable `_last_snap_name` that is
never bound anywhere; and every builtin fn assumes raw Python values
(`isinstance(name, str)`, `interp.miss(...)`) where Whence's actual builtin
convention is `fn(interp, args, line)` with `args` as `Prov`-wrapped values
and no `Interpreter.miss` method exists. The corrected, previously-invalid
example (`let x = x + 10` rebinds `x` in the same block, a parse error
under decision 3) is deleted rather than fixed, since the feature it
demonstrated is not live. `tests/test_timetravel.py` (11 tests, green)
exercises `TimeTravelDebugger` directly as a Python class — that part is
real and correctly tested, just never connected to the interpreter.
Left as a flagged backlog item, not fixed this round (see research-state.md
round 132): either rewrite `install_timetravel_builtins` to the real
convention and wire it into `Interpreter.__init__`, or delete the dead
integration hook and keep `TimeTravelDebugger` as a documented pure-Python
helper (e.g. for a future REPL) — a decision for whichever round picks it
up, not a default to make silently.
