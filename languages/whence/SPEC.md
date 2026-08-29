# Whence — a provenance-first language (spec v0.16.6 + v0.14.2, rounds 009/011/014/020/024/026/030/108/110/122/128/132/146/164/168/204/206/210/216/218/222/224/264/266)

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
- **Self-hosting round 6 (round 192)** ran the guest evaluator ON the guest
  lexer/parser's own real source for the first time — not a hand-picked
  corpus snippet, `self_host.lang`'s actual ~680-line file, feeding
  `self_eval.lang`'s `run_src` two full levels of tree-walking
  interpretation deep. This found a real bug the fuzzer had 20+ rounds to
  catch and never did: `self_host.lang`'s hand-copied `suppressed()`
  newline-continuation check only implemented HALF of `whence/lexer.py`'s
  rule (bracket depth), missing the other half — a newline right after a
  token that "cannot end a statement" (an operator, `=`, `:`, `,`, or
  `and`/`or`/`not`/`rescue`) is ALSO a continuation, independent of
  brackets. `self_host.lang`'s own multi-line `check "label":\n  expr`
  style (and `effects.lang`'s, see below) round-trips fine under the HOST
  but was an unconditional `parse_error` under the GUEST — invisible to
  every fuzz run because the fuzzer's printer never emits a bare trailing
  operator/colon/keyword followed by a real newline. Fixed with a
  `last_continues(acc)` helper (checks the last emitted token's `t`/`v`
  against a `continue_ops`/`continue_kws` list) OR'd into `suppressed`,
  mirrored byte-identically in both `self_host.lang` and `self_eval.lang`'s
  shared parser section (`test_parser_section_matches_self_host` pins the
  line range, now 27..561). Confirmed at both levels: the guest parser
  called directly on the full source (`tests/test_self_hosting.py::
  test_guest_parser_parses_its_own_full_source`, pins 154 top-level
  statements) and the guest EVALUATOR interpreting the parser as guest
  closures (`test_guest_evaluator_executes_self_host_library`). As a side
  effect this also closes round 164's old backlog item — `effects.lang`'s
  own `check "...":\n  expr` line was the exact same bug, and now parses
  and evaluates cleanly under the guest (`test_effects_lang_runs_under_the_
  guest_round_164_backlog_closed`). A full run of `self_host.lang`'s ENTIRE
  66-check test section through `run_src` (guest-evaluating the guest's own
  full test suite, not just its library) was attempted and abandoned: RSS
  passed 1.7 GB and was still climbing after 3 minutes on this machine's
  3.8 GB budget — a first real data point on how guest-level tree-walking
  cost compounds on a non-synthetic program, not pursued further this
  round.
- **Self-hosting round 7 (round 200)** turned that single data point into a
  curve and a root cause, safely: each probe runs in a fresh subprocess with
  `resource.setrlimit(RLIMIT_AS, cap)` set before any Whence code runs
  (`bench/self_host_memscale.py`), so a runaway hits a clean, immediate
  Python `MemoryError` inside that one subprocess — enforced by the kernel
  at allocation time, independent of what else is running — instead of
  risking the kernel OOM-killer picking an unrelated victim on a
  memory-tight box shared with live trading services (round 198's stated
  reason for not attempting this live). Growing `self_host.lang`'s own
  66-check test section one checkpoint at a time through `run_src`: 5
  checks 112 MB, 10 → 113 MB, 15 → 126 MB, 20 → 198 MB, 25 → 259 MB, 30 →
  366 MB, 31 → **738 MB** — one added statement (a `parse_whence` call on a
  three-branch if/else program) roughly doubled peak RSS. Root cause,
  confirmed by reading the interpreter, not guessed: the guest store is a
  Whence record threaded through every step (see above), and `put`
  (`whence/interp.py` `b_put`) does `fields = dict(r.payload.fields)` — a
  full shallow copy of the CURRENT store on every single update, no
  structural sharing (unlike lists, v0.6). Worse, every `derived(...)`
  result keeps its `inputs` — including the prior, now-superseded store
  copy — alive forever via the provenance graph (`why`/`steps` must be able
  to trace back through it, by design), so old copies are never collected.
  N sequential `put`s each costing O(current store size) is quadratic
  cumulative cost by construction; a guest program with many top-level
  statements (`self_host.lang`'s test section, not the library, is exactly
  this shape — one `put` per statement onto an ever-growing store) is the
  worst case. This is a quantified explanation for round 192's "1.7 GB and
  still climbing," not a new bug — the store-copying cost was already named
  as `self_eval.lang`'s bottleneck as far back as round 010's summary, just
  never measured. A fix (structural sharing for records, e.g. a persistent
  map) is a real but nontrivial interpreter change with no current
  curriculum driver; flagged as optional future backlog, not attempted this
  round. **Built round 204 — see "v0.16" below**: `Record` is now backed by
  `PMap`, a persistent AVL tree, closing this gap.

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
  parameter types only. **Stale-note correction (round 240): this used to
  say "a return annotation is future work, not started" — true when this
  section was written (round 122) but closed the very next version; see
  `## v0.13 (round 128/132) — return type annotations` below, which even
  has its own round-234 stale-note correction for a different paragraph.
  This is the same "prose describing a resolved question as still open"
  bug class rounds 230/234/236 already found and fixed elsewhere in this
  file/repo, just one section closer to the root this time — the very
  bullet that originally posed the question, not a later summary of it.**
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
- **Stale-note correction (round 234):** this bullet used to say the
  fuzzer's program grammar did not generate `: Type`/`-> Type` annotations
  yet and called it a "standing backlog, not blocking." That was true when
  this section was first written (round 128/132) but was closed shortly
  after and this paragraph was never updated — round 134 (verified round
  144) added `TYPE_TAGS`/`typed_params()`/`maybe_ret_type()` to
  `harness/swe/fuzz.py`, wired into every generated `fn` (30%/param and
  25% chance respectively), so both param and return guards have been
  exercised by every fuzz/oracle campaign run since. The guest side closed
  later still: `harness/swe/guest.py`'s `GuestGen` overrode both hooks to
  a no-op until round 158 taught `self_eval.lang`/`self_host.lang`'s
  shared parser section to tokenize `: TAG`/`-> TAG` and gave the guest
  evaluator its own `typed` builtin + return-type check — `GuestGen` now
  inherits the real (non-no-op) grammar unchanged (see `guest.py`'s own
  `GuestGen` docstring for the two-round arc). What genuinely remains
  out of scope, by construction rather than oversight: `TYPE_TAGS` is
  primitive tags only (`num str bool list record fn any`), so no fuzzed
  program ever names a `shape` as a type spec on either the host or guest
  side — `self_eval.lang` still has no `shape` support at all (round
  144/224's own SPEC notes on `typed`/`matches` guest parity, above and
  below, cover this same limit from the builtin-dispatch side). No new
  example beyond extending `examples/shapes.lang` with a return-typed
  `midpoint`/`broken_midpoint` pair (4 new checks, 12 → 16) — a dedicated
  flagship example was judged unnecessary since the feature composes
  directly with v0.12's existing one and the design point (return checks
  are call-boundary checks like parameter checks) is best shown as an
  addition, not a separate story.

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
  supports, not just `check`. Tracked as fresh backlog at the time; closed
  by round 192 (`test_effects_lang_runs_under_the_guest_round_164_
  backlog_closed`, confirmed still closed by round 230's re-check) —
  this paragraph previously read "tracked as fresh backlog" past that
  fix, corrected here (round 264).

## v0.14.1 (round 264) — effect system: nested fns inherit lexically
- **Closes the first of v0.14's two documented "deliberately SHALLOW"
  gaps** (see the two bullets above): "a nested `fn` defined inside a
  restricted body is a separate closure with its own (absent, hence
  unrestricted) declaration" — a clause-less nested fn could print freely
  even lexically inside an `effects []` function, an escape hatch v0.14
  called out and `examples/effects.lang`'s `strict_sum` demonstrated on
  purpose. Closed by making a fn with NO clause of its own **inherit its
  nearest enclosing fn's already-resolved effect scope** instead of
  defaulting to unrestricted — pure lexical scoping, not a call-graph
  analysis.
- **Mechanism:** `Parser._resolve_effects_scope(own_spec)` — `own_spec`
  (the fn's own `parse_effects_clause()` result, `None` if absent) wins
  if not `None`; otherwise the CURRENT top of `self.effects_stack` is
  reused. Both push sites (`fn name(...)` statements and anonymous
  `fn(...) {...}` expressions) call this before pushing, so `_check_
  effect_call` itself needed no change — `effects_stack[-1]` is already
  the fn's fully resolved scope by the time any call inside its body is
  checked. Because inheritance only ever reads an ALREADY-pushed frame,
  a top-level fn (`effects_stack` empty) with no clause still resolves to
  `None` (unrestricted) exactly as before — no behavior change for any
  program that never nests an `effects`-relevant fn.
- **An explicit clause on the nested fn still always overrides the
  inherited scope, in either direction** — narrower, broader, or
  unrelated — the same "one settle point, explicit always wins" rule
  return types (v0.13) already established. This is why
  `test_nested_undeclared_fn_escapes_outer_purity` (an inner fn that
  explicitly declares its OWN `effects [io]` inside an outer `effects
  []`) is unchanged and still passes: it was never testing the
  clause-LESS case this round closes, only that an explicit declaration
  is independent of its lexical parent.
- **`examples/effects.lang`'s `strict_sum` updated to match**: its nested
  `debug_print` (previously clause-less, printing "for free" inside a
  pure outer fn) now declares its own `effects [io]` explicitly — the
  file's own comment rewritten to demonstrate the new default
  (inheritance) alongside the still-available explicit opt-out, instead
  of celebrating the now-closed implicit escape.
- **Still open, unaffected by this round** (the second v0.14 gap):
  passing a builtin as a value (`let p = print`) and calling THAT is
  still invisible to the check — `_check_effect_call` only inspects a
  literal `NameRef` callee, and this is fundamentally a value-flow
  question, not a lexical-scoping one, so it needs a different mechanism
  entirely. Also still open: a fn calling a DIFFERENT, unrestricted
  top-level fn that itself performs the effect — only LEXICAL nesting is
  tracked now, not the dynamic call graph. A full call-graph-aware
  (transitive) effect system closing both remains future work.
  **Partially closed by v0.14.2 (round 266, below)**: the direct-alias
  case (`let p = print` then `p(1)`) specifically is now tracked; passing
  a builtin through a function argument, return value, or a list/record
  field, and the separate call-graph gap, both remain open.
  **Further partially closed by v0.14.3 (round 270, below)**: the
  bare-name-tail return-value case (`fn get() { print }` then `let p =
  get()` or `get()(1)`) is now tracked too; a function ARGUMENT, a
  list/record field, a tail hidden behind an `if`, and the call-graph gap
  all remain open.
  **Further partially closed by v0.14.4 (round 272, below)**: a
  literal-record field case (`let box = @{run: print}` then `box.run(1)`)
  is now tracked too; a function ARGUMENT, a non-literal or call-valued
  record field, a tail hidden behind an `if`, and the call-graph gap all
  remain open.
- **Verification:** `tests/test_v14.py` 20/20 (was 18; one test rewritten
  from `all_ok` to `pytest.raises(ParseError)` since its own assertion
  flipped, two new tests added: a granting-scope inheritance case and a
  two-level inheritance-chains-transitively case).
  `languages/whence/run_tests_fast.sh` 850 passed/38 deselected (was 842
  before landing round 263's own lexer mutation-testing work in a
  separate commit first; +8 = round 263's own +7 lexer tests +1 net from
  this round's test_v14.py changes). Full `pytest tests/` (background,
  no `-m` filter) **888 passed in 819.79s**. `examples/effects.lang`
  re-run directly: all 4 checks pass, output unchanged in spirit (the
  nested "(debug)" prints still happen, now via an explicit clause).
  Guest parity needed NO change and was re-verified, not just assumed:
  `harness/swe/guest.py`'s guest evaluator (`self_eval.lang`) never
  enforced `effects [...]` at all — round 164's own header comment says
  so explicitly ("skip-and-ignore, not enforce") — so this is a HOST-only
  parse-time change; a program the host newly rejects surfaces as the
  already-handled `parse_error` oracle outcome
  (`harness/swe/guest.py::oracle_self_eval` returns early on a host
  `ParseError`, never reaching the host-vs-guest value comparison, so it
  cannot manufacture a false differential mismatch) — cross-checked
  directly against `harness/swe/fuzz.py`'s `ProgramGen`, which DOES
  generate exactly this shape (a clause-less anonymous `fn(...)` 70% of
  the time, nestable inside an `effects [...]`-declared outer fn via
  `expr`/`fnlike`), confirming this isn't a theoretical-only path.

## v0.14.2 (round 266) — effect system: direct builtin aliases are tracked
- **Closes the FIRST HALF of v0.14.1's own "still open" gap**: "passing a
  builtin as a value (`let p = print`) and calling THAT is still invisible
  to the check" (SPEC.md "v0.14.1", above). Closed for the direct-alias
  case only — `let p = print` then `p(1)` is now checked exactly as
  `print(1)` would be — by tracking, at parse time, which currently
  in-scope names are a direct alias of an effectful builtin.
- **Mechanism:** `Parser.alias_scopes` — a stack of dicts, one per lexical
  block scope (pushed/popped by `stmt_list` itself, so every `{...}`,
  including a bare block-as-expression, an `if` arm, and a fn body, gets
  its own frame), name -> tag-or-`None`. A `let NAME = <expr>` statement
  records `alias_scopes[-1][NAME] = tag` where `tag` is whatever
  `_resolve_effectful_alias(expr.name)` returns if `expr` is a bare
  `NameRef` (`None` for any other expression shape). `_resolve_effectful_
  alias(name)` walks the stack innermost-first and returns the FIRST
  frame's value for `name` if any frame has an entry at all — falling back
  to `_EFFECTFUL_BUILTINS` only if NO scope frame mentions `name`.
  `_check_effect_call` now calls this instead of indexing
  `_EFFECTFUL_BUILTINS` directly, so a checked call is "callee resolves to
  an effect tag", not "callee's literal name is `print`".
- **Shadowing is handled correctly, not just aliasing**: recording `None`
  (not skipping the entry) for every plain `let`/`fn`/parameter binding —
  not only ones that happen to alias a builtin — means a local `let p = 5`
  correctly BLOCKS the lookup from falling through to an outer alias `p`,
  rather than misidentifying the shadowed local as the alias. A named
  `fn NAME(...)` statement similarly stakes `None` into the ENCLOSING
  scope's frame for its own name (same slot a `let` would occupy) before
  parsing its params/body, so `fn p() {...}` shadows an outer alias `p`
  too. A fn's OWN parameters get a separate frame, pushed between the
  enclosing scope and the body block's own `stmt_list` frame — mirroring
  the real runtime Env layering (`interp.py`: `_call_gen`'s `call_env`
  holds params, `eval_Block`'s own `inner` is a CHILD of that for the
  body's own `let`s) — so a parameter also correctly shadows an outer
  alias of the same name.
- **Chains transitively**: `let q = p` where `p` is itself a tracked alias
  re-resolves through `_resolve_effectful_alias`, so `q` becomes an alias
  of whatever `p` ultimately aliases, any number of hops deep.
- **Order-dependent, like the rest of this single left-to-right parse
  pass** (the same character `_resolve_effects_scope`'s nested-fn
  inheritance already has): only an alias `let` that appears TEXTUALLY
  BEFORE the call it would cover, in a currently-open scope, is detected.
  A `let` written after the call site it would have covered (e.g. inside
  a closure defined and stored before the alias exists, never invoked
  before the alias binding executes) is invisible — this is a
  single-pass static analysis, not a whole-program fixed point.
- **Still open, unaffected by this round** (the SECOND half of the same
  v0.14.1 gap, plus the pre-existing one): passing the builtin as a
  FUNCTION ARGUMENT, returning it from a call, or storing it in a
  list/record field and calling it back out are all still invisible —
  only a direct `let alias = <name-or-alias>` hop is tracked, not general
  value flow through data structures or other bindings (`for`/pattern
  bindings, if Whence ever gains them). **Partially closed by v0.14.3
  (round 270, below)**: the "returning it from a call" clause specifically
  is now tracked, for the narrow case where the returning fn's own body
  tail-returns a bare name — a function ARGUMENT, a list/record field, and
  a tail hidden behind an `if` all remain invisible. Calling into a DIFFERENT,
  unrestricted top-level function that itself performs the effect is
  ALSO still untouched by the caller's own declaration — only lexical
  nesting and direct aliasing are tracked, not the dynamic call graph. A
  full call-graph-aware (transitive, data-flow-sensitive) effect system
  closing both remains future work. **Further partially closed by v0.14.4
  (round 272, below)**: the "storing it in a record field" clause is now
  tracked too, for the narrow case where the record is a `let`-bound
  LITERAL and the field's own value is a bare name — a function ARGUMENT,
  a non-literal or call-valued record field, and a tail hidden behind an
  `if` all remain invisible.
- **Verification:** `tests/test_v14.py` 28/28 (was 20; one test renamed
  from `test_indirect_call_via_variable_is_not_checked` to `..._is_now_
  checked` since its own assertion flipped from `all_ok` to
  `pytest.raises(ParseError)`, 7 new tests added: grant-still-works,
  two-hop chaining, `let`-shadowing, nested-`fn`-name-shadowing,
  parameter-shadowing, cross-scope visibility into a nested fn, and the
  order-dependence limitation, plus one new three-way differential pin).
  `languages/whence/run_tests_fast.sh` 858 passed/38 deselected (was 850;
  +8 = this round's own net test delta). `examples/effects.lang` extended
  with a `log_total`/`logger` demonstration (an `effects [io]` fn calling
  `print` through a `let logger = print` alias) and re-run directly: all 5
  checks pass (was 4).
- **Guest parity needed no change, for a different and STRONGER reason
  than v0.14.1's**: `print` itself is in `harness/swe/guest.py`'s
  `BANNED` regex — any guest-oracle program that so much as MENTIONS
  `print` anywhere before its own `__result` scrub line is short-circuited
  to a `parse_error`-labeled outcome before the host or guest ever runs it
  (`oracle_self_eval`'s own `BANNED.search` check, ahead of even calling
  `O._parse`), because the guest evaluator does not mirror `print`'s
  host-visible output at all. This is unaffected by, and unrelated to,
  the generic "a host `ParseError` short-circuits before any host-vs-guest
  comparison" mechanism v0.14.1 relied on — `print`-mentioning programs
  never reach that comparison for an entirely separate, pre-existing
  reason. Cross-checked against `harness/swe/fuzz.py`'s `ProgramGen`:
  unlike v0.14.1's nested-clause-less-fn shape (confirmed fuzzable), this
  round's own trigger shape — a bare `print` NameRef assigned by a `let`,
  rather than called directly — does **not** appear anywhere in the
  generator grammar (`print(...)` is always emitted as a literal call
  template, e.g. `"print(%s)"`, never as a bare value); this feature is
  exercised only by `tests/test_v14.py`'s hand-authored cases, not
  cross-validated against the differential fuzz corpus. Documented here
  rather than treated as a gap to close, since fixing it would mean
  teaching the GENERATOR a new expression shape, not the effect checker
  itself, and no other host-only parse-time feature in this codebase has
  ever required generator changes to be considered adequately tested.

## v0.14.3 (round 270) — effect system: RETURN-value flow through a direct call

- **Closes one narrow clause of v0.14.2's own "still open" gap**: "passing
  the builtin ... returning it from a call ... [is] still invisible" —
  closed for the specific shape where the RETURNING function's own body's
  tail statement is a bare name resolving to an effectful alias.
  `fn get_printer() effects [] { print }` doesn't itself perform the "io"
  effect (naming `print` in tail position isn't calling it), but
  `let p = get_printer()` now propagates the fact that `p` holds an
  effectful alias, checked exactly as `let p = print` (v0.14.2) would be.
- **Mechanism**: `Parser.return_alias_scopes` — a SECOND stack, the exact
  same shape as `alias_scopes` (one frame per lexical block, pushed/popped
  at the identical three sites: `stmt_list` itself, and both fn-parameter
  scopes), tracking a different fact per name: "does CALLING this name
  yield an effectful alias" rather than "IS this name one". Populated from
  `stmt_list`'s own new `tail_alias_tag` return value — computed while the
  block's own `alias_scopes` frame is still open, so it can resolve a tail
  statement referencing either a parameter or a body-local `let`, not just
  the fn's own params — stashed onto the real `Block.tail_alias_tag` field
  (`ast_nodes.py`; set at construction, unlike `Call.tail`, which
  `mark_tails` sets in a separate later pass, since `stmt_list` has already
  fully resolved this by the time `block()` constructs the node). A named
  `fn NAME(...)` statement writes `return_alias_scopes[-1][NAME] = None` as
  a placeholder BEFORE parsing its own params/body (shadow-safety and
  self-recursion-safety, mirroring `alias_scopes[-1][NAME] = None`'s
  identical role in v0.14.2), then overwrites it with `body.tail_alias_tag`
  once the body is fully parsed and its own frames popped, back in the
  ENCLOSING scope's frame. `_resolve_effectful_return(name)` walks the
  stack innermost-first, same as `_resolve_effectful_alias`, with no
  `_EFFECTFUL_BUILTINS` fallback (this fact only ever comes from a
  user-written fn body's own tail, never a builtin itself).
- **Three call shapes all read from the same table**: (1) `let p =
  get_printer()` — the `let`-handling code recognizes an `A.Call` expr
  whose own callee is a NameRef with a tracked return fact, and propagates
  it into `p`'s `alias_scopes` entry (an ordinary alias from here on,
  needing no new logic at the `p(...)` call site). (2) `get_printer()(1)` —
  chained, no intermediate `let` — `_check_effect_call` gained a second
  branch: a `Call` callee whose own `fn` is a NameRef resolves through
  `_resolve_effectful_return` directly. (3) `let g = get_printer` (a plain
  RENAME, no call) now carries BOTH of `get_printer`'s facts to `g` — its
  direct-alias status (already true in v0.14.2, was `None` here since a fn
  name is never itself an alias) AND its return fact, so `g()`'s result is
  checked exactly as `get_printer()`'s would be. The same propagation
  applies to a `let`-bound anonymous `fn(...) {...}` — its own
  `body.tail_alias_tag`, already resolved by `block()`, is read directly at
  the `let` site (`expr.__class__ is A.FnExpr`), no separate named-fn
  machinery needed.
- **Shadowing is handled correctly, the same class of bug v0.14.2's own
  design note (§4 of `knowledge/round-266-...md`) warned about**: every
  `let`/named-`fn`/parameter binding writes an explicit entry into BOTH
  stacks (even `None`), not just the ones that happen to carry a fact — an
  inner, differently-behaved `fn get_printer() { 5 }` correctly shadows an
  outer, effectful-returning `get_printer` of the same name, blocking the
  lookup rather than falling through to the stale outer fact.
- **Deliberately narrower than it could be, by design**: only a fn body
  whose tail statement is a BARE NameRef is inspected — a tail that is
  itself an `if` (even one whose every arm tail-returns the same effectful
  name) is not recursed into, unlike `mark_tails`'s fuller structural walk
  of tail position (that one needs no scope context at all, since it only
  ever flips a boolean; this one does, so it can't simply run as a
  after-the-fact pass over the finished AST — it has to observe the
  `alias_scopes`/`return_alias_scopes` frames while they're still open,
  which only `stmt_list` itself can do without threading parser state
  through a second AST walker).
- **Still open, unaffected by this round**: passing a builtin as a FUNCTION
  ARGUMENT, or storing it in a list/record field and reading it back out,
  remain completely invisible — genuine value-flow-through-data-structures
  questions this round does not attempt. The dynamic call graph (calling a
  DIFFERENT, unrestricted function that itself performs the effect) is also
  still untouched. A full call-graph-aware, fully data-flow-sensitive
  effect system closing all of these remains future work — see
  `state/research-state.md`'s language backlog for why the call-graph half
  specifically is sized as multi-round-scale, not a quick follow-up.
- **Verification**: `tests/test_v14.py` 37/37 (was 28; 9 new tests: return
  value via `let` [checked + granted], chained call with no `let` [checked
  + granted], renamed-fn fact propagation, `let`-bound anon fn, the
  same-name shadowing case, the bare-name-tail-only limitation, and one new
  three-way differential pin). `languages/whence/run_tests_fast.sh` 867
  passed/38 deselected (was 858; +9 matches the net new-test delta
  exactly). `examples/effects.lang` extended with a `get_logger`/
  `log_total2` demonstration; `python3 run.py examples/effects.lang` → exit
  0, 6/6 checks pass (was 5/5). `tests/test_examples.py::test_effects` and
  `tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed` both updated for the new check count (6, was 5)
  and re-verified green — the guest evaluator still does not enforce
  `effects [...]` at all (round 164's own finding, unchanged), so this is
  purely one more ordinary check passing through it, same reasoning as
  round 266's own guest-parity note.
- **Fuzz coverage — same honest gap as v0.14.2, for the same reason**:
  `harness/swe/fuzz.py`'s `ProgramGen` never emits a bare `print` NameRef in
  tail position (or anywhere) — `print(...)` is always one of its literal
  call templates (`"print(%s)"` and variants). This round's own trigger
  shapes (a fn whose tail is a bare effectful name, then calling that fn's
  result) are consequently exercised only by `tests/test_v14.py`'s
  hand-authored cases, not the differential fuzz corpus — not a new gap,
  the same one v0.14.2 already documented and left open for the identical
  reason (fixing it needs a new GENERATOR expression shape, not a checker
  change).

## v0.14.4 (round 272) — effect system: CONTAINER-FIELD value flow through a record literal

- **Closes the CONTAINER-FIELD slice of v0.14.3's own "still open" gap**:
  "storing it in a list/record field and reading it back out" remains
  invisible in general, but is now closed for the specific shape where the
  record is built directly by a `let name = @{...}` LITERAL and the field
  in question was assigned a bare NameRef. `let box = @{run: print}` then
  `box.run(1)` is now checked exactly as `let p = print; p(1)` (v0.14.2)
  would be.
- **Mechanism**: `Parser.field_alias_scopes` — a THIRD stack, the exact
  same shape and push/pop sites as `alias_scopes`/`return_alias_scopes`
  (one frame per lexical block: `stmt_list` itself, and both fn-parameter
  scopes), tracking a third fact per name: "is this name bound to a record
  literal, and if so, which of its fields are themselves effectful
  aliases?" Each frame maps a name to either `None` (not a tracked record
  binding) or a dict `{field: tag-or-None}`, built once, at the `let`, by
  resolving each field VALUE that is a bare `NameRef` through the existing
  `_resolve_effectful_alias`. `_resolve_effectful_field(name, field)`
  mirrors the other two resolvers exactly: innermost-first, first-frame-
  wins walk on `name`, then a plain `.get(field)` within the winning
  frame's dict.
- **`_check_effect_call` gained a third branch**: a callee that is an
  `A.FieldAccess` whose own `.obj` is a NameRef resolves through
  `_resolve_effectful_field` — sitting alongside the existing direct-name
  and chained-call-return branches, all three feeding the same
  `effects_stack`-comparison logic unchanged.
- **Shadowing is handled correctly, the same discipline v0.14.2/v0.14.3
  established**: every `let`/named-`fn`/parameter binding writes an
  explicit entry into ALL THREE stacks (even `None`) — an inner `let box =
  @{run: helper}` (non-effectful) correctly shadows an outer, effectful
  `box` of the same name; a parameter named `box` shadows an outer
  record-tracked `box` the same way a parameter already shadows an outer
  direct/return alias.
- **Deliberately narrower than it could be, by design, same mold as
  v0.14.3**: only a record built directly by a `let`-LITERAL is tracked —
  one returned from a call (even one whose own body tail-returns a literal
  record with an effectful field) is invisible; a record literal reached
  by a chain of hops (merged, copied, mutated) is likewise invisible. Only
  a BARE-NameRef field value is inspected within a tracked literal — a
  field whose value is itself a call (even one returning `print`) resolves
  to `None`, the same "one hop, no recursion" limit v0.14.3 applied to a
  fn's tail statement.
- **Still open, unaffected by this round**: passing a builtin as a
  FUNCTION ARGUMENT remains completely invisible — the one shape of
  v0.14.3's own three-way "still open" list (argument / return / container
  field) this round did not touch, correctly left open per
  `state/research-state.md`'s own reasoning for why it doesn't fit the
  same single-pass mold (a fn body is parsed once, independent of its call
  sites; the fact would need per-call-site specialization or an unsound
  over-approximation). The dynamic call graph is also still untouched —
  see `state/research-state.md`'s language backlog for why it's sized as
  multi-round-scale, not a quick follow-up.
- **Verification**: `tests/test_v14.py` 45/45 (was 37; 8 new tests: field
  call via record literal [checked + granted], a non-effectful field is
  not flagged, inner-record-of-same-name shadowing, param-name shadowing
  [with a real record passed at runtime], a non-literal binding is not
  tracked, a call-valued field is not tracked, one new three-way
  differential pin). `languages/whence/run_tests_fast.sh` 875 passed/38
  deselected (was 867; +8 matches the net new-test delta exactly, no other
  file's count moved).
- **Guest parity**: same reasoning as v0.14.2/v0.14.3, for the same
  underlying cause — `print` is in `harness/swe/guest.py`'s `BANNED`
  regex, so any guest-oracle fuzz program mentioning it anywhere is
  short-circuited to `parse_error` before either interpreter runs it; not
  something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2/v0.14.3, for the same
  reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits a record
  literal whose field value is a bare `print` NameRef — this round's own
  trigger shape is consequently exercised only by `tests/test_v14.py`'s
  hand-authored cases, not the differential fuzz corpus. Fixing it needs a
  new GENERATOR expression shape, not a checker change — named here so a
  future round doesn't rediscover it as a mystery.

## v0.14.5 (round 276) — effect system: IF/ELSE-tail value flow through a direct call

- **Closes the "if" half of v0.14.3's own documented gap**: a fn body
  whose TAIL STATEMENT is an `if`/`else` (any `else if` chain length),
  where EVERY arm resolves to the exact same effectful alias, is now
  tracked as a "return fact" the same way a bare-NameRef tail already was
  — `let get_printer = fn(cond) { if cond { print } else { print } }`
  then `let p = get_printer(true); p(1)` is now checked exactly as
  `let p = print; p(1)` (v0.14.2) would be. `test_return_tag_only_sees_a_
  bare_name_tail` (the test that pinned this as an honest, open gap since
  round 270) is replaced by
  `test_return_tag_sees_an_if_else_tail_when_both_arms_agree` and five
  companions covering the granted case, an `else if` chain, and two
  "one arm disagrees, stays untracked" cases.
- **Mechanism, and why it needed no new stack**: `Parser._if_tail_alias_
  tag(if_node)` is a purely STRUCTURAL, post-hoc walk — `if_node.then` is
  always an already-parsed `A.Block` (`block()` always returns one), and
  `if_node.otherwise` is either another already-parsed `A.Block` (a plain
  `else { ... }`) or an already-parsed `A.If` (an `else if ...` chain,
  recursed into). Each such child block ALREADY resolved its own
  `tail_alias_tag` correctly, via `stmt_list`, while ITS OWN `alias_
  scopes` frame was open (the exact same code path v0.14.3 uses for a
  bare-NameRef tail) — by the time the ENCLOSING `stmt_list` looks at its
  own tail (now possibly an `A.If`), those child facts are just plain
  already-computed field reads, no scope context needed, the same "no
  scope context needed" shape `mark_tails`'s own boolean structural walk
  already has. This is why the previous three rounds' "can't simply run
  after the fact" limitation (`stmt_list`'s own docstring, pre-v0.14.5)
  didn't actually block this specific shape once looked at carefully: the
  blocker was re-resolving a BARE NAME after its scope closed, not
  reading an ALREADY-RESOLVED per-block field.
- **Sound, not approximate, by construction**: `_if_tail_alias_tag`
  requires every arm's tag to be identical, not merely non-None — one
  arm resolving to a different tag, or to `None` (a plain value, or an
  untracked callable), makes the whole `if` resolve to `None`
  (`test_return_tag_if_else_tail_needs_every_arm_to_agree`,
  `test_return_tag_else_if_chain_one_mismatched_arm_is_not_tracked`). An
  "any arm matches" rule would be UNSOUND: a caller in an `effects [io]`
  scope could then reach a branch performing a real, undeclared effect
  without ever being flagged — exactly the kind of false-negative-that-
  looks-like-a-false-positive-fix this feature family has avoided at
  every step (v0.14.2's shadowing discipline, v0.14.4's exact-field-match
  requirement).
- **Still deliberately narrow**: the recursion only ever starts from the
  enclosing block's own TAIL statement — an `if` bound to a `let` first
  and referenced afterward is not inspected
  (`test_return_tag_only_sees_a_tail_if_else_not_a_deeper_nested_one`),
  matching the "one hop from the tail, no general data-flow" discipline
  v0.14.3/v0.14.4 already established. The two gaps v0.14.4 left fully
  open — passing a builtin as a FUNCTION ARGUMENT, and the dynamic call
  graph — are both still completely untouched by this round; neither fits
  the same single-pass, no-interprocedural-analysis mold this whole
  feature family relies on (see `state/research-state.md`'s language
  backlog for why both are sized as multi-round-scale work, not a quick
  follow-up).
- **Verification**: `tests/test_v14.py` 51/51 (was 45; net +6: one old
  test documenting the now-closed gap replaced by six new ones — both-
  arms-agree [checked + granted], an `else if` chain [checked + one-arm-
  mismatch-stays-untracked], one new three-way differential pin, and the
  "not from a non-tail position" boundary case).
  `languages/whence/run_tests_fast.sh` 880 passed/38 deselected (was 875;
  +5 is net-new across the whole suite, matching `test_v14.py`'s own net
  delta exactly — no other file's count moved). Full unfiltered
  `pytest tests/` also run this round (parser.py's `stmt_list` is on
  every block-parse path, not just effects-declared code) — no
  regressions.
- **Guest parity**: same reasoning as v0.14.2/v0.14.3/v0.14.4, for the
  same underlying cause — `print` is in `harness/swe/guest.py`'s
  `BANNED` regex, so any guest-oracle fuzz program mentioning it anywhere
  is short-circuited to `parse_error` before either interpreter runs it;
  not something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2/v0.14.3/v0.14.4, for the
  same reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits a fn
  body whose tail is an `if`/`else` with a bare `print` NameRef in every
  arm — this round's own trigger shape is exercised only by
  `tests/test_v14.py`'s hand-authored cases, not the differential fuzz
  corpus. Fixing it needs a new GENERATOR expression shape, not a checker
  change — named here so a future round doesn't rediscover it as a
  mystery (the fourth round in a row to note this same class of gap for
  its own new shape). **Closed by round 278/279's landed diff** (see
  round 278's own entry in `state/research-state.md`) — `ProgramGen` now
  covers this shape along with v0.14.3/v0.14.4's.

## v0.14.6 (round 282) — effect system: RETURN-value flow through a field call

- **Closes the specific slice of v0.14.4's own documented gap named but not
  touched**: "a field whose value is itself a call/alias chain is
  invisible" — closed here for the case where the field's bare-NameRef
  value is itself a return-carrier (a fn tracked, per v0.14.3, to
  tail-return an effectful alias). `let box = @{run: get_printer}` then
  `box.run()(1)` — TWO applications, the FIRST (`box.run()`) itself
  invoking whatever `get_printer` was tracked to return — is now checked
  exactly as `get_printer()(1)` (v0.14.3) would be. The mirror-image
  extension is exactly what its name suggests: v0.14.3 added a RETURN
  fact for bare names, v0.14.4 added a FIELD fact for direct aliases,
  this round adds the missing fourth combination, a FIELD fact for return
  aliases.
- **Mechanism**: `Parser.field_return_alias_scopes` — a FOURTH stack, the
  exact same shape and three push/pop sites as the other three
  (`stmt_list`, and both fn-parameter scopes). Built at the same `let
  name = @{...}` LITERAL site `field_alias_scopes` already inspects, from
  the SAME bare-NameRef field values, just resolved through
  `_resolve_effectful_return` instead of `_resolve_effectful_alias` — the
  two dicts are independent (a field can be a direct alias, a
  return-carrier, both, or neither;
  `test_field_return_chain_and_field_direct_alias_are_independent` pins
  this). `_resolve_effectful_field_return(name, field)` mirrors the other
  three resolvers exactly: innermost-first, first-frame-wins walk on
  `name`, then a plain `.get(field)` within the winning frame's dict.
- **`_check_effect_call` gained a fourth branch**: a callee that is a
  `Call` whose own `.fn` is a `FieldAccess` on a NameRef resolves through
  `_resolve_effectful_field_return` — sitting alongside the existing
  direct-name, chained-call-return, and direct-field branches, all four
  feeding the same `effects_stack`-comparison logic unchanged. The FIRST
  application (`box.run()` on its own) is still checked, separately and
  independently, by the pre-existing direct-field branch (v0.14.4) —
  `box.run` itself is not tracked as effectful here, only calling its
  result is.
- **Shadowing is handled correctly, the same discipline v0.14.2/v0.14.3/
  v0.14.4/v0.14.5 established**: every `let`/named-`fn`/parameter binding
  writes an explicit entry into ALL FOUR stacks (even `None`)
  (`test_inner_record_of_same_name_shadows_outer_field_return_alias`).
- **Still deliberately narrow, same mold as v0.14.4**: only a record
  built directly by a `let`-LITERAL is tracked
  (`test_field_return_chain_of_a_non_literal_binding_is_not_tracked`); a
  field value that resolves to `None` in `return_alias_scopes` (an
  ordinary, non-return-tracked fn) leaves the field-return fact at `None`
  too (`test_field_return_chain_field_value_that_is_not_a_return_carrier`).
  Passing a builtin as a FUNCTION ARGUMENT and the dynamic call graph
  remain completely untouched, unchanged from v0.14.4/v0.14.5's own
  "still open" notes — this round is a fourth combination of the SAME
  four building blocks (direct/return x bare-name/field), not a step
  toward either of those two genuinely multi-round-scale items.
- **Verification**: `tests/test_v14.py` 58/58 (was 51; 7 new tests: the
  chained-field-call check itself [checked + granted], independence from
  the direct-alias field dict, a non-return-carrier field value is not
  tracked, the non-literal-binding boundary, inner-record shadowing, one
  new three-way differential pin). `languages/whence/run_tests_fast.sh`
  888 passed/38 deselected (was 881 going into this round — round 278's
  fuzz-coverage diff, landed by round 279, had already moved the fast-tier
  count from 880 to 881 with zero `test_v14.py` tests of its own; +7 this
  round matches `test_v14.py`'s own net delta exactly). Full unfiltered
  `pytest tests/` also run this round (`parser.stmt_list`/`statement` sit
  on every block-parse path, not just effects-declared code) — see
  `knowledge/round-282-whence-v0146-effect-field-return-chain.md` for the
  exact count and any regressions found.
- **Guest parity**: same reasoning as v0.14.2/v0.14.3/v0.14.4/v0.14.5, for
  the same underlying cause — `print` is in `harness/swe/guest.py`'s
  `BANNED` regex, so any guest-oracle fuzz program mentioning it anywhere
  is short-circuited to `parse_error` before either interpreter runs it;
  not something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2/v0.14.3/v0.14.4/v0.14.5,
  for the same reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits
  a record literal whose field value is a bare-NameRef return-carrier —
  this round's own trigger shape is exercised only by
  `tests/test_v14.py`'s hand-authored cases, not the differential fuzz
  corpus. Named here so a future round doesn't rediscover it as a
  mystery, same as v0.14.2/v0.14.3/v0.14.4/v0.14.5 each did for their own
  new shape.

## v0.14.7 (round 288) — effect system: CONTAINER-FIELD value flow through a NESTED record literal

- **Closes the specific slice of v0.14.4's own documented gap named but not
  touched**: "a field whose value is itself a ... nested-record[/shape] is
  invisible" — closed here for the case where the OUTER field's value is
  itself another record literal, one level deeper than v0.14.4's own
  single-hop case. `let outer = @{box: @{run: print}}` then
  `outer.box.run(1)` — a TWO-FIELD access chain reaching all the way down
  to a bare-NameRef effectful alias — is now checked exactly as `box.run
  (1)` (v0.14.4) would be for a `box` bound directly by the enclosing
  `let`.
- **Mechanism**: `Parser.nested_field_alias_scopes` — a FIFTH stack, the
  exact same shape and three push/pop sites as the other four
  (`stmt_list`, and both fn-parameter scopes). Built at the same `let name
  = @{...}` LITERAL site `field_alias_scopes`/`field_return_alias_scopes`
  already inspect, but keyed only on fields whose OWN value is ANOTHER
  `A.RecordLit` — for each such field, the inner literal's own
  bare-NameRef fields are resolved through `_resolve_effectful_alias` the
  exact same way a top-level literal's fields already are, producing a
  dict-of-dicts: `{outer_field: {inner_field: tag-or-None}}`.
  `_resolve_effectful_field_nested(name, outer_field, inner_field)`
  mirrors the other four resolvers' innermost-first, first-frame-wins walk
  on `name`, then two chained `.get`s (each individually guarded against a
  missing or `None` intermediate result, the same way
  `_resolve_effectful_field`/`_resolve_effectful_field_return` guard their
  own single `.get`).
- **`_check_effect_call` gained a fifth branch**: a callee that is an
  `A.FieldAccess` whose own `.obj` is ITSELF an `A.FieldAccess` (rather
  than a bare NameRef, the shape v0.14.4's branch already covers) whose
  own `.obj` is a NameRef — i.e. the `outer.box.run` shape — resolves
  through `_resolve_effectful_field_nested`, sitting alongside the
  existing four branches, all five feeding the same `effects_stack`-
  comparison logic unchanged. This is a genuinely NEW branch, not a
  generalization of the existing field branch, because the existing
  branch's guard (`callee.obj.__class__ is A.NameRef`) is a class check —
  mutually exclusive with the new branch's guard by construction, so
  there is no ordering hazard between the two.
- **Shadowing is handled correctly, the same discipline v0.14.2/v0.14.3/
  v0.14.4/v0.14.5/v0.14.6 established**: every `let`/named-`fn`/parameter
  binding writes an explicit entry into ALL FIVE stacks (even `None`)
  (`test_inner_record_of_same_name_shadows_outer_nested_field_alias`,
  `test_param_named_like_outer_nested_field_alias_shadows_it`).
- **Still deliberately narrow, same mold as v0.14.4/v0.14.6, and does NOT
  generalize to arbitrary depth**: only an OUTER record built directly by
  a `let`-LITERAL is tracked
  (`test_nested_field_of_a_non_literal_outer_binding_is_not_tracked`); the
  nesting stops at exactly ONE additional hop — a THIRD level
  (`a.b.c.run(...)`) is not tracked by this stack at all, the callee shape
  simply does not match the new branch's guard (`callee.obj.obj.__class__
  is A.NameRef` requires the chain to bottom out in a bare name exactly
  two `.field` hops up). A middle field whose value was never itself a
  record literal correctly leaves the chain untracked
  (`test_nested_field_where_middle_field_is_not_itself_a_record_literal`);
  an inner field whose value is itself a call is also untracked, the same
  "bare NameRef only" rule every level of this family applies
  (`test_nested_field_value_that_is_itself_a_call_is_not_tracked`).
  Passing a builtin as a FUNCTION ARGUMENT and the dynamic call graph
  remain completely untouched, unchanged from v0.14.4/v0.14.5/v0.14.6's
  own "still open" notes — this round is a deeper nesting of an EXISTING
  building block (container fields), not a step toward either of those
  two genuinely multi-round-scale items.
- **Verification**: `tests/test_v14.py` 67/67 (was 58; 9 new tests: the
  nested-field call itself [checked + granted], a non-effectful nested
  field is not flagged, inner-record shadowing at the outer name, param-
  name shadowing [with a real nested record passed at runtime], the
  non-literal-outer-binding boundary, the middle-field-not-a-literal
  boundary, a call-valued inner field is not tracked, one new three-way
  differential pin). `languages/whence/run_tests_fast.sh` 897 passed/38
  deselected (was 888; +9 matches `test_v14.py`'s own net delta exactly,
  no other file's count moved). Full unfiltered `pytest tests/` also run
  this round (`parser.stmt_list`/`statement` sit on every block-parse
  path, not just effects-declared code): **935 passed in 382.40s**, zero
  regressions.
- **Guest parity**: same reasoning as v0.14.2 through v0.14.6, for the
  same underlying cause — `print` is in `harness/swe/guest.py`'s `BANNED`
  regex, so any guest-oracle fuzz program mentioning it anywhere is
  short-circuited to `parse_error` before either interpreter runs it; not
  something this round needed to re-verify.
- **Fuzz coverage — same honest gap as v0.14.2 through v0.14.6, for the
  same reason**: `harness/swe/fuzz.py`'s `ProgramGen` never emits a record
  literal whose field value is itself ANOTHER record literal at all (let
  alone one with a bare-NameRef `print` field nested inside it) — this
  round's own trigger shape is exercised only by `tests/test_v14.py`'s
  hand-authored cases, not the differential fuzz corpus. Fixing it needs a
  new GENERATOR expression shape (a nested `@{...}` as a field value), not
  a checker change — named here so a future round doesn't rediscover it as
  a mystery, same as every prior round in this family. `harness/swe/
  alias_effects.py`'s `ExtendedEffectGen` (round 281/287's independent
  parse-time-VERDICT oracle) also does not yet cover this shape — a
  natural next SWE-loop(D) round, same size/shape as round 287's own
  v0.14.6 extension.

## v0.14.8 (round 294) — effect system: the second effectful builtin, `rand`
- **Every alias-tracking round from v0.14.2 through v0.14.7 exercised
  `_EFFECTFUL_BUILTINS` (`parser.py`) with exactly ONE real entry**
  (`print`/"io"); the "per-tag, not merely was-a-clause-present" property
  (`test_effects_unrelated_tag_still_blocks_print`) was only ever pinned
  against a hypothetical, unused tag name ("network"), never a second REAL
  capability. Round 293's own next-steps explicitly named the choice this
  round faced: the two genuinely multi-round-scale alias-tracking gaps
  (builtin-as-argument, dynamic call graph) are "unchanged in scope-
  assessment since round 270, still correctly not attempted piecemeal", so
  any further extension to the effect-alias family should be "a genuinely
  new Whence language feature (v0.14.8+)... unless one turns up during
  normal spec review". A normal spec review of `parser.py`'s own v0.14
  design comment turned exactly that up: "`_EFFECTFUL_BUILTINS = {"print":
  "io"}` is the one place a future effectful builtin (randomness, a clock,
  real I/O) would register its tag; nothing else would need to change" —
  an anticipated extension point, sitting unclaimed since round 146.
- **`rand()` (arity 0) draws a float in `[0.0, 1.0)`** from the
  `Interpreter`'s own `random.Random` instance, tagged `"random"` (distinct
  from `print`'s `"io"`) in `_EFFECTFUL_BUILTINS = {"print": "io", "rand":
  "random"}`. Built as a `leaf` node (no input provenance, exactly like a
  literal) — `whence/interp.py`'s `b_rand`.
- **The one real design decision this round makes, and the reason it took
  real thought rather than being a one-line addition**: an actually-
  nondeterministic builtin is fundamentally at odds with THREE existing,
  load-bearing pieces of this project's own testing methodology — the
  three-way differential (`assert_three_way`, three SEPARATE `Interpreter`
  instances for direct/fast/slow that must agree byte-for-byte on
  `render_why`), the guest/host oracle campaigns, and `bench/ref_diff.py`'s
  reference comparison — all of which assume a Whence PROGRAM's behavior
  is a pure function of its source text. **Resolution: `rand()` is
  reproducible, not unpredictable.** `Interpreter.__init__` gained a
  `seed=0` parameter; `self._rng = random.Random(seed)` is a per-instance
  stream, not process-global entropy. Two fresh `Interpreter()` instances
  (the default seed, 0, unless overridden) draw the IDENTICAL sequence
  (`test_rand_is_deterministic_for_the_default_seed`), so the three-way
  differential's three independently-constructed interpreters agree on
  `rand()`'s value exactly as they already agree on everything else
  (`test_three_way_rand_matches_across_direct_fast_slow`) — no special-
  casing needed anywhere in the differential harness itself. This is a
  genuine departure from mainstream languages (most seed `random()` from OS
  entropy by default, favoring unpredictability); Whence favors
  reproducibility instead, the same value judgment sandboxed/deterministic-
  replay execution environments make, and the only value judgment under
  which "randomness" and "the entire test suite assumes determinism" can
  coexist without a special case. `run.py` gained a `--seed N` CLI flag
  (default 0) so a real user CAN vary the stream deliberately; the REPL and
  every existing embedder that doesn't pass `seed=` keep the reproducible
  default unchanged.
- **Confirms the v0.14 design comment's own claim literally true**: adding
  the second entry to `_EFFECTFUL_BUILTINS` needed ZERO other code changes
  — `_check_effect_call` and every `_resolve_effectful_alias`/`_resolve_
  effectful_return`/`_resolve_effectful_field`/`_resolve_effectful_field_
  return`/`_resolve_effectful_field_nested` helper (v0.14.2 through
  v0.14.7) already operate purely on the tag a name resolves to, generic
  since the day each was written. `test_aliased_rand_is_checked_same_as_
  aliased_print` exercises this live: `let r = rand; effects [] { r() }`
  is rejected, `effects [random] { let r = rand; r() }` is granted, through
  the SAME `_resolve_effectful_alias` v0.14.2 wrote for `print`.
- **Per-tag distinctness, now proven with two real capabilities, not one
  real + one hypothetical**: `effects [io]` does not grant `"random"` (so
  `rand()` is still rejected), and `effects [random]` does not grant
  `"io"` back (so `print(...)` is still rejected) — `test_effects_random_
  tag_is_independent_of_io_tag`, the two-real-tag mirror of `test_effects_
  unrelated_tag_still_blocks_print`. `effects [io, random]` grants both
  (`test_effects_io_and_random_together_allow_both`).
- **`examples/effects.lang` gained two checks** (7 → 9) demonstrating the
  unrestricted top-level case and `effects [random]` granting the new tag
  — no rejected-case example, the same reason v0.14's own file gives none
  (a `ParseError` aborts the whole file before any `check` runs; the
  rejection paths are pinned by `tests/test_v14.py` instead).
- **Verification**: `tests/test_v14.py` 78/78 (was 67; 11 new tests: return-
  type/arity/determinism/seed-argument for `rand` itself, the empty-scope
  rejection, the granting case, the two-real-tag independence check in
  BOTH directions, the io+random-together case, the aliased-`rand` reuse
  check, one new three-way differential pin). `languages/whence/
  run_tests_fast.sh` 908 passed/38 deselected (was 897; +11 matches
  exactly, no other file's count moved). `bash harness/run_tests_fast.sh`
  (the unrelated SWE-loop(D) track's own suite, run as a cross-track
  regression check since this round touches `parser.py`/`interp.py`
  neither alias_effects.py nor fuzz.py inspect directly) — **403 passed,
  196 deselected, byte-identical to round 293's own baseline**.
- **Guest parity — NOT done this round, by design, matching every prior
  v0.14.x feature's own arc** (v0.14 itself landed round 146, guest parity
  round 164; v0.14.1 round 264 still has no guest-side inheritance change
  needed since the guest never enforced `effects [...]` at all): `self_
  eval.lang`'s own `builtin_names` list has no entry for `rand` yet, so a
  guest program calling it fails at NAME RESOLUTION, the same gap class
  rounds 206 (`steps`)/218 (`at`/`blame`/`diverge`/`contrast`)/224
  (`matches`/`shapeof`) each found and fixed for their own builtin.
  `tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed` updated to expect exactly `rand`'s own two new
  checks failing under the guest (an unbound-name miss propagates through
  both), every pre-existing check unaffected — the file still parses
  cleanly (a bare `rand()` call is an ordinary `Call` node to the guest
  parser, no different from any other name).
- **Fuzz/oracle coverage — also NOT done this round, same reasoning**:
  `harness/swe/fuzz.py`'s `ProgramGen` and `harness/swe/alias_effects.py`'s
  `ExtendedEffectGen` both only know about `print`; teaching either
  generator that `rand` is a second effectful builtin (and, for the fuzzer,
  that `harness/swe/guest.py`'s `BANNED` line-filter needs a second entry so
  guest-differential campaigns keep vacuously satisfying declarations the
  same way they do for `print`) is future SWE-loop(D) work, not this
  round's (language(C)'s) own scope — the same track split every prior
  v0.14.x feature has followed.

### `rand` guest parity (round 296)
- **Closes the gap the section above named**: `examples/self_eval.lang`'s
  `builtin_names` gained a `"rand"` entry (after `"print"`, its fellow
  effectful builtin) and its `arities` record gained `rand: 0` — the
  guest's first-ever arity-0 builtin. `apply_builtin`'s own arity check
  (`if ar == -1 {...} else {len(args) == ar}`) already handles 0 with no
  change; a 0-arg call's `args` list is simply `[]`.
  `apply_host_builtin(name, args)` dispatches `"rand"` to the real host
  `rand()` builtin directly (`else if name == "rand" { rand() }`, next to
  `"print"`'s own branch) rather than reimplementing a draw in guest code.
- **Why calling the real builtin gives correct VALUE parity, not just
  correct SHAPE**: `self_eval.lang` is itself Whence source, executed by
  an outer `Interpreter`. When it calls `rand()` to service a guest
  program's own `rand()` call, that draws from the SAME outer
  interpreter's seeded `_rng` a fully direct (non-guest) evaluation of the
  identical program would use — since `self_eval.lang`'s own code never
  calls `rand()` except in this one dispatch branch, each guest-level
  `rand()` call consumes exactly one draw, in the same order the guest
  program makes them, so guest and direct-host evaluation agree exactly
  given the same seed. No special-casing needed anywhere in the guest
  evaluator, the same "operate purely on values, oblivious to where they
  came from" property that let the parser-side `_EFFECTFUL_BUILTINS`
  extension (above) need zero other code changes.
- **Node shape parity is automatic, not hand-mirrored**: `rand`'s host
  node (`interp.py`'s `b_rand`) is `leaf("rand", "", line, value)` — op
  `"rand"`, empty detail, no inputs. `apply_builtin`'s existing catch-all
  branch (the `else` after every named special case) already produces
  exactly that shape for any builtin absent from `propagating`/the
  node-shape-override list: `o = name` (not `"builtin"`, since `rand` is
  correctly NOT added to `propagating` — arity 0 means there is nothing to
  propagate from) and `ins2 = args` (`[]`). No new special-case branch was
  needed in `apply_builtin` itself, only in `apply_host_builtin`'s
  dispatch table.
- **`tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed`** updated: `examples/effects.lang`'s all 9
  checks (including both of `rand`'s own) now pass under the guest, where
  round 294 pinned exactly those 2 as the expected failures. Verified
  directly with `python3 run.py examples/effects.lang` (host) and via the
  guest harness (`Interpreter().run(eval_lib + run_src(effects_src))`) —
  both report `checks: 9 passed, 0 failed`.
- **Verification**: `pytest tests/test_self_hosting.py -q` → **15 passed**
  (no count change — this fixed an existing test's assertion, added none).
  `bash run_tests_fast.sh` → **908 passed, 38 deselected**, byte-identical
  to round 294's own post-`rand`-landing baseline (this round touches only
  `examples/self_eval.lang` and one test file, no interpreter code).
  Unfiltered `pytest tests/` → **946 passed**. `bench/ref_diff.py
  --counters examples/*.lang` (working tree `whence/` package vs git HEAD)
  → every file, including `effects.lang` (`bindings=12 checks=9 out=11`),
  `SAME` across direct/fast/slow — expected, since this round's diff is
  entirely inside `self_eval.lang`, never `whence/*.py`, so the reference
  differential (which only compares the Python package) has nothing to
  disagree about; run anyway as the standing cross-check this project's
  language(C) rounds always include. Cross-track regression check: `bash
  harness/run_tests_fast.sh` → **403 passed, 199 deselected** (round 295's
  own `GuestHarness`/`harness_for` `max_depth` fix, reconciled the same
  round this work landed, moved the deselected count from 196; unaffected
  by this round's own change).
- **Still open, unchanged in scope from the section above**: fuzz coverage
  (`harness/swe/fuzz.py`'s `ProgramGen`, + a `BANNED` second entry in
  `harness/swe/guest.py`) and `ExtendedEffectGen` oracle coverage for
  `rand` — SWE-loop(D)'s own next round, same shape as the v0.14.2-
  v0.14.7 arc but for a genuinely new builtin. **Closed by round 299**
  (`harness/swe/fuzz.py`, `harness/swe/alias_effects.py`,
  `harness/swe/guest.py`) — see that round's own `research-state.md` entry.

## v0.14.9 (round 300) — effect system: the NAMED-fn slice of value flow through a function ARGUMENT
- **The two remaining effect-system gaps, unchanged in scope-assessment
  since round 270** (SPEC.md's own v0.14/v0.14.4/v0.14.7/`tests/
  test_v14.py`'s module docstring, repeatedly reaffirmed through round
  298's `research-state.md` next-steps): (a) value flow through a function
  ARGUMENT, (b) the dynamic call graph (calling a different, unrestricted
  top-level fn that itself performs the effect). Both were explicitly
  flagged as needing a real design decision — "per-call-site
  specialization or an unsound over-approximation... not just more
  lexical-scope bookkeeping" (round 270's own words) — before any future
  round should attempt more than a design sketch. This round picks (a)
  apart rather than attempting it whole: within it, a NAMED fn (`fn
  NAME(...) {...}`) calling one of its OWN parameters directly is a
  narrower, cleanly-scoped sub-problem than the general case (an anonymous
  `fn(...) {...}` bound by `let`, or a param merely stored/returned/passed
  further along), and is exactly the "one hop past the existing frontier"
  shape every prior v0.14.x round has used to make forward progress
  without attempting the full, genuinely multi-round-scale feature in one
  sitting.
- **Design**: unlike every sibling `_resolve_effectful_*` (each answers
  "does THIS NAME carry an effect fact", decidable once, at its own
  binding site), whether `fn apply(f) effects [io] { f(1) }` is sound to
  call as `apply(print)` depends on the SPECIFIC ARGUMENT at each call
  site — `apply`'s own body, parsed exactly once, independent of any call
  site, never learns what `f` actually is. The check therefore cannot live
  where every other v0.14.x check lives (inside the callee's own body
  parsing); it has to run at each CALL SITE instead, against a fact
  recorded ONCE, when `apply` itself was defined: which of its own params
  it calls directly, and under what `effects [...]` scope. New machinery,
  `whence/parser.py`:
  - **`Parser.param_call_scopes`**: a SIXTH stack, same per-block-frame
    shape and push/pop sites as the other five (`alias_scopes` and
    friends). Maps a NAMED fn's name to `None` (calls none of its own
    params directly) or `(effects_scope, params_tuple,
    frozenset_of_directly_called_param_names)`, recorded once its body
    finishes parsing — the exact same place `return_alias_scopes[-1][name]
    = body.tail_alias_tag` already records the v0.14.3 return fact.
  - **`Parser.current_fn_params_frame_stack` / `direct_param_calls_stack`**:
    transient (NOT scope-shaped) bookkeeping, live only while a single
    fn's own body is being parsed, accumulating which of ITS OWN params
    are seen as a direct call target (`f(...)`) anywhere in the body, at
    any nesting depth. Correctness of SHADOWING (a nested block's own
    `let`/`fn`/param of the same name must NOT be misattributed to the
    outer fn's own parameter) comes from an IDENTITY comparison: the exact
    dict object pushed for the fn's own params frame is captured once and
    compared, by `is`, against whatever frame an innermost-first walk of
    `alias_scopes` actually resolves the callee name through
    (`_innermost_frame_containing`) — if a closer frame wins, it is not
    this fn's own parameter, full stop.
  - **`Parser._check_call_site_param_effects`**: runs at every call
    expression (`postfix()`, alongside `_check_effect_call`), looks up the
    callee's recorded param-call fact (`_resolve_param_call_fact`, the
    same innermost-first walk every sibling resolver uses), and for each
    argument landing in a directly-called parameter slot, checks it —
    against the CALLEE's own recorded effects scope, not the caller's
    (the callee's body, not the call site, is what actually performs the
    effect).
- **Deliberately narrow, the same discipline every v0.14.x round before
  it used**: only a NAMED fn is tracked (an anonymous `fn(...) {...}`
  bound by `let` has no name yet at the point its own param-call fact
  would need to be recorded under — would need a new `A.FnExpr` AST field
  to carry the fact forward, the same way `body.tail_alias_tag` already
  rides on `A.Block`, deliberately out of scope this round); only a
  parameter called DIRECTLY (`f(...)`) is tracked, not one merely stored,
  returned, or passed on to a THIRD function; only a bare-NameRef argument
  at the call site is inspected, the same "bare-NameRef only" boundary
  every sibling resolver already has; forward-referenced or mutually-
  recursive fns are invisible, same single left-to-right parse pass as
  everything else in this family.
- **Zero interpreter changes, zero new AST nodes** — entirely parse-time,
  same as every v0.14.x feature before it.
- **Verification**: `tests/test_v14.py` 78 → **92 passed** (14 new:
  the basic grant/reject pair, the no-clause-unrestricted case, the
  `random` tag mirror, a non-effectful argument, "stored not called" is
  not a false positive, only the directly-called param position is
  checked (not a sibling param), a non-NameRef argument is invisible, the
  anonymous-`let`-bound-fn boundary, inner-fn-same-param-name shadowing in
  both directions, the callee's-own-scope-not-the-caller's distinction,
  a too-few-args guard, a plain rename carries the fact forward, and a
  parameter shadowing an earlier-tracked fn name). `run_tests_fast.sh`:
  **908 passed, 38 deselected**, byte-identical to round 296's own
  baseline (this round adds new tests but no new runtime-reachable code
  path any pre-existing fast-tier test would exercise). Full unfiltered
  `pytest tests/` run in the background per the round-227 convention.
  Cross-track regression: `bash harness/run_tests_fast.sh` unaffected
  (this round touches only `languages/whence/`, confirmed via `git status`
  before starting).
- **Still open, unchanged from every prior round's own assessment**: an
  argument reaching an effectful builtin through a SECOND function call
  before landing in a directly-called param; a builtin flowing into a
  param that is stored/returned rather than called directly; the
  anonymous-fn-bound-by-`let` slice of even the NAMED-fn shape this round
  closes; and the dynamic call graph (b), completely untouched. Fuzz
  coverage (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for this new shape are open, the same
  "ship the checker, name the fuzz gap, close it in a later dedicated
  round" rhythm every v0.14.x feature has followed.

## v0.14.10 (round 302) — effect system: the anonymous-fn-bound-by-`let` slice of value flow through a function ARGUMENT
- **Closes v0.14.9's own explicitly-named remaining slice** ("only a NAMED
  fn is tracked... would need a new `A.FnExpr` AST field to carry the fact
  forward, the same way `body.tail_alias_tag` already rides on `A.Block`,
  deliberately out of scope this round" — v0.14.9's own words, unchanged
  through round 301's next-steps): `let g = fn(f) effects [io] { f(1) }`
  then `g(print)` is now checked, exactly as if `g` were a NAMED fn.
- **Design**: `Parser.primary()`'s `fn(...) {...}` branch already pushes
  and pops the same `current_fn_params_frame_stack`/`direct_param_calls_
  stack` bookkeeping the NAMED-fn branch uses (needed regardless, for
  shadowing/tracking consistency of anything declared INSIDE the anonymous
  fn's own body) — but through v0.14.9, the popped `called_params` set at
  that site was simply discarded, because there was no NAME yet to key
  `Parser.param_call_scopes` by while the anonymous fn's own params/body
  were being parsed. v0.14.10 does exactly what v0.14.9's own text
  predicted: a new `A.FnExpr` field, `param_call_fact` — `None`, or
  `(effects_scope, params_tuple, frozenset_of_directly_called_param_
  names)`, the identical shape `param_call_scopes` already stores for a
  NAMED fn — set once, right before the `A.FnExpr` node is constructed,
  the same way `A.Block.tail_alias_tag` is already set once `stmt_list`
  finishes resolving a block's own tail (v0.14.3). `statement()`'s own
  `let` handling (the `expr.__class__ is A.FnExpr` branch) then does the
  one thing v0.14.9 left as a placeholder: `self.param_call_scopes[-1][name]
  = expr.param_call_fact` instead of unconditionally `None` — the first
  point anywhere a NAME exists to key the fact by. `_check_call_site_param_
  effects` and `_resolve_param_call_fact` themselves needed **zero
  changes** — both already resolve through `param_call_scopes` generically,
  via the same innermost-first scope-stack walk every sibling resolver in
  this family uses, indifferent to whether a given frame's fact originated
  from a NAMED fn's own definition or a `let`-bound anonymous one.
- **`A.FnExpr` gains a new field, `param_call_fact`** — the ONLY AST
  change this round makes (still zero interpreter changes, zero new node
  TYPES): `whence/interp.py`'s `eval_FnExpr` reads `node.params`/
  `node.body`/`node.ret_type` by name already, so the new field is inert
  to it, and `A.FnExpr` has exactly one construction site in the codebase
  (`primary()`'s own `fn(...) {...}` branch), so updating its call needed
  no downstream ripple.
- **Deliberately still narrow**, unchanged from v0.14.9's own remaining
  boundaries: only a parameter called DIRECTLY (`f(...)`) is tracked, not
  one merely stored, returned, or passed to a THIRD function; only a
  bare-NameRef argument at the call site is inspected; forward-referenced
  or mutually-recursive fns are invisible; a fn expression used any way
  OTHER than `let NAME = fn(...) {...}` — called immediately without ever
  being bound to a name, passed straight through as someone else's
  argument, stored directly in a container/record field without an
  intervening `let` — still has no name to key `param_call_scopes` by and
  remains untracked. This is not a new gap: it is the same "nothing to
  check without SOME name" boundary this whole family has always had (a
  bare builtin passed inline, `total(fn(x){x})`, was never checkable
  either, for the identical reason).
- **Verification**: `tests/test_v14.py` 92 → **95 passed** (3 new: the
  basic grant/reject pair for a `let`-bound anonymous fn — inverting what
  had been `test_anon_fn_bound_by_let_param_call_is_not_tracked` into
  `test_anon_fn_bound_by_let_param_call_is_now_checked` — plus the
  no-clause-unrestricted case, the fact carrying forward through a plain
  rename, and shadowing by a same-named parameter).
  `examples/effects.lang` gained one new demo (`apply_logger_anon`, the
  `let`-bound mirror of v0.14.9's `apply_logger`): checks 10 → **11
  passed, 0 failed**. `tests/test_examples.py::test_effects` and `tests/
  test_self_hosting.py`'s guest-parity pin both updated to 11 checks — the
  guest needed **zero code change**, confirming the same "purely a host
  parse-time field, invisible to the guest evaluator" property v0.14.9
  already established (`self_eval.lang` builds its own record-shaped AST
  nodes entirely independently of the host's `whence/ast_nodes.py`, so a
  new host-only field on `A.FnExpr` is simply never visible to it).
  `run_tests_fast.sh`: 922 → **925 passed, 38 deselected** (+3 exact).
- **Still open, unchanged from v0.14.9's own remaining assessment**: an
  argument reaching an effectful builtin through a SECOND function call
  before landing in a directly-called param; a builtin flowing into a
  param that is stored/returned rather than called directly; the dynamic
  call graph (calling a different, unrestricted top-level fn that itself
  performs the effect), completely untouched. Fuzz coverage
  (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for the v0.14.9/v0.14.10
  argument-flow shape overall remain open, the same "ship the checker,
  name the fuzz gap, close it in a later dedicated round" rhythm every
  v0.14.x feature has followed. **Closed by round 305 (landed by round
  306) — see below.**

## v0.14.11 (round 306) — effect system: a param renamed inside its own fn body, then called through the rename

- **Closes HALF of v0.14.9's own explicitly-named remaining gap** ("a
  builtin flowing into a param that is stored... rather than called
  directly", unchanged through v0.14.10's own next-steps): `fn apply(f)
  effects [io] { let g = f\n g(1) }` then `apply(print)` is now checked
  exactly as `f(1)` itself already was — including through any number of
  further rename hops within the SAME open fn body (`let h = g` then
  `h(1)` too). The OTHER half of that gap — a param RETURNED to a
  caller, who then holds and calls the alias itself, rather than the
  fn's own body calling it — is a genuinely different, still fully open
  value-flow-ACROSS-A-RETURN-BOUNDARY mechanism (see the negative case in
  `tests/test_v14.py`'s `test_param_returned_then_called_by_caller_is_
  still_not_checked`).
- **Design**: a new, SEVENTH scope-stack, `Parser.param_alias_scopes`,
  pushed/popped at the identical three sites `param_call_scopes` already
  is (`stmt_list`'s per-block frame, plus the params-frame push at each
  of the two fn-definition sites). Each frame maps a name to either
  `None` or the ORIGINAL PARAM NAME (a key of `current_fn_params_frame_
  stack[-1]`) it is currently a pure `let`-rename of — set by a new
  branch in `statement()`'s own `let` handling (the existing `expr.
  __class__ is A.NameRef` rename branch): if the RHS resolves, by
  identity, to the currently-open fn's own params frame, record the RHS
  name directly; otherwise recurse through the new `_resolve_param_alias`
  resolver, so a rename-of-a-rename chains automatically. A new fallback
  in `_check_effect_call`'s own existing v0.14.9 tracking step — reached
  only when the EXISTING identity check (the base case, `f(1)` itself)
  finds no match — calls `_resolve_param_alias(callee.name)` and, if it
  resolves, records the ORIGINAL param name (not the rename) into
  `direct_param_calls_stack`, so `_check_call_site_param_effects`'s later
  per-call-site check sees no difference between calling `f` directly and
  calling it through any number of renames. **Zero AST changes** — unlike
  v0.14.10's own `A.FnExpr.param_call_fact` field, this is pure parser
  scope-stack bookkeeping, exactly like v0.14.9's own original mechanism.
- **The one genuine correctness subtlety this design had to get right**:
  `_resolve_param_alias` must never cross a FN-BODY boundary — a rename
  recorded in an ENCLOSING fn's own scope must not leak into a DIFFERENT,
  inner fn's own param-call fact, even via a coincidental name collision
  (`fn outer(p) { let g = p\n fn inner(g) effects [io] { g(1) } }` must
  check `inner`'s call against `inner`'s OWN param `g`, and must NOT
  spuriously attribute it to `outer`'s unrelated `p`, which isn't even
  one of `inner`'s own params). Fixed by locating `current_fn_params_
  frame_stack[-1]`'s own identity inside `alias_scopes` and bounding the
  `param_alias_scopes` walk to that index and everything pushed after it
  — pinned by `test_param_rename_in_enclosing_fn_not_misattributed_to_
  inner_fn`.
- **Deliberately still narrow**, same family discipline: only a rename
  WITHIN THE SAME OPEN FN BODY is tracked (a rename inside a nested
  block still counts, since `param_alias_scopes` is pushed/popped at the
  same per-block granularity as every sibling stack); a RETURNED param is
  still invisible (see above); an argument reaching an effectful builtin
  through a SECOND function call, and the dynamic call graph (calling a
  different, unrestricted top-level fn that itself performs the effect),
  remain completely untouched, unchanged in scope from every prior
  v0.14.x round's own assessment.
- **Verification**: `tests/test_v14.py` 95 → **100 passed** (5 new: the
  basic grant/reject pair, a two-hop rename chain, a nested-block
  shadowing case, the cross-fn-boundary misattribution guard, and the
  explicit negative case pinning the still-open "returned" half).
  `examples/effects.lang` gained one new demo (`apply_logger_renamed`):
  checks 11 → **12 passed, 0 failed**. `tests/test_examples.py::
  test_effects` and `tests/test_self_hosting.py`'s guest-parity pin both
  updated to 12 checks — the guest needed **zero code change**, the same
  "purely a host parse-time mechanism, invisible to the guest evaluator"
  property v0.14.9/v0.14.10 already established, this time even more
  directly since there is no new AST field at all to be inert to.
  `run_tests_fast.sh`: 925 → **930 passed, 38 deselected** (+5 exact).
  `pytest tests/test_examples.py tests/test_self_hosting.py`: 34 passed.
- **Still open**: everything named above under "deliberately still
  narrow"; fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage
  (`harness/swe/alias_effects.py`) for this round's own new rename-chain
  shape specifically (round 305's fuzz/oracle work, landed alongside this
  round, covers only the v0.14.9/v0.14.10 direct-call shapes, not this
  round's rename extension) — the natural next SWE-loop(D) round, same
  "ship the checker, name the fuzz gap, close it later" rhythm.

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
- **Round 194 fixed a guest parity bug the round-176 work above shipped**,
  found by the why-shape differential fuzzer (seed 9205): `sure([], 0.0)` —
  a plain, non-Guess value, threshold irrelevant — diverged, guest op
  `literal` vs host ops `{let, list}`. The host's `sure` (`b_sure`) is a
  PASS-THROUGH when its value was never a Guess ("already certain: `sure`
  is a no-op escape hatch") — no new provenance node at all, so `let v =
  sure([], 0.0)` derives exactly the same two nodes as `let v = []`. Before
  this fix `sure` fell to `apply_builtin`'s generic catch-all, which always
  synthesizes a fresh "sure" box regardless of whether the host did.
  `sure` moved out of the generic `guess`/`is_guess`/`confidence`/`sure`
  delegation group (that group's own no-closure-guard comment was corrected
  accordingly) into its own `apply_builtin` branch with an explicit
  pass-through case, mirroring `typed`'s existing shape. The Guess-ABOVE-
  threshold pass-through case (unwraps to `g.node` on the host) was left
  NOT special-cased at the time — no fuzzer finding on that path yet, and
  a Guess arriving already-flattened (re-guessed, or threaded through a
  function parameter) has no local guest box to point at.
- **Round 234 closed that gap, plus a second one found alongside it, by
  direct construction rather than waiting on the fuzzer**: `sure`/`guess`
  are absent from `harness/swe/guest.py`'s `WHY_VOCAB`, and the ops the
  old code DID leak that are in that vocabulary (`literal`) already
  legitimately appear elsewhere in the host derivation — so the
  differential fuzzer's containment-only probe could never have caught
  either gap regardless of run count, a real, now-understood blind spot
  in the probe design, not bad luck. Fixed:
  - **below threshold**: host `mk_miss(..., inputs=(v,))` keeps only the
    VALUE's own derivation, never the threshold's; the old guest code
    wrapped with both, one spurious extra `literal` leaf every time.
  - **above threshold**: new `unwrap_guess_box` (`self_eval.lang`, next
    to `is_guess_val`) reconstructs the box for `g.node` purely from
    guest box structure — no new host accessor needed. It walks
    single-input wrapper boxes (`let NAME`/`arg NAME`/a plain `call`
    result all thread their one real value through unchanged) down to
    the box whose op is literally `"guess"`, takes ITS first argument
    (exactly what `b_guess` stored as `.node`), and repeats if that
    argument is itself still a Guess (mirrors `b_guess`'s own
    guess-of-guess flattening). A box with more than one `ins` element
    (a real `call`/`if`/tail-loop merge) falls back to returning the box
    unchanged — the same imperfect-but-safe behaviour this file used
    everywhere before this round, not a new failure mode.
  - Verified with a stronger check than containment: exact op-LIST
    equality (not just "no guest-only tokens") across six shapes — direct
    above/below threshold, a `let`-chain, a function-parameter hop (both
    above and below threshold), and guess-of-guess flattening — all six
    match host and guest token-for-token
    (`test_guest_sure_why_shape_matches_host_exactly_including_flattening`,
    `tests/test_self_hosting.py`). See `knowledge/round-234-whence-guest-sure-why-shape-parity-and-spec-staleness.md`.
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
- **Round 251's guest-targeted campaign (seed 1940) found a fresh gap in the
  same why-shape family, and round 252 closed it (plus a sibling it
  exposed)**: `binop`/`_unary`'s host-side Guess handling
  (`Interpreter._guess_binop`/`_unary`, `whence/interp.py`) is ASYMMETRIC —
  a Guess operand that makes the op SUCCEED keeps the ORIGINAL operand
  node(s) as the result's inputs (the outer "guess"-labelled node
  included), but a Guess operand that makes the op MISS (ordering a Guess
  against an incompatible type, dividing by zero, negating a Guess-wrapped
  string, `not` on a Guess-wrapped number, …) uses whatever the plain
  op-without-Guess-handling built from the Guess's UNWRAPPED inner node
  (`Guess.node`) instead — the outer "guess" node is silently dropped, so
  the host's own why-tree for that miss never mentions "guess" at all.
  `self_eval.lang`'s `apply_binop`/`eval_unary` boxed their inputs
  uniformly (`mkb(p, op, [a, b])` / `mkb(p, op, [r.v])`) regardless of this
  asymmetry, leaking a "guess" op into the guest's why-tree for a
  miss that the host's real derivation never has. Fixed with a shared
  `guess_unwrap_if_missed(a, p)` helper (reusing `sure()`'s own
  `unwrap_guess_box`, round 234) applied per-operand, but ONLY when the
  result missed — a succeeding Guess propagation keeps the original box(es)
  unchanged, matching the host's success path exactly. The unary half
  (`-`/`not` on a Guess) was never fuzzed (the differential generator's
  grammar has no unary-on-Guess template) and was found by checking the
  sibling code path for the same bug class once the binop finding was
  root-caused, not by a fresh campaign finding. Verified with exact op-LIST
  equality (not just containment) across 9 shapes: `>` miss with the Guess
  on either side, guess-of-guess ordering miss, divide-by-zero miss, a
  success control (original boxes kept), unary `-` on a Guess-string miss,
  unary `not` on a Guess-num miss, and two unary success controls
  (`test_guest_binop_guess_operand_miss_why_shape_matches_host_exactly`,
  `test_guest_unary_guess_operand_miss_why_shape_matches_host_exactly`,
  `tests/test_self_hosting.py`). See
  `knowledge/round-252-whence-guess-binop-unary-why-shape-parity.md`.

## v0.16 (round 204) — persistent records (structural sharing for `Record`)
- **The fix round 200 flagged and left as optional backlog.** `Record` was
  a thin wrapper around a plain Python `dict`; every `put` (`b_put`,
  `whence/interp.py`) did `fields = dict(r.payload.fields); fields[k] = v`
  — a full shallow copy of the CURRENT store on every single call. Since
  `derived(...)` keeps a node's `inputs` (including the superseded store)
  reachable forever — by design, `why`/`steps` must be able to trace back
  through it — N sequential `put`s onto a growing store costs O(N) each
  with the store growing ~linearly in N: O(N^2) cumulative allocation by
  construction, and every intermediate copy stays live. Round 200 measured
  this directly (`self_host.lang`'s own 66-check test section, run through
  `self_eval.lang`'s guest evaluator, passed 700 MB/1.2 GB `RLIMIT_AS`
  caps by checkpoint 35/40) but declined to fix it (no curriculum driver
  at the time, a real but nontrivial change).
- **What was built**: `whence.values.PMap`, a persistent (immutable) AVL
  tree keyed by string, giving `Record` the same treatment `WList` (v0.6)
  already gives lists. `put(k, v)` returns a NEW map allocating only the
  O(log n) nodes on the path from the root to `k`'s position —every
  sibling subtree is the SAME object as before, shared, not copied. `get`/
  `__contains__`/`__len__`/`items()`/`keys()` round-trip through the same
  dict-shaped API every existing call site already used (`in`,
  `fields[name]`, `.get(...)`, `.items()`, `set(fields)`, `sorted(fields)`,
  `len(fields)`) — no call site needed new methods except the two that
  used to hand-roll the copy: `b_put` now does
  `r.payload.fields.put(name, v)` and `merge` does
  `a.payload.fields.merged_with(b.payload.fields)` (`other` wins on
  shared keys, same as the old `dict.update` semantics). `Record.__init__`
  accepts either a plain dict (record literals, tests — built via
  `PMap.from_dict`, a one-time O(k log k) cost for the literal's own small,
  fixed field count) or an already-built `PMap` (the `put`/`merged_with`
  fast path — stored directly, no extra copy at the `Record` layer).
  Field order was never semantically meaningful to begin with — every
  display site already did `sorted(p.fields.items())` and equality is
  set-based — so `PMap`'s key-ordered iteration is not a behaviour change,
  just a faster way to reach the same order. No delete is needed (Whence
  records never lose a field), which keeps the AVL logic to the classic
  insert-only rotations.
- **Verification.** `tests/test_v16.py` (15 new tests): `PMap` unit tests
  differential against a plain dict (including a branch-from-a-snapshot
  case that only makes sense for a persistent structure — two divergent
  futures from the same shared prefix, both reading back correctly);
  `Record` integration tests (construction from a dict vs. a `PMap`,
  `put`-chain-via-real-language-builtins, `merge` conflict semantics,
  three-way fast/direct/slow parity on a long `put` chain, and a check
  that a record's OWN provenance `inputs` still come from the literal's
  DECLARED order, not `PMap`'s key order — the two are orthogonal, this
  round only changed the latter). Full suite 865/865 (850 + 15). Whole-repo
  differential (`bench/ref_diff.py --counters`, direct/fast/slow ×
  every example, binding/check/output counts) against the pre-round-204
  `HEAD`: 0 differing (file, mode) pairs — behaviour is byte-identical.
- **`bench/pmap_scaling.py`** isolates the asymptotic claim from the
  self-hosting harness's noisier end-to-end numbers (parsing, lexing, the
  guest evaluator itself all mixed in there): N sequential `put`s onto a
  record with N ~distinct keys (matching the real store-growth shape,
  NOT a small fixed key set — repeatedly overwriting a handful of keys
  keeps the old `dict`-copy approach linear, not quadratic, so the
  benchmark has to grow the store to be a fair comparison), every
  intermediate version retained in a list (mirrors provenance retention).
  Old (`dict` copy) vs new (`PMap`), same N: 200 → 0.0035s/0.0055s,
  400 → 0.020s/0.011s, 800 → 0.081s/0.038s, 1600 → 0.30s/0.050s,
  3200 → 0.61s/0.116s — old grows quadratically (16x N from 200→3200,
  ~174x time, close to the 256x a pure O(N^2) would predict), new grows
  close to N log N (~21x time for 16x N). A 12800-point run was attempted
  and killed by the OOM reaper (exit 137) — retaining ALL versions of a
  dict that reaches thousands of entries is itself O(N^2) MEMORY
  regardless of which map implementation is under it (each of the N
  retained versions has its own O(N)-sized flat dict), a reminder that
  this microbenchmark's "keep every version in a Python list" is a
  deliberately pessimistic stand-in for provenance retention, not
  something to push arbitrarily far on a memory-constrained box.
- **A real, honestly-reported trade-off, not a pure win**: re-running
  `bench/self_host_memscale.py` (round 200's own tool) shows the memory
  curve is now dramatically flatter — checkpoint 20 (`self_host.lang`'s
  real test section through the guest evaluator) peaks at 119 MB vs round
  200's 198 MB, checkpoint 25 at 121 MB vs 259 MB — but checkpoint 30
  TIMED OUT at the script's default 60s wall clock (elapsed was already
  climbing: 12.4s → 14.1s → 17.7s → 25.6s → 29.8s for checkpoints
  5/10/15/20/25, roughly 2x round 200's elapsed at the same checkpoints).
  Root cause: a Python-level AVL node allocation (attribute reads on two
  child pointers, height/size arithmetic, a `_pinsert` recursive call per
  tree level) costs far more per operation in constant-factor terms than
  a single C-level `dict.copy()` + `__setitem__`, which is exactly the
  operation it replaced. At the store sizes this specific harness
  actually reaches, the O(log n)-vs-O(1)-per-op difference does not (yet)
  outweigh the constant-factor gap — this is the textbook trade-off every
  real persistent data structure makes (Clojure's/Scala's persistent maps
  are slower per-operation than a mutable hash map for exactly this
  reason), not a bug in this implementation. See round 204's knowledge
  file for the full re-run at a longer timeout and the net verdict.

## v0.16.1 (round 206) — guest parity: `steps` in `self_eval.lang`
- **The bug round 204 found and flagged.** Getting further into
  `self_host.lang`'s test section than any previous round (its own
  checkpoint 47, `parse_whence(...)` on a small recursive function, then
  `check "guest AST is itself a real Whence value with its own history":
  not missed(p7) and len(steps(p7)) > 0`) failed under the deep
  guest-EVALUATOR level (`self_eval.lang`'s `run_src`) — but passed fine
  when the SAME `parse_whence`/`steps` call ran at the shallower
  direct/host level (self_eval.lang's own functions executed directly by
  the host, no `run_src` involved: 743 real steps). The two levels
  disagreeing pointed at `run_src`'s own machinery, not `parse_whence`.
- **Root cause, once isolated with a 12-second targeted repro (library
  text + ONE `steps(p7)` call, skipping the other 46 checkpoint-47
  checkpoints' cost) instead of replaying the whole slow checkpoint**:
  `steps` was never in `self_eval.lang`'s `builtin_names` list at all — so
  a guest program calling `steps(...)` failed at NAME RESOLUTION
  (`lookup`'s "unbound name 'steps'"), never even reaching `apply_builtin`/
  `apply_host_builtin`'s dispatch tables. This is a materially different
  failure than "arity mismatch" or "not implemented in the guest" (the
  two outcomes `apply_builtin`/`apply_host_builtin` are actually built to
  produce for a recognized-but-unsupported name) — the whole "provenance
  as data" (round 4) builtin family (`steps`, `at`, `blame`, `diverge`,
  `contrast`) was simply invisible to the guest's own name resolver,
  because no prior self-hosting round's test corpus had ever called one
  of them from GUEST-evaluated code before checkpoint 47 existed.
- **The fix**: add `"steps"` to `builtin_names` (so `new_store()` seeds a
  real builtin-ref binding for it) and `steps: -1` to `arities` (reusing
  the same "1 or 2 args" sentinel `range` already uses, matching the
  host's own `@register("steps", (1, 2))`), then delegate straight to the
  REAL host `steps` builtin in `apply_host_builtin`:
  `else if name == "steps" { if len(args) == 1 { steps(a0) } else { steps(a0, (args[1]).v) } }`.
  This is the exact same "free delegation" trick round 176 used for
  `guess`/`is_guess`/`confidence`/`sure`: `a0` (`args[0].v`, the guest
  box's own payload) is not a synthetic guest structure — it is a REAL
  host Whence value, because every guest `put`/`merge`/record-literal
  self_eval.lang's own evaluator performs to build the guest AST is
  itself a real host builtin call with real host provenance. `steps`
  walking `a0` therefore reflects genuine (if much larger — see below)
  history, for free, with zero guest-side reimplementation of
  `walk_steps`. Deliberately NOT added to the `propagating` list: like
  `is_guess`, `steps` (and `blame`) are explicitly TOTAL on the host
  (`interp.py`'s own comment: "these are total: they work on misses —
  that is the point") — an argument miss must reach the real `steps` call
  so it can walk the MISS's own history, not get short-circuited into a
  generic "builtin"-op miss first.
- **Why `at`/`blame`/`diverge`/`contrast` are NOT fixed alongside this**:
  same family, same fix shape, but nothing in the current test corpus
  exercises them from guest code, so shipping untested guest dispatch for
  them would violate this project's own testing discipline. Flagged as
  the natural, narrowly-scoped follow-up if a future round's self-hosting
  work needs one of them.
- **Why the differential fuzzer's `BANNED` list keeps `steps` banned even
  though the guest now supports it** (unlike `guess`/`confidence`, which
  round 176 DID unban): `harness/swe/guest.py`'s oracle compares bare
  PAYLOAD values between host-direct and guest-mediated execution, and
  `len(steps(x))` (or `steps(x)` itself) is a direct readout of
  provenance GRAPH SIZE — which legitimately, permanently differs between
  the two execution modes, because `self_eval.lang`'s own interpreter
  loop adds many more real host Prov nodes per guest operation (every
  guest `put`/`merge`/field-access is itself an additional real host
  builtin call) than a host directly evaluating the same expression would.
  A Guess's confidence float or a `sure()` boolean outcome does not have
  this problem (provenance-shape-independent); a step COUNT does. Unbanning
  it would manufacture false "divergence" findings on nearly any
  nontrivial fuzzed program — not a language bug, an inherent, permanent
  cost of self-hosting layering (documented alongside `guest.py`'s
  existing `depth_skew`/miss-reason-wording exemptions).
- **Verification**: `tests/test_self_hosting.py` gained the exact
  self_host.lang check (line 651-652) as a 5th assertion inside
  `test_guest_evaluator_executes_self_host_library` (now passes), plus a
  new `test_guest_steps_two_arg_pattern_and_total_on_miss` covering the
  2-arg pattern-filter form and the miss-is-total guarantee — neither was
  exercised anywhere before this round. Full suite 866/866 (865 + 1 new
  test function). Host fuzz (seed 401, n=300), oracle campaign (seed 402,
  n=200 × 6 oracles), and guest-differential campaign (seed 403, n=150,
  `steps` still banned so unaffected by construction) all clean: 0 unique
  finding signatures. `bench/ref_diff.py --counters` re-run against the
  pre-round-206 tree. **Also confirmed, NOT caused by this round** (two
  pre-existing `harness/tests/test_swe_guest.py` failures found while
  running the wider suite, isolated against a clean git-HEAD copy of
  `languages/whence` before attributing): seed 4002's `effects`-guest
  divergence (flagged since round 167/171, still open) and a NEW-to-this-
  investigation seed-152 `why_shape` guest divergence on a `guess`-family
  program (`guest-only ops: ['literal']` vs `host ops: ['let', 'list',
  'miss']`) both reproduce identically on `HEAD` with none of this
  round's or round 204's changes applied — see
  `knowledge/round-206-whence-v16-guest-steps-parity.md` §5.

## v0.16.2 (round 210, landed by round 212) — closing both seed-152/seed-4002 guest divergences
- **Seed-152 (`why_shape`)**: `self_eval.lang`'s `eval_unary` "miss" branch
  unconditionally kept the reason operand as a why-input
  (`mkb(miss r.v.v, "miss", [r.v])`) for every `miss <expr>`. The real host
  (`interp.py`'s `_miss_lit`) only keeps that input when the reason is
  itself a miss (propagation) or a valid string; a non-string, non-miss
  reason (e.g. `miss 1`) discards the operand and produces a fresh 0-input
  miss node. The guest's unconditional version invented a `"literal"` op
  the host derivation never has for that third case. Fixed to match the
  host's own three-way branch (`if missed(r.v.v) or is_str(r.v.v) { ... }
  else { mkb(miss r.v.v, "miss", []) }`); pinned with a dedicated why-shape
  op-walk test (`tests/test_self_hosting.py::
  test_guest_miss_unary_why_shape_matches_host_for_all_three_reason_kinds`)
  since a plain value-level `check` in `self_eval.lang` itself cannot see
  an input-COUNT difference, only a value difference.
- **Seed-4002 (`effects`)**: guest recursion deep enough to reach the
  HOST's own recursion-depth guard mid-chain — inside `self_eval.lang`'s
  own `eval`/`exec_stmt`/`apply`/`apply_closure` recursion, not the guest
  program's own call depth as such — got back a bare miss where that
  chain's own code unconditionally expects an `@{v:.., st:..}` store
  record, corrupting the WHOLE guest store into a miss and cascading false
  "unbound name" failures through every later statement. Fixed with a
  guest-level function-CALL depth ceiling, `GUEST_MAX_DEPTH = 400`, tracked
  as `st.gd` (threaded through `new_store`/`alloc`/`apply_closure`'s
  return) and checked ONLY in `apply_closure` — the single choke point
  every GUEST call passes through (`self_eval.lang`'s own internal
  statement-sequencing recursion never reaches `apply_closure`, so it's
  unaffected). Picked with a wide safety margin under the host's own
  effective ceiling (~1300 guest levels at ~15 host frames/guest call): no
  example or self-hosting corpus this project has ever run comes close to
  400 real guest-level call frames. Past the ceiling, `apply_closure`
  returns a well-formed miss (blaming the over-deep call by name and
  depth) with the CALLER's own still-good store untouched, instead of
  silently corrupting the store.
- **Verification**: full `languages/whence` suite 867/867 (was 866 + this
  round's 1 new test); `tests/test_self_eval.py`'s example-run count
  updated 102→103 (`self_eval.lang`'s own self-test corpus gained one
  check: `"guest miss with non-string reason still misses"`). The wider
  `harness/tests/test_swe_guest.py` differential suite: 44/44 (was 2
  failures pre-fix). Both flagged seeds directly re-probed via
  `swe.guest.oracle_self_eval` — seed 152 and seed 4002 both now return
  `ok` (were `mismatch`). A fresh 100-program guest-fuzz campaign (seed
  401, `swe.guest` CLI): 0 unique finding signatures.
- **History note**: round 210 built and tested this fix but was killed
  mid-flight (the recurring outer-driver-timeout pattern — see
  `research-state.md`'s harness(A) entry) before it could commit or write
  a knowledge file. Round 212 found it sitting as an unstaged, uncommitted
  diff, re-verified everything from a clean read of the diff (not by
  trusting any prior round's own narration, per this session's standing
  discipline), and landed it. See
  `knowledge/round-212-whence-r210-reconciliation-seed152-seed4002-closure.md`.

## v0.16.3 (round 216) — self-hosting round 8: `steps`'s real memory cost, first full 66/66-check completion
- **Falsified hypothesis, kept in the record on purpose**: `bench/
  self_host_memscale.py` (round 200/204's fresh-subprocess, `RLIMIT_AS`-
  capped memory-scaling tool) reran under the default 700 MB cap and
  failed at checkpoint 50 with `MEMORY_ERROR` at ~703 MB, where round 204's
  own table reported 310 MB for the identical checkpoint. First hypothesis
  — round 210/212's `GUEST_MAX_DEPTH` depth-guard fix added two extra
  `merge` calls per guest closure call (entry/exit `st.gd` bookkeeping),
  plausibly ~doubling retained store versions — was tested with a
  controlled A/B (identical host `interp.py`/`values.py`, `self_eval.lang`
  swapped between its pre-/post-round-210 versions) and **refuted**: both
  versions failed within 0.2 MB of each other (701.7 MB vs 701.5 MB) at
  checkpoint 50, ruling out the depth guard as the cause.
- **Real cause, found by testing one commit further back**: swapping in
  the TRUE round-204-era `self_eval.lang` (pre-round-206, before `steps`
  had a working guest builtin) reproduced round 204's own historical
  numbers almost exactly (checkpoint 45: 234.4 MB vs round 204's 234 MB;
  checkpoint 50: 310.3 MB vs round 204's 310 MB). The difference is round
  206's `steps` guest-parity fix: `self_host.lang`'s checkpoint-47 check
  (`len(steps(p2)) > 0`) failed with a cheap, immediate "unbound name"
  miss before round 206 — round 204's own checkpoint-47-and-later readings
  never actually exercised a working `steps` call. Once `steps` really
  runs (round 206 onward), it walks the FULL host-level provenance graph
  reachable from its argument, exactly as round 206's own writeup
  predicted ("much larger... for free, with zero guest-side
  reimplementation") but never quantified: a one-time jump from 282.7 MB
  (checkpoint 46) to 690.3 MB (checkpoint 47), after which growth resumes
  the same roughly-linear per-check slope as before.
- **Not a regression to fix** — `steps` genuinely working (vs. silently
  failing name resolution) is round 206's whole point; the memory cost is
  an honest, expected consequence of a real provenance walk over
  guest-multiplied host nodes, the same "not a pure win, but a real
  trade-off" framing round 204 used for `PMap`'s own elapsed-time cost.
- **New milestone**: with the cap raised to 1200 MB (round 216, informed
  by this measurement — see `bench/self_host_memscale.py`'s updated
  module docstring for the full curve and reasoning), the complete
  66-check `self_host.lang` test section now runs end-to-end through the
  deep guest-EVALUATOR level (`run_src`) for the FIRST TIME ever: 66/66
  checks passing, 1072 MB peak, ~112-122 s (two independent runs). Every
  prior round (192/198/200/204) either killed the run early or hit the
  wall-clock/memory ceiling before completion.
- **Verification**: no host code (`interp.py`/`values.py`) or guest code
  (`self_eval.lang`/`self_host.lang`) changed this round — this is a
  measurement-and-tooling round only (`bench/self_host_memscale.py`'s
  default cap/timeout and docstring updated to match reality). Full
  `languages/whence` suite reconfirmed green post-change (unaffected by
  construction, since no interpreter or example file was touched).

## v0.16.4 (round 218) — guest parity: `at`/`blame`/`diverge`/`contrast` in `self_eval.lang`
- **Closes the follow-up backlog round 206 explicitly flagged and declined
  to build**: `at`/`blame`/`diverge`/`contrast` are the same "provenance as
  data" (round 4) builtin family as `steps`, share the exact same gap —
  never in `self_eval.lang`'s `builtin_names`, so guest code calling one
  failed at NAME RESOLUTION before ever reaching `apply_builtin`/
  `apply_host_builtin`'s dispatch tables — and get the identical fix.
  Round 206 explicitly declined to build them alongside `steps` because
  nothing in the test corpus exercised them from guest code yet
  ("evaluate-before-authoring"); `self_host.lang`'s own source still calls
  none of them, so this round wrote the exercising tests FIRST (making the
  gap real, per the same discipline) before fixing it.
- **The fix**: add `"at"`, `"blame"`, `"diverge"`, `"contrast"` to
  `builtin_names`, arities `at: 2, blame: 1, diverge: -1, contrast: -1`
  (matching the host's own `@register` arities — `diverge`/`contrast` reuse
  the `-1` "1 or 2 args" sentinel `steps`/`range` already use), then
  delegate straight to the real host builtin of the same name in
  `apply_host_builtin`, exactly `steps`'s own free-delegation shape:
  `a0` (`args[0].v`) is already a real host Whence value with real host
  provenance (every guest `put`/`merge`/record-literal call
  `self_eval.lang`'s own evaluator performs is a real host builtin call),
  so `at`/`blame`/`diverge`/`contrast` walking it costs zero guest-side
  reimplementation. None of the four were added to `propagating` — like
  `steps`, host `interp.py` documents this whole family as TOTAL (a miss
  argument must reach the real builtin so it can walk the miss's own
  history, not get short-circuited into a generic "builtin"-op miss).
- **A real representational wrinkle found while writing the tests, left
  unfixed as out-of-scope**: indexing into a `steps(...)`/`blame(...)`
  result list from GUEST code and then field-accessing an element (e.g.
  `steps(x)[0].op`) returns a MISS, not the expected step-record field —
  `eval_index`'s `is_list((o.v).v)` branch passes list elements through
  UNBOXED (bare host `Record`s shaped `{op, detail, line, show, depth,
  inputs, count, value}`), but every other guest field-access path expects
  the `{v, op, ins}` "guest box" shape, so `.op` looks for a `v` field that
  isn't there. Round 206's own `test_guest_steps_two_arg_pattern_and_total_
  on_miss` had already sidestepped this by only ever comparing `len(...)`
  of two step lists, never indexing an element — this round's tests follow
  the same discipline for the same reason, and do not fix the underlying
  boxing mismatch (a real design question — should `_step_record`'s guest-
  visible list elements get `mkb`-wrapped? — with no corpus need yet to
  force an answer either way). Flagged as backlog if a future round's
  guest code actually needs to introspect individual step records.
- **A second wrinkle, informing the tests' design**: the REAL host
  provenance reachable from a guest value under `run_src` reflects
  `self_eval.lang`'s OWN internal call chain (its parameter names like
  `arg p`, its own eval helpers), not the guest program's syntax — e.g.
  `diverge(1 + 2, 1 + 2)` (the identical literal, evaluated twice) still
  reports one origin, because the two evaluations run through different
  internal paths inside `self_eval.lang` itself, not because the GUEST
  values differ. Confirmed empirically before writing any assertion (see
  the round-218 knowledge file for the raw numbers). Test assertions below
  therefore avoid exact-pattern-match and same-vs-different-divergence-
  count claims, and instead pin only properties true regardless of that
  internal noise.
- **Why the differential fuzzer's `BANNED` list needs no change**:
  `harness/swe/guest.py`'s `BANNED` regex already listed `at`, `blame`,
  `diverge`, `contrast` alongside `steps`, `why`, `snip`, `print` — banned
  from the START (well before any of them had a working guest dispatch),
  for the identical "graph size legitimately, permanently differs between
  host-direct and guest-mediated execution" reason round 206 documented
  for `steps`. Confirmed unaffected by this round's change (still banned,
  by construction, from the fuzzed/oracle/guest-differential campaigns).
- **Verification**: `tests/test_self_hosting.py` gained two new tests —
  `test_guest_at_blame_diverge_contrast_dispatch_to_real_host_builtins`
  (proves the real host builtin runs, via the real "no step named ..."
  miss wording `at` produces on a not-found search — a pre-fix guest call
  would instead hit the generic "not implemented in the guest" stub
  message, so seeing the real host wording is a genuine differential
  proof, not just "didn't crash") and
  `test_guest_at_blame_diverge_contrast_total_on_miss_arguments` (pins
  `at`'s specific total-vs-propagating split: its VALUE argument being a
  miss still gets a real search, but its PATTERN argument being a miss
  DOES propagate via `merge_miss`, matching host `b_at`; `diverge`/
  `contrast` stay total on either side). Full `languages/whence` suite
  869/869 (867 + 2 new test functions); `tests/test_self_hosting.py` alone
  7/7 (was 5/5). `harness/tests/test_swe_guest.py`'s two pre-existing,
  unrelated divergences (seed-152/seed-4002) closed by round 210/212 stay
  closed — reconfirmed, not touched by this round.

## v0.16.5 (round 222, landed by round 223) — guest parity: `steps`/`blame`/`diverge` list-element field access in `self_eval.lang`
- **Closes the "real representational wrinkle" v0.16.4 found and explicitly
  left as backlog**: guest code that indexes a `steps(...)`/`blame(...)`/
  `diverge(...)` result list and reads a field off an element (e.g.
  `steps(x)[0].op`) read as a miss ("no field 'v' (record has: count,
  depth, detail, inputs, line, op, show, value)") even though `steps(x)`
  itself and `len(steps(x))` both worked. Root cause: `eval_index`'s
  `is_list((o.v).v)` branch passes list elements through UNBOXED — correct
  for guest-*built* lists (their elements are already `{v, op, ins}` boxes,
  since guest expressions always produce boxes), wrong for these three
  builtins' elements, which are raw host `Record`s (`_step_record`'s
  `{op, detail, line, show, depth, inputs, count, value}` for
  `steps`/`blame`; a second, structurally different `{kind, a, b[, which]}`
  shape for `diverge`, whose `a`/`b` nest a `_step_record` one level down)
  — correct at the HOST level, where field access reads a `Record`
  directly with no box convention, but never boxed for guest consumption.
- **The fix**: `box_step_record(rec)` in `self_eval.lang` re-boxes each of
  the 8 `_step_record` fields individually (`mkb(rec.op, "step", [])` etc.
  — a fixed `"step"` op label and empty `ins`, since no real guest-visible
  derivation happened inside the bridge; mirrors how `range`/`key`/
  `reason` list elements are already labelled a few lines above).
  `box_diverge_record(rec)` handles the second shape by boxing `kind`/
  `which` directly and calling `box_step_record` on the nested `a`/`b`.
  Both wired into the same post-`apply_host_builtin` list-mapping branch
  `range`/`keys`/`reasons` already used (`else if name == "steps" or
  name == "blame" { map(fn(x) { mkb(box_step_record(x), "step", []) }, p) }`
  and the `diverge` analogue).
- **Note: `at`'s single-node result and `contrast`'s string result need no
  equivalent fix.** `contrast`'s payload is always a string (a rendered
  report), never a list of records, so no boxing question arises.
  `at(v, pattern)` returns a single history node rather than a list, so
  `eval_index`'s list-passthrough branch never applies to it; whether a
  successful `at()` match's own payload is guest-box-shaped depends on
  *where inside `self_eval.lang`'s own internal call chain* the match
  landed (see v0.16.4's "internal noise" note below) — not a new gap this
  round found or fixed. Confirmed empirically while investigating this fix
  (round 224): `at(x, "let x")` against a guest `let x = @{...}` record
  literal returns a MISS (`missed(found)` is `True`), the same "doesn't
  find the guest-syntax match" property v0.16.4 already documented for
  `diverge(1+2, 1+2)` — so `found.a` reading as a miss afterward is a miss
  propagating through field access as designed, not a boxing defect.
- **Verification**: new test
  `test_guest_steps_blame_diverge_element_field_access` (`tests/
  test_self_hosting.py`) indexes an element AND reads multiple fields off
  it for all three builtins (not just `len(...)`, which is all v0.16.1/
  v0.16.4's own tests exercised) — every field read a miss pre-fix, so
  this is real exercising code, not a retroactive pin. `tests/
  test_self_hosting.py` 43/43 (was 41). Full `languages/whence` suite
  green. `harness/swe/guest.py`'s `BANNED` regex needs no change (already
  excludes `steps`/`at`/`blame`/`diverge`/`contrast` from the fuzzed
  differential corpus, unaffected by construction).
- Round 222 built and tested this but was killed by the driver's own outer
  wall-clock timeout mid-round (`tool_calls=87`, well under the max-turns
  cap — a genuine wall-clock kill, not a crash or a turn-budget death) and
  left it uncommitted with no knowledge file; round 223 (harness A track)
  verified fresh from a clean read and landed it as commit `8c6aeeb`; round
  224 backfilled this SPEC.md section, which neither round's own track
  mandate covered (223 was harness work, 222 never reached documentation
  before being killed). See `knowledge/round-223-harness-round222-landing-
  and-second-timeout-kill-counterexample.md` §1 for the landing detail and
  `knowledge/round-224-whence-matches-shapeof-guest-parity.md` for this
  round's own verification.

## v0.16.6 (round 224) — guest parity: `matches`/`shapeof` in `self_eval.lang`
- **A fresh instance of the same gap class rounds 206/218 already found and
  fixed for the rest of the "introspection" builtin surface, found by
  auditing `self_eval.lang`'s `builtin_names` against the host's full
  `## Builtins` list below** (not flagged by any prior round, since neither
  builtin is exercised by `self_host.lang`'s own source or by the
  differential fuzzer's generator grammar — `harness/swe/fuzz.py` never
  emits a `matches`/`shapeof` call, so this gap was entirely invisible to
  every regression campaign run to date): `matches`/`shapeof` (v0.12
  structural types) were never added to `builtin_names` at all, so guest
  code calling either failed at NAME RESOLUTION ("unbound name"), never
  reaching `apply_builtin`/`apply_host_builtin`'s dispatch tables.
- **The fix**: `"matches"`/`"shapeof"` added to `builtin_names` and
  `arities` (`matches: 2, shapeof: 1`, matching the host's own `@register`
  arities), dispatched in `apply_host_builtin` via the same free-delegation
  trick `steps`/`at`/`blame`/`diverge`/`contrast` already use — both are
  TOTAL (host `b_matches`/`b_shapeof` are documented "like `missed`: never
  itself a miss") and return scalar payloads (a bool / a kind string), so
  no list-of-records post-processing is needed the way `steps`/`blame`/
  `diverge` (v0.16.5 above) required.
- **One real wrinkle found empirically, before writing any test, that pure
  free-delegation would have missed**: a GUEST closure is an ordinary
  tagged `Record` under the hood (`self_eval.lang`'s own `is_callable`
  guard, used a few branches above to keep `len`/`keys`/`put`/`merge`/
  `has` opaque on functions), not a real host `Closure`/`Builtin` Python
  object — so undguarded delegation to host `shapeof`/`matches` reports
  `"record"` for a guest function's shape, never `"fn"`. Unlike the
  `len`/`keys` guard (where the right guest answer is a miss — "of a
  function" makes no sense), `shapeof`'s entire job IS reporting shape, so
  silently mislabelling a function as a record would be a real,
  user-visible correctness bug in the fix itself, not a cosmetic gap left
  for later. Fixed with an explicit `is_callable(a0)` branch ahead of the
  delegation (`shapeof`: `"fn"` outright; `matches`: `is_str(spec) and
  (spec == "any" or spec == "fn")`), the same split `typed`'s own
  `guest_type_ok` already uses for its own callable case two branches
  above — found by testing every `_KIND_ORDER` shape (`num`/`str`/`bool`/
  `list`/`record`/`miss`/`guess`/`fn`) individually rather than assuming
  scalar delegation would just work once dispatch was wired up.
- **A narrower, deliberately unfixed caveat, documented rather than
  chased**: `matches`/`shapeof` free-delegate to the real host builtin for
  every NON-callable case, which keeps the full v0.12 feature surface
  reachable (including a STRUCTURAL `Record` spec, e.g. matching a shape's
  nested field types) — `typed`'s own guest implementation, by contrast,
  only ever supports a plain string spec (`guest_type_ok`'s `is_str(spec)`
  guard has no Record-spec branch at all, and no round has ever needed to
  lift that). A structural Record spec matched against a guest RECORD
  value would still misbehave the same way `typed` already doesn't
  support: `_type_match` would recurse into the guest record's own
  `payload.fields`, landing on each field's `{v, op, ins}` box wrapper
  instead of its raw value, and every nested check would see the wrong
  shape. Real, same "evaluate before authoring" discipline as `at()`'s
  internal-noise caveat (v0.16.5) and `typed`'s own pre-existing scope
  limit — no corpus need yet for guest code to structurally `matches` a
  record built entirely inside `run_src`.
- **Verification**: new test
  `test_guest_matches_shapeof_dispatch_and_callable_guard` (`tests/
  test_self_hosting.py`) — 15 checks covering every `_KIND_ORDER` shape for
  `shapeof`, the total-on-miss property and an `"any"`/mismatching-spec
  pair for `matches`, and the callable-guard branch for both builtins
  explicitly (not just name resolution succeeding). `tests/
  test_self_hosting.py` 44/44 (was 43). Full `languages/whence` suite
  green (871/871: 869 baseline + round 222's own +1 landed by round 223,
  +1 this round). `harness/swe/guest.py`'s `BANNED` regex needs no
  addition for these two — unlike `steps`/`at`/`blame`/`diverge`/
  `contrast`, `matches`/`shapeof` report a value's own SHAPE, a property
  that is identical between host-direct and guest-mediated execution of
  the same program (a number's kind doesn't depend on which internal call
  chain computed it), so there is no "legitimate but noisy divergence"
  concern to suppress — confirmed moot in practice since the fuzzer's
  generator grammar never emits either builtin anyway. Fresh regression
  campaigns re-run this round before AND after the fix (fuzz seed 501,
  oracles seed 503, guest seed 502): 0 unique finding signatures in all
  three, both passes.
- See `knowledge/round-224-whence-matches-shapeof-guest-parity.md`.

## Builtins
`print rand len range map filter fold push str num abs sqrt missed reasons
note contains join keys merge get put has find steps at blame diverge
contrast typed matches shapeof guess is_guess confidence sure`

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
**Resolved (round 138, see `state/research-state-archive.md` and
`knowledge/round-144-whence-structural-types-reconciliation.md` §3):**
`install_timetravel_builtins` was deleted rather than fixed —
`whence/timetravel.py`'s own module docstring carries the same writeup as
this section, plus the reason the fix-it option was rejected: restoring a
prior value of a named binding has no coherent meaning under decision 3
(no assignment/no rebinding), so the feature was a design misfit from the
moment it was proposed outside the round process, not just a wiring bug.
`TimeTravelDebugger` stays as a documented, never-wired, pure-Python
helper for inspecting `Env.vars` while developing the interpreter itself
(e.g. a future host-side REPL) — `tests/test_timetravel.py`'s 11 tests
exercise it directly as a Python class, real and unaffected by the
deletion. A real "time travel" language feature, if ever wanted, belongs
on top of the existing provenance builtins (`at`/`steps`/`blame`), not as
a mutable checkpoint stack — nothing has needed it since.

## Self-hosting round 9 (round 254) — `bench/self_host_memscale.py --mode steps-repro`
Round 228 root-caused `steps()`'s enormous guest-level cost (any
`steps()` call, on any value, once self_host.lang's function library has
been loaded via `self_eval.lang`'s `run_src`, walks the ENTIRE
store-threaded interpretation trace, not just the target value's own
derivation) but explicitly declined to re-run the 13-checkpoint,
multi-GB sweep `bench/self_host_memscale.py` needs to find a fresh
absolute-MB replacement for its now-stale 1200 MB default, judging the
risk/cost not worth it on this specific shared, contended host. Round
254 re-checked that judgment call with fresh numbers (`free -h`: 675 MB
physically free, 2.1 GB "available", swap already 70% full — less
headroom than round 227/228 had) and made the same call again, for the
same reason: a capped subprocess can't trigger a system-wide OOM sweep,
but a multi-GB resident probe still pages everything else on a 3.8 GB
box through swap while it runs, a real cost to this host's other live,
unrelated services (trading bots, Hermes gateways).
Instead of the full sweep, promoted round 228's own ad hoc minimal
isolation repro (library load + one trivial `steps(miss ...)` call, no
self_host.lang test-section checks, no `parse_whence` call — strictly
less prior work than checkpoint 5) into a permanent, reusable tool mode:
`bench/self_host_memscale.py --mode steps-repro`, with its own
safe-by-default cap/timeout (600 MB / 120 s — chosen to sit comfortably
inside this run's own 2.1 GB "available" figure, unlike the full sweep's
1200 MB default). Measured live, twice, via a real subprocess (not
guessed): **`MEMORY_ERROR` at peak_kb≈600,000 (~600 MB) in 85–89
seconds**, both runs. This is a strictly cheaper and safer confirmation
of round 228's finding (which reached >1.35 GB, still climbing, after
291 s uncapped) — the cost has not shrunk, and if anything has grown
further, since rounds 234/236/246/252 each added more guest-parity
dispatch code to `self_eval.lang` that becomes part of every `st` trace
`steps()` walks. A full re-sweep for a fresh absolute-MB number for the
13-checkpoint table still needs round 228's own order-3000-4000 MB /
600 s treatment, on a host that isn't mid-contention — not this one,
not this round. See `knowledge/round-254-whence-self-hosting-round9-steps-repro-tool.md`.
