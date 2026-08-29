---
name: tiny-language-implementation
description: Builds a small, fully-tested interpreted language (lexer → parser → evaluator) in stdlib Python in one session, using errors-as-values, parse-time discipline, and a four-layer test pyramid. Use when asked to design or implement a programming language, DSL, config language, expression evaluator, or interpreter, or to add ordinary language features or tests to an existing one. NOT for an existing interpreter that crashes with RecursionError/"maximum recursion depth", needs tail calls, or must be restructured to recurse deeper or faster — that is generator-trampoline-evaluator's territory even when the request says "restructure the evaluator".
---

# Tiny language implementation (stdlib Python, one session)

## Trigger conditions
- Task asks to design/implement a programming language, DSL, config language,
  expression evaluator, or "interpreter for X".
- Task asks to add a feature to such an interpreter and it lacks tests.
- Proven on: Whence (`languages/whence/`, 148 tests, ~1,700 LOC total).

## Steps
1. **Write a 1-page SPEC.md before any code.** Name the one idea, list the
   deliberate design decisions, sketch the grammar with a precedence ladder
   (low→high), and pin exit codes. Every later ambiguity gets resolved by the
   spec, not ad hoc.
2. **Decide the error story first — it shapes everything.** Best-in-class for a
   tree-walker: *errors as propagating values* (a `Miss`/`Error` payload with
   reason strings). Then `eval` never raises for user errors, there is no
   exception plumbing, and the interpreter is total. Convert every runtime
   fault (unbound name, bad index, arity, div-by-zero, non-bool condition)
   into that value; give it a `rescue`-style recovery operator and a
   `missed(x)` predicate.
3. **Lexer** (`tokenize(src) -> [Token(type, value, line, col)]`):
   - Track `line`/`col` on every token; all later diagnostics depend on it.
   - If newlines separate statements, keep a bracket stack and suppress
     NEWLINE inside `( ) [ ]` (data) but not `{ }` (statement blocks).
     Collapse consecutive NEWLINEs; never emit a leading one.
   - Check two-char operators (`==`, `<=`, …) before one-char.
4. **AST**: one tiny class per node, all carrying `line`. A `_simple(name,
   fields)` class factory keeps this to ~40 lines.
5. **Parser**: recursive descent, one method per precedence level, `expect()`
   helper that reports "expected X, got Y at line:col". Push discipline to
   parse time where possible — it turns runtime surprises into instant errors:
   duplicate bindings in a block, duplicate params/record fields, `if` without
   `else`, block not ending in an expression, chained comparisons.
6. **Evaluator**: dispatch dict `{NodeClassName: method}` built once from
   `dir()`; `Env` chain with `get`/`define`. If values carry metadata
   (provenance, types, source spans), make the value *be* the metadata node
   rather than a `(payload, meta)` pair — Whence v0.4 merged `Value` into
   `Prov` (payload aliased onto the same slot with the member descriptor,
   `Prov.payload = Prov.__dict__["value"]`), which halved objects per
   operation and needed no call-site changes because `v.prov` became a
   property returning `self`. Cache the value of every literal node on the
   AST node (immutable values are shareable). Decide the recursion story now:
   a plain recursive walker costs ~10-12 Python frames per language call
   (limit 20000 ≈ guest depth 1800, and embedders must remember to raise
   it). If guest recursion matters, build the evaluator as a generator
   trampoline from the start — see `generator-trampoline-evaluator` — and
   make the depth cap a constructor/CLI tunable that yields the language's
   error value.
7. **CLI `run.py`**: distinct exit codes (0 ok / 1 program-level failure /
   2 lex-parse error), `sys.path.insert` so it runs from any cwd.
8. **Test pyramid, in this order** (Whence ratios in parens):
   a. lexer: token types/values/positions + every LexError branch (13)
   b. parser: shape of precedence trees + every ParseError branch (17)
   c. interpreter: one test per semantic rule, esp. every error path (~56)
   d. examples: run every shipped example via `subprocess`, assert exit code
      AND key output substrings — this locks the user-facing contract (8)
9. **Ship runnable examples** that double as integration fixtures, including
   one that *fails on purpose* to prove the failure path (assert exit 1).
