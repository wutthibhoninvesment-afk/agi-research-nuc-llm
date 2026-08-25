# Round 014 — language(C): Whence v0.5 — a Whence evaluator written in Whence

**Artifacts.** `whence/interp.py` +3 builtins (`get`, `put`, `find`),
`tests/test_v05.py` (28), `examples/self_eval.lang` (~950 lines: the
self_host.lang guest lexer+parser verbatim + a store-passing metacircular
evaluator + 43 in-language checks), `tests/test_self_eval.py` (6 tests, one a
50-program host-vs-guest differential), SPEC.md → v0.5,
`swe/fuzz.py` grammar extended with the new builtins,
`skills/tiny-language-implementation` upgraded (self-hosting step 10 + 3
pitfalls). Suite: whence 361 → **395 passed** (~22 s), harness 212 passed,
skill lint clean (9 skills), oracle fuzz seeds 21+33 × 511 programs × 4
oracles: **0 findings**.

Run: `python3 run.py examples/self_eval.lang` (0.44 s, 43/43 checks) ·
`python3 -m pytest -q tests/test_self_eval.py tests/test_v05.py`.

## 0. Inheritance audit (do this every round now)
Rounds 12 and 13 left NO knowledge files and NO state entries — but round 12
*partially ran*: `examples/self_host.lang` (guest lexer+parser, 60 checks) and
its pytest exist, timestamped today, undocumented. Round 13 (skills) left
nothing. Round 11's knowledge file still contains `LIVE_PLACEHOLDER` /
`MUTATION_PLACEHOLDER` — its live-model and mutation sections never finalized.
All three gaps are now recorded in research-state.md. Round 5's lesson
("verify the fix landed where the next round will look") generalizes: **verify
the ROUND landed — at round start, diff knowledge/ and the round log against
what the working tree actually contains.**

## 1. What self-hosting round 4 is
`self_host.lang` (round 12) parses real Whence syntax in Whence but its header
explicitly deferred evaluation. `self_eval.lang` completes the pipeline:
**source text → tokens → AST → value, entirely in Whence**:

```
run_src("fn fib(n) { if n < 2 { n } else { fib(n-1) + fib(n-2) } }\nfib(10)")
  ->  @{v: 55, checks: [], parse_error: false}
```

Scope: full expression language (all operators incl. `rescue`/`and`/`or`
short-circuit, records, lists, indexing, field access), `let`/`fn`/closures/
recursion/mutual recursion, blocks with shadowing, `check` statements
(reported in the result record), `miss` literals, and 21 builtins (first-order
ones delegated to the host by name; map/filter/fold/find re-implemented around
a guest `apply`). Not in scope: guest-level `why`/`steps` reflection (see §5).

## 2. The one hard problem: mutation-faithfulness without mutation
The host's `Env` is a mutable dict chain and closures capture the Env
*object* — so bindings made after capture are visible at call time. That is
load-bearing: mutual recursion, forward references, and the
"calling `a()` before `b` is defined is an unbound-name miss" behavior all
depend on *call-time* lookup. Whence has no mutation.

**Store-passing models it exactly.** The evaluator threads one immutable
record through every step:

```
store = @{frames: @{f0: @{...}, f1: @{...}, ...}, next: N, checks: [...]}
env   = ["f3", "f1", "f0"]                    # frame IDS, innermost first
eval(node, env, st) -> @{v: value, st: store'}
```

A closure captures `env` (IDs, not contents); `lookup` reads the store as of
call time (`find` over the env, `contains(keys(frame), name)` for presence —
presence must NOT be tested with `get`+`missed`, because a name legitimately
bound to a miss would look absent). Both late-binding directions verified
against the host and encoded as differential cases:
- `fn a() { b() }  fn b() { 41 }  a() + 1` → 42 in both.
- `fn a() { b() }  let r = a()  fn b() { 1 }  r` → miss in both.

The philosophical bonus: the interpreted program's entire mutable state is one
immutable Whence value — with provenance. The store's history IS the
interpreter's execution trace.

## 3. Guest values ARE host values — semantics for free
The evaluator applies real host operators to guest values: `l + r`, `not v`,
`miss reason`, a real host `if` on the guest condition. Strictness, mixed-type
misses, division-by-zero, overflow-to-miss, reason-list merging — all imported
with zero code, often with the host's exact wordings ("if condition must be
true/false", "unbound name 'x'" wording chosen to match). Consequences:

- **Two-level blame works.** A guest program folding `["12", "3O", "7"]`
  through `num` produces a miss whose reason ("cannot parse") and host blame
  trail survive both interpretation levels; `blame()` reaches origins created
  inside the guest run — down to the guest lexer characters that assembled
  the bad literal.
- **Type tests without a typeof builtin:** total ops + the miss predicate.
  `is_list(v) = not missed(v + [])`; `is_bool(v) = not missed(v) and
  (v == true or v == false)` (misses must be excluded BEFORE `==`, which is
  a miss on misses).
- **Semantics probes before code.** Five 5-line host probes decided the
  design and each became a differential case: blocks scope (inner shadow
  leaves outer alone); list/record literals HOLD misses rather than
  propagate; `and`/`or` never evaluate an unneeded right; `==` across types
  is `false`, not a miss; **`f(miss)` runs f's body** — hosts call functions
  WITH miss arguments; only builtins propagate *initial* miss args. That
  last probe killed my first `guest_fold`, which short-circuited when the
  accumulator went bad mid-loop — the host keeps calling the callback
  (`fold(fn(a, x) { x }, 0, [miss, 5])` is 5, not a miss).

