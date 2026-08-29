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
   - **Also differential-test the PARSER layer, not just the evaluator.**
     If the guest's own parser runs at host level (no `run_src`/boxing
     involved — it emits plain records the same way `parse_whence`'s host
     twin emits plain AST nodes), canonicalize both sides' node kinds into
     one shared kind↔field table (built by grepping the guest's own
     `@{kind: ...}` literals) and diff the WHOLE tree, node for node, over
     a corpus of hand-written per-node-kind snippets plus every shipped
     example. This is cheap (both sides are already-real objects, zero
     unboxing) and catches a class of bug field-by-field spot-checks miss
     entirely — see the pitfall below.
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
  not to** — the guest lexer/parser is a syntax snapshot that doesn't grow
  with the host parser; twice in this program a feature's fuzz coverage and
  real guest parity landed multiple rounds apart. Full mechanism:
  [references/pitfall-history.md#host-feature-fuzzer-guest-parity-gap](references/pitfall-history.md#host-feature-fuzzer-guest-parity-gap).
- **When the guest evaluator is itself written IN the host language
  (self-hosting), a new builtin's guest support can be a straight
  delegation, not a reimplementation** — but every existing "what type is
  this value" probe must be re-audited for it (round 176). Full mechanism:
  [references/pitfall-history.md#guest-evaluator-in-host-language-delegation](references/pitfall-history.md#guest-evaluator-in-host-language-delegation).
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
  unrelated bug** (confirmed twice, Whence rounds 206/218). Full mechanism:
  [references/pitfall-history.md#self-hosted-dispatch-two-gates](references/pitfall-history.md#self-hosted-dispatch-two-gates).
- **A host builtin that returns a raw, unboxed record can silently break
  guest code that assumes every value is wrapped** — a second, independent
  gap from the name-resolution one above (round 218). Full mechanism:
  [references/pitfall-history.md#host-builtin-raw-unboxed-record](references/pitfall-history.md#host-builtin-raw-unboxed-record).

- **A scope-mirroring static analysis (parse-time effect/alias/purity
  checks) must record NON-matches explicitly, not just skip the write when
  there's nothing interesting to say** — the same bug shape as a cache that
  only writes on a hit, letting an inner scope fall through to an outer
  scope's stale match (Whence round 266). Full mechanism:
  [references/pitfall-history.md#scope-mirroring-must-record-non-matches](references/pitfall-history.md#scope-mirroring-must-record-non-matches).
- **Extending a scope-mirroring static analysis to recurse into a branch
  construct (`if`/`else`, `match`) often needs NO new scope-context
  plumbing** — check whether the branch is itself a block whose own fact
  was already resolved while ITS scope was still open (Whence round 276).
  Full mechanism:
  [references/pitfall-history.md#scope-mirroring-branch-construct-extension](references/pitfall-history.md#scope-mirroring-branch-construct-extension).
- **A scope-mirroring analysis can be extended hop-by-hop to track a value
  across function-call boundaries with the SAME repeatable recipe every
  time — but the recipe has a hard edge, and knowing where that edge is
  matters as much as the recipe itself.** Validated identically across
  four consecutive rounds (Whence v0.14.9-v0.14.12); a fact recorded once
  at the callee's own definition, combined with one call site's actual
  arguments, needs zero new dispatch branches once it lands in the
  ordinary alias table. The edge: three rounds (302/306/308) confirmed a
  SECOND function call and a dynamic call graph are NOT another one-hop
  slice, because both need the verdict to depend on WHICH call site,
  never over-approximate. Full mechanism (incl. how round 312 closed the
  first edge case and round 314 hit the second):
  [references/pitfall-history.md#hop-by-hop-value-flow-recipe](references/pitfall-history.md#hop-by-hop-value-flow-recipe).
- **A flat scope-stack that spans every open block AND fn (not just the
  currently-open one) can let an ENCLOSING fn's own recorded fact leak
  into an INNER fn's check via a coincidental name collision** — bound the
  hop-stack walk to the current fn's own frame index forward (Whence round
  306). Full mechanism:
  [references/pitfall-history.md#flat-scope-stack-cross-fn-leak](references/pitfall-history.md#flat-scope-stack-cross-fn-leak).
- **Adding a genuinely nondeterministic builtin (`rand`, a clock, real I/O)
  to a total, differentially-tested language breaks every oracle that
  assumes a program's behavior is a pure function of its source text —
  fix this by making the builtin REPRODUCIBLE, not by special-casing the
  oracles** (Whence round 294: a per-instance seeded RNG, not a module
  global). Full mechanism:
  [references/pitfall-history.md#deterministic-nondeterministic-builtin](references/pitfall-history.md#deterministic-nondeterministic-builtin).
- **When a differential/self-hosting comparison's two sides are built by
  two different code paths, an unstated default-value MISMATCH between
  them silently reclassifies real bugs as expected divergence** instead of
  a visible failure — a coverage gap a green suite can't flag (Whence
  rounds 289/295). Full mechanism:
  [references/pitfall-history.md#differential-harness-default-value-mismatch](references/pitfall-history.md#differential-harness-default-value-mismatch).
- **A "gap" a design sketch describes can actually be the analysis
  family's own founding, deliberately-tested boundary — the only reliable
  way to tell the two apart is to implement the sketch in full and run the
  WHOLE suite, not to re-read the sketch a second time.** Whence round 314
  implemented the dynamic-call-graph design sketch named above in full
  (mechanically identical in shape to every prior hop in the recipe) and
  it broke 7 already-tested, deliberately-designed programs plus 1
  diagnostic regression — not a bug in the new code, but proof the sketch
  silently collapsed two questions the family had always kept separate.
  Reverted in full; closed as by-design, not fixed as a bug. Full
  mechanism and the generalizable checklist:
  [references/pitfall-history.md#dynamic-call-graph-founding-boundary](references/pitfall-history.md#dynamic-call-graph-founding-boundary).
- **A self-hosted guest parser can byte-match the host on every
  SUCCESS-path field spot-check while silently diverging on a
  REJECTION-path field no spot-check ever exercises.** Whence round 320's
  first-ever whole-tree host-vs-guest AST differential (see step 10) found
  a real, years-old gap invisible to 66 hand-picked field assertions. Full
  mechanism:
  [references/pitfall-history.md#parser-differential-rejection-path-gap](references/pitfall-history.md#parser-differential-rejection-path-gap).

## Verification
- `python3 -m pytest tests/ -q` → all green, runtime < 1s.
- Every example runs with documented exit code; the deliberately-failing one
  exits 1.
- Feed the parser garbage (`let = 5`, `"unterminated`, `if x { 1 }`) → clean
  error with line/col, exit 2, never a Python traceback.