10. **Self-hosting (the honest expressiveness test), staged:** first a guest
   lexer+parser for the language's own syntax emitting ASTs as guest records,
   then a metacircular evaluator (Whence rounds 12+14, `self_host.lang` /
   `self_eval.lang`). What makes the evaluator work in an immutable language:
   - **Store-passing models the host's mutable environments.** Host closures
     capture an Env *object*, so bindings made after capture are visible at
     call time (mutual recursion, forward refs). Reproduce with
     `eval(node, env, store) -> {value, store}`: env = list of frame IDs,
     store = one immutable record mapping frame IDs to binding records,
     threaded through every step. Lookups read the store as of call time, so
     late binding is faithful in BOTH directions (calling a fn that names a
     not-yet-executed sibling is an unbound-name error, same as the host).
     Needs dynamic record access — add `get(record, name)` / `put(record,
     name, value)` builtins to the host first (make `get` share the host's
     field-access helper so `get(r, "a")` ≡ `r.a` node-for-node).
   - **Make guest values BE host values.** Then every host operator the
     evaluator applies (`l + r`, `not v`, a real host `if` on the guest's
     condition) imports host semantics — strictness, propagation, overflow —
     including the host's own error wordings. Delegate first-order builtins
     to the host by name; reimplement only the higher-order ones
     (map/filter/fold/find) around a guest `apply`.
   - **Type tests without a typeof:** total ops + the error predicate:
     `is_list(v) = not missed(v + [])`, `is_bool(v) = not missed(v) and
     (v == true or v == false)` (guard misses BEFORE `==`, which is an
     error on misses).
   - **Differential-test against the host** on a corpus where ≥25% of
     programs error: compare payloads and missed-ness, exempt reason
     wordings; run the guest once (library + N `run_src` calls in one
     program) so the ~800-line library parses once.
   - **Guest-level metadata by boxing (Whence round 18: provenance):** to give
     guest values the host's per-value metadata, box every guest value as
     `{v: payload, op: label, ins: [input boxes]}` — reads (name lookup, list
     index, field/get) PASS THE BOX THROUGH; derivations wrap. Deep-strip
     boxes at the `run_src` boundary so external contracts and the
     host-vs-guest differential stay unchanged. Reuse the host's exact label
     strings (`"let x"`, `"call f"`, `"arg n"` — read them from the host
     source, don't guess: "if then branch" was actually "if took
     then-branch") so provenance itself becomes differentially testable:
     assert hand-picked labels appear in BOTH graphs, and both blame walks
     name the same origin op. Expose metadata to guest programs by REIFYING
     the box graph into ordinary guest records under a node budget — then
     `blame` is 3 lines of guest code over `why` data, no new builtins.
     Boxing also closes tag-spoofing leaks (user record fields become boxes,
     never equal to a raw tag string) and costs ~30% per guest op.

## Exact commands
```bash
cd languages/<lang>
python3 run.py examples/<name>.lang      # run one program
python3 -m pytest tests/ -q              # full suite (should be <1s)
```

## Pitfalls
- `isinstance(True, int)` is True in Python: check `bool` BEFORE numeric in
  show/eq/arith paths, or `true == 1` and `-(true)` silently work.
- Two-char operator lexing after one-char lexing steals `=` from `==`.
- If evaluation wraps results in provenance/metadata nodes, don't add a node on
  *reads* (variable refs, list index, field access) — only on *derivations* —
  or trees explode and history gets laundered.
- Deep recursion in a plain walker: RecursionError must be caught at the
  call boundary, not program top, so it converts to an in-language error
  value and execution continues. With a trampolined walker the binding
  limits move to *other* recursive helpers (rendering, structural equality,
  snapshotting nested values) — cap their nesting.
- If the language propagates errors-as-values through builtins *before*
  inspecting arguments, an error value used as a `fold` seed is rejected
  before the list is examined. Write lookups as recursion, not
  `fold(..., <error>, xs)`.
- Text search over a *rendered* derivation tree is bounded by the render
  caps (depth/nodes) and silently fails past them; expose the structure as
  data (list of step records) for programs to query.
- Rendering derivation/AST trees: cap BOTH depth and node count, and mark
  shared (DAG) nodes on re-encounter, or a fold over 10k items prints forever.
- subprocess example tests: use `sys.executable`, not `"python3"`.
- Verifying `bench/ref_diff.py --counters` (or any per-file differential
  report) via a backgrounded run piped through `tail`: this can silently
  drop files with no error (confirmed twice, rounds 296/300) — redirect to
  a real file instead; see `one-shot-agent-no-background-wait`'s matching
  Pitfall for the full mechanism and the confirmed workaround.

- **Value walkers recurse even when the evaluator does not.** Trampolining
  the evaluator (see `generator-trampoline-evaluator`) lets programs build
  values nested thousands deep (`nest(1500)`); any helper that walks a value
  recursively — structural equality, `contains`, hashing, serialisation —
  then dies with the host's `RecursionError`. Write those with an explicit
  stack (round 5: `deep_eq` crashed on `nest(1500) == nest(1500)`).
- **Recursive-descent parsers have a hidden depth limit.** `((((1))))` ×100
  or `- - - 1` ×977 exceeds the host recursion limit *inside the parser*, so
  the crash escapes before the evaluator's error-as-value discipline can
  apply. Count nesting explicitly at the recursive entry points and raise
  the language's own parse error past a documented limit.
- **The host's number parser is more permissive than your spec.** Python's
  `int()`/`float()` accept `"1_000"`, `"nan"`, `"infinity"`, non-ASCII
  digits; mixing unbounded ints with floats raises `OverflowError`. Parse
  numbers with your own regex and catch `OverflowError` at every float
  operation, or fuzzing will find both (round 5 did).
- **Fuzz the totality invariant before calling the evaluator total.** A
  grammar-directed generator plus stress templates found five crash
  families in an evaluator with 148 green tests — see `fuzz-mutate-kill-loop`.
- **In a total language, your interpreter's own bugs surface as the GUEST
  program's errors.** A wrong-arity recursive call inside the evaluator
  (round 14: `bind_params` dropping an argument) doesn't crash — it becomes
  a miss that propagates into "unbound name" for every closure parameter.
  Debug by calling the evaluator's internals directly at top level, not by
  staring at guest programs; and treat "every guest closure misbehaves the
  same way" as a signal the bug is in one shared helper.
- **Hosts call functions WITH error-valued arguments.** `f(miss)` runs f's
  body (f may ignore the argument); only builtins propagate *initial* miss
  arguments before inspection. A guest fold that short-circuits when the
  accumulator goes bad mid-loop diverges from a host that keeps calling the
  callback. Probe the host's behavior with 5-line scripts BEFORE writing the
  guest's apply, and encode each probe as a differential-corpus case.
- **A grammar-directed fuzzer generating a new host syntax feature will
  feed it straight into the hand-copied guest parser too, unless told
  not to.** The guest lexer/parser (self-hosting, step 10) is a snapshot
  of host syntax at whatever round it was written; it does not
  automatically grow when the host parser does. A shared program
  generator that emits the new construct for both host and
  differential-guest runs turns "guest doesn't support this yet" into a
  false divergence finding instead of an honest, tracked parity gap.
  Give the generator's guest-facing path an explicit no-op override for
  every host feature the guest doesn't parse yet, verify with a fuzz seed
  that 0 guest-generated programs contain the new construct, and track
  closing the gap as backlog — twice in this program a feature's fuzz
  coverage (host-only) and its real guest parity landed multiple rounds
  apart (`: Type`/`-> Type`: round 134 fuzz-only to round 158 guest
  parity; an effect system repeated the same two-step shape one round
  later, still open).
- **When the guest evaluator is itself written IN the host language and
  runs as literal host source (self-hosting), a new builtin's guest support
  can be a straight delegation, not a reimplementation — but every existing
  "what type is this value" probe must be re-audited for it.** Round 176's
  Whence guest (`self_eval.lang`) added guest support for `guess`/
  `is_guess`/`confidence`/`sure` (an uncertainty-carrying value with
  weakest-link confidence propagation through arithmetic) by having the
  guest's `apply_host_builtin` call straight through to the REAL host
  builtins — the guest program is executing as genuine top-level host
  source, so `a.v + b.v` on a wrapped value already gets the host's own
  propagation semantics for free, no guest-side reimplementation needed.
  This was expected going in to be "a materially bigger lift" than the
  guest's earlier `: Type`/`effects` parity work (both of which only
  needed parse-time clause-skipping) — the delegation shortcut closed it
  in one round instead. The cost: every guest helper that asks "is this
  value a number/bool/list" (`is_num`, `is_bool`, `is_list`, a `kind`
  dispatcher) was written before the new value existed, and the new
  value's arithmetic transparently succeeds on those same probes (`missed
  (guess(5,...) + 0)` is false, so a naive `is_num` misreports a guess as a
  plain number) — each such probe needs an explicit `is_<newthing>(v)`
  guard added FIRST, or every downstream dispatch that assumes "arithmetic
  succeeds implies plain number" silently misclassifies the new value.
  Grep every `is_*`/`kind`/`show`-style probe in the guest for this before
  declaring delegation-based parity done, don't just add the new builtins.
- **Duplicated guest source sections drift.** If the evaluator example
  embeds the parser example's code verbatim, add a byte-identity test that
  extracts the shared section from both files and asserts equality.
  **If that extraction is a hardcoded LINE-NUMBER slice (`lines[27:420]`),
  growing the shared section (a new syntax feature) moves the real end
  line without moving the constant** — the test then silently truncates
  the slice and fails on a content mismatch that looks like drift but is
  actually a stale boundary; update both slice bounds in the same edit
  that adds lines to the shared section (round 158: self_host.lang's
  `parse_whence` moved from line 420 to 485 adding `: Type`/`-> Type`
  parsing, and the test needed both numbers bumped, not just the source).
- **A self-hosted guest evaluator's builtin dispatch has two independent
  gates — name resolution, then arity/type dispatch — and a builtin
  missing from the FIRST gate fails as "unbound name", which reads like an
  unrelated bug.** If guest calls resolve by looking the callee name up in
  an environment/name table (seeded with builtin-ref bindings once at
  store-init time) before the dispatcher ever runs, a builtin that already
  exists at the host level — even with delegation code already written for
  it elsewhere in the guest evaluator — can still be completely
  unreachable from guest programs if its name was simply never added to
  that table. The symptom is "unbound name 'x' (line N)" thrown from the
  guest's OWN lookup helper, not an arity mismatch and not the generic
  "not implemented in the guest" stub a missing-dispatch-branch bug would
  produce — don't debug it as either of those. Confirmed twice on the same
  interpreter (Whence rounds 206/218): a whole builtin family (`steps`,
  then `at`/`blame`/`diverge`/`contrast`) sat outside `self_eval.lang`'s
  `builtin_names`/`arities` tables even though nothing else about them was
  guest-incompatible. The fix each time was three additive lines — the
  name in the name table, its arity, one dispatch branch delegating
  straight to the real host builtin using the guest box's already-real
  host-value payload (see the delegation pitfall above) — closing a
  years-old gap in under an hour once diagnosed. Decide whether the new
  dispatch branch belongs on the "propagating" (miss argument
  short-circuits) or "total" (must still run on a miss, e.g. to inspect
  the miss's own history) side by reading the HOST's own totality comment
  for that builtin family, not by guessing or waiting for a test to fail —
  round 206 caught that `steps` needed to stay total from the host
  docstring alone, before writing any test.
- **A host builtin that returns a raw, unboxed record can silently break
  guest code that assumes every value is wrapped.** If guest values are
  boxed for metadata (see the provenance-boxing step above) but a builtin
  you just delegated to returns the host's own internal record shape
  (fields the box format doesn't have, no wrapper field guest code expects
  first), then guest code that reads through it — indexing into the
  result, then field-accessing an element — mismatches the expected shape
  and reads as a miss, not a clear type error. Confirmed in Whence
  (round 218): `steps(x)[0].op` misses because `steps` returns a list of
  bare host `Record`s but the guest's list-element passthrough path
  expects every element to already be a `{v, op, ins}` box. This is a
  second, independent gap from the name-resolution one above — closing
  name resolution does not by itself fix representational mismatches in
  what a delegated builtin hands back; don't assume "it resolves and
  dispatches now" also means "every consumer of its result is compatible."

- **A scope-mirroring static analysis (parse-time effect/alias/purity
  checks) must record NON-matches explicitly, not just skip the write when
  there's nothing interesting to say.** If a per-scope tracking dict is
  only ever written to when a binding IS the thing you're tracking (e.g.
  "this name aliases a known effectful builtin"), then an ordinary,
  unrelated local binding that reuses the same name in an inner scope
  writes nothing — and a lookup that walks outward from the inner scope
  finds nothing there either, so it falls through to an OUTER scope's
  stale match and misidentifies the unrelated local as the tracked thing.
  This is the same bug shape as a cache that only writes on a hit and
  never on an explicit miss: a later lookup can't tell "never computed"
  from "computed and irrelevant here." Fix: write `None`/a sentinel for
  every binding in the tracked namespace — not just interesting ones — so
  an inner scope's entry, present but empty, correctly blocks fallthrough
  to an outer scope's real match (Whence round 266, v0.14.2's
  `alias_scopes`: a `let p = print` then an unrelated inner `let p = 5`
  would otherwise let a `p(...)` call in the inner block wrongly resolve
  to the outer `print` alias).

- **Extending a scope-mirroring static analysis to recurse into a branch
  construct (`if`/`else`, `match`) often needs NO new scope-context
  plumbing — check whether the branch is itself a block whose own fact
  was already resolved while ITS scope was still open, before assuming
  you need to re-derive it after the fact.** It's tempting to conclude
  "a tail that is itself an `if` can't be inspected the same way a bare
  name can, because by the time we look at it the branch's own scope has
  closed" — true only if you'd need to re-run the ORIGINAL resolution
  (e.g. re-look-up a bare name against scopes that no longer exist). If
  each branch is its own block, parsed via the same recursive `block()`/
  `stmt_list()` that already computes and STORES a per-block fact (e.g.
  a `tail_alias_tag` field) while that block's own frame was open, then
  reading that already-resolved field back later is a purely structural,
  scope-free walk — the same shape a separate boolean-only structural
  pass (e.g. tail-call marking) already has. Confirmed in Whence (round
  276, v0.14.5): a fn body whose tail is `if c { print } else { print }`
  was flagged three rounds earlier as "can't simply run after the fact"
  and left as a documented, un-revisited gap — it turned out to need
  zero new stacks, just reading `if_node.then.tail_alias_tag` and
  `if_node.otherwise.tail_alias_tag` (recursing through an `else if`
  chain) and requiring an EXACT match across every arm, not "any arm",
  to stay sound (an approximate match would create a false negative that
  looks like a fix but is actually unsound). Before writing off a branch
  construct as "needs interprocedural analysis," check whether the
  per-block fact you need is already sitting on the AST node from an
  earlier pass.

- **A scope-mirroring analysis can be extended hop-by-hop to track a value
  across function-call boundaries with the SAME repeatable recipe every
  time — but the recipe has a hard edge, and knowing where that edge is
  matters as much as the recipe itself.** Validated identically across
  four consecutive rounds of the same feature family (Whence v0.14.9:
  param called directly; v0.14.10: the anonymous-fn variant; v0.14.11: a
  same-body rename of the param, then called; v0.14.12: the param
  returned across a call boundary, then called by the caller) — each
  landed in its own round with zero rework of the others: (1) add ONE new
  scope-stack, pushed/popped at the IDENTICAL per-block/per-fn-definition
  sites every EXISTING stack in the family already uses (never invent a
  new push/pop site); (2) write a resolver that combines a fact recorded
  ONCE at the callee's own definition (independent of any call site) with
  the ACTUAL arguments at ONE specific call site, to decide whether that
  one call site is sound; (3) once the resolved fact lands in the
  ordinary alias-tracking table the check-site code already reads, the
  actual verdict dispatch needs ZERO new branches — the same
  fact-producer/fact-consumer split makes 3 of the 4 rounds land with no
  changes to their own readers at all. Keep each hop deliberately narrow
  (bare-NameRef only, no widening to `if`/`else` tails, no crossing into
  an ancestor fn's own frames — see the next pitfall) and pin its boundary
  with an explicit negative test, not prose. The recipe's limit is just as
  load-bearing: three consecutive rounds (302, 306, 308) independently
  re-confirmed the SAME two remaining gaps — an argument reaching the
  target through a SECOND function call, and a dynamic call graph (a
  different, unrestricted fn performing the effect) — are NOT another
  one-hop slice, because both need the verdict to depend on WHICH call
  site you're checking (per-call-site specialization) rather than only on
  the callee's own definition, or else an unsound over-approximation.
  Don't spend a round trying to force either into this recipe without a
  real design sketch first — every round in this family that considered
  it said so explicitly rather than attempting a partial fix.
- **A flat scope-stack that spans every open block AND fn (not just the
  currently-open one) can let an ENCLOSING fn's own recorded fact leak
  into an INNER fn's check via a coincidental name collision.** If a
  resolver for a hop-tracking stack (the recipe above) walks the whole
  stack innermost-first with no lower bound, and an inner fn happens to
  redeclare a name the resolver would otherwise still find further out,
  the walk can attribute a call inside the inner fn to the OUTER fn's own
  tracked value — one that isn't even among the inner fn's own declared
  parameters. Fix by locating the currently-open fn's own params frame by
  IDENTITY inside the base scope stack first, and bounding the hop-stack
  walk to that index and everything pushed after it, never crossing into
  an ancestor fn's own frames (Whence round 306, v0.14.11's
  `_resolve_param_alias`). Write the specific cross-fn-boundary
  misattribution case as its own test — it's easy for this to look
  harmless (the misattributed name is dead data a later step never
  visits) rather than prove it can't ever flip a verdict.
- **Adding a genuinely nondeterministic builtin (`rand`, a clock, real I/O)
  to a total, differentially-tested language breaks every oracle that
  assumes a program's behavior is a pure function of its source text —
  fix this by making the builtin REPRODUCIBLE, not by special-casing the
  oracles.** A three-way differential (three independently-constructed
  interpreters), a guest/host self-hosting comparison, and a fast/slow
  reference-diff bench all silently assume re-running the same source
  yields the same result; a builtin that draws from OS entropy breaks
  that assumption for every one of them at once, and the fix looks like
  it needs a special case in each. Instead give the interpreter its own
  seeded stream at construction time (`Interpreter(seed=0)` →
  `self._rng = random.Random(seed)`, a per-instance field, not a module-
  global) and have the builtin draw from `interp._rng` — two interpreters
  built at the same seed then draw the identical sequence, so every
  oracle that already compares two interpreters' output keeps working
  with ZERO code changes, because "same input source" now really does
  imply "same output" again (the seed is part of the input). This is a
  deliberate divergence from mainstream languages (most seed `random()`
  from OS entropy by default) — the same value judgment deterministic-
  replay execution environments make, and the only choice under which
  real randomness and full-determinism testing coexist without a special
  case anywhere (Whence round 294, v0.14.8's `rand()`: `Interpreter.
  __init__(..., seed=0)`, `whence/interp.py`'s `rand` node reading
  `interp._rng.random()`). Decide this BEFORE writing the builtin, not
  after an oracle starts flaking — retrofitting a seed onto an already-
  shipped entropy-backed builtin means every prior recorded oracle run
  is now unreproducible.

- **When a differential/self-hosting comparison's two sides are built by
  two different code paths, an unstated default-value MISMATCH between
  them silently reclassifies real bugs as expected divergence instead of
  causing a visible failure.** If the comparison already has a named
  exemption bucket for "one side legitimately has a lower resource
  ceiling than the other" (e.g. a guest evaluator paying more host
  frames per guest call than the direct host path, so it can exhaust a
  depth/step budget the host doesn't), then giving each side's builder
  its own independent default for that ceiling — one defaulting to
  `None` (resolves to the interpreter's own unrelated top-level default,
  e.g. 20000) and the other defaulting to a much lower, deliberately-
  chosen comparison value (e.g. 2000) — silently WIDENS that exemption:
  a real mismatch that would surface as a genuine divergence between a
  depth-2000 host and a depth-2000 guest instead gets swallowed as
  "expected depth skew" between a depth-2000 host and an unrelated
  depth-20000 guest. This is a coverage gap, not a crash or a false
  positive, so nothing in a green test suite flags it — it only shows up
  as "this class of bug can no longer be found," which is easy to miss
  for many rounds. Confirmed in Whence's SWE-loop harness (round 289
  flagged it, round 295 fixed it): `GuestHarness.__init__` defaulted
  `max_depth=None` while `oracle_self_eval`'s own host-side default was
  `2000`; the fix was making the guest builder take the SAME `max_depth`
  the host side already uses as an explicit, threaded parameter (and
  keying any cache on `(pkg, max_depth)`, not just `pkg`, so two
  different depths for the same package never silently share one
  cached instance) rather than letting each side pick its own default.
  When auditing a differential harness, grep both builder call sites for
  every parameter that has a *named* exemption bucket in the comparison
  logic and confirm both sides pass the same value — an exemption bucket
  existing at all is evidence a mismatch has bitten this comparison
  before.

## Verification
- `python3 -m pytest tests/ -q` → all green, runtime < 1s.
- Every example runs with documented exit code; the deliberately-failing one
  exits 1.
- Feed the parser garbage (`let = 5`, `"unterminated`, `if x { 1 }`) → clean
  error with line/col, exit 2, never a Python traceback.