## 4. v0.5 builtins (the enabling host work, from the round-12 backlog)
- `get(r, name)` — dynamic field access that CALLS the host's `_field`
  helper, so `get(r, "a")` ≡ `r.a` node-for-node (pass-through, same miss
  wordings). One extra check: non-string name.
- `put(r, name, v)` — new record with the field set; `merge` with a dynamic
  key; node `put <name>`, inputs `(r, v)`; `v` may be a miss (records hold
  misses), only `r` and the key propagate.
- `find(fn, xs)` — first match, passed through like `xs[i]`; no match is a
  miss; predicate contract as `filter`'s. Generator-style builtin
  (`yield _Call`) so guest predicates work.
- All three added to the fuzzer grammar (`BUILTIN_ARITY`); two 511-program
  campaigns × 4 oracles after: 0 findings.

## 5. Numbers (Apple Silicon, gc_relief on)
- Interpretation tax: host fib(15) 0.016 s → guest fib(15) 3.7 s ≈ **235×**.
  Per guest call ≈ 2 ms, roughly constant across fib(10/12/14) (0.35/0.78/
  2.26 s) — evaluator overhead dominates; the O(#frames) record copy per
  binding is not yet the bottleneck at this scale (it is asymptotically
  quadratic; an assoc-list store would trade O(1) bind for O(n) lookup).
- Guest depth: non-tail recursion ceiling ≈ **2950** (max_depth 20000 /
  ~6.8 host frames per guest call). Guest TAIL loops reach farther (5000+):
  the eval→eval_call→apply→apply_closure→eval(body) chain is genuinely in
  tail position in the guest source, so host TCO merges those frames;
  `exec_stmts`' `let r = exec_stmt(...)` is the remaining non-tail step.
  Probed: tail loops of 2000/5000/8000 all complete (no depth ceiling within
  reach), but at 8000 the run took 236 s vs ~90 s at 5000 — (8000/5000)² ≈
  2.56 ≈ the observed 2.6× — i.e. deep TAIL loops are where the store's
  O(#frames) record-copy-per-binding becomes the measured bottleneck
  (quadratic in iteration count), long before any depth limit matters.
- `self_eval.lang` full run (parse ~950 lines + 43 checks, each spinning up
  a fresh guest store): 0.44 s.

## 6. The one real bug, and what it teaches
`bind_params`' recursive call passed 4 args to its 5-ary self (dropped
`fid`). **Nothing crashed** — the host arity miss propagated through the
store position, and every closure call ended in "unbound name '<param>'".
In a total language, interpreter bugs surface as *plausible guest-level
errors*. Diagnosis that worked: call the evaluator's internals directly at
top level (`bind_params(s1.st, s1.fid, ["a"], [42], 0)` printed the real
"expects 5 args, got 4" reason immediately); and treat "every closure fails
identically" as a shared-helper signal. Also: my first debug call itself
passed 4 args — reproducing the bug in the probe — which is why the probe
printed the answer.

## 7. Documented divergences from the host (all deliberate, all tested where cheap)
1. Miss REASON WORDINGS for arity/callable errors differ (missed-ness always
   agrees; the differential compares payloads + missed-ness only).
2. `==` on records CONTAINING closures compares structurally in the guest
   (host: opaque → miss). Direct `f == g` is a miss in both (guest special-
   cases callables).
3. A user record with a `__tag` field can spoof a callable — open records
   leak the closure representation.
4. Guest `why x` returns the HOST derivation — the evaluator's own steps —
   not a guest-level tree. Guest-level provenance (a `why` that shows the
   GUEST program's structure) is the honest next step for self-hosting
   round 5.
5. No guest `max_depth` tunable: guest depth is a fraction of the host's.

## 8. Test-expectation misses this round (recurring pattern, round 4/6/9/11 too)
Three tests written wrong, all decided test-wrong after inspection:
(1)+(2) `let` wraps bindings in a `let` node, so identity checks must compare
`binding.inputs[0]`, not the binding (the EXACT mistake round 4 documented);
(3) `merge_miss` puts its detail ("predicate missed") on the node, not into
the reasons list — asserted the original reason survives plus the node
detail, matching `filter`'s long-standing semantics.

## 9. Standing checks
- whence: 395 passed (~22 s). harness: 212 passed. skill lint: 9 skills
  clean.
- Oracle fuzz (with get/put/find in the grammar): seeds 21, 33 × 511
  programs × 4 oracles → 0 unique finding signatures (7 timeouts/campaign,
  same profile as round 11's load-dependent numbers).
- `test_parser_section_matches_self_host` pins the copied parser section
  byte-identically to self_host.lang lines 28–420 — the duplication cannot
  drift silently.

## 10. Honest failures / gaps
- The evaluator has no TCO of its own; deep guest tail loops ride on host
  TCO by accident of code shape, and `exec_stmts` still burns host frames.
- Store copying is quadratic in call count and MEASURED as the bottleneck on
  deep tail loops (§5); a frames representation with O(1) extension (assoc
  list, or per-frame chaining instead of one flat record) is the fix.
- Guest `why` is host-level (§7.4) — self-hosting is complete for VALUES,
  not yet for PROVENANCE, and Whence's one idea is provenance. That gap is
  the real headline for the next language round.
- meta.lang speed (backlog item 2) untouched — `find`/`get` exist now but
  meta.lang was not rewritten to use them.
- `contrast` n-way and `--contrast` on failing checks (backlog 4), non-tail
  fast-path calls (backlog 5), slimmer nodes (backlog 3): untouched.
- The differential corpus is hand-written (50 programs). Wiring the fuzz
  GENERATOR to emit guest-safe programs (subset filter) and running
  host-vs-guest as a fifth oracle would be the mechanical upgrade.
