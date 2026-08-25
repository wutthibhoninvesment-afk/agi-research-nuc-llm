# Whence — a provenance-first language (spec v0.9, rounds 009/011/014/020/024/026/030)

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

## Builtins
`print len range map filter fold push str num abs sqrt missed reasons note
contains join keys merge get put has find steps at blame diverge contrast`

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
