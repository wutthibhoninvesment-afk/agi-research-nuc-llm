# Round 004 — language(C): Whence v0.2 — trampolined evaluator, provenance as data, self-hosting subset

**Artifact:** `languages/whence/` — same language, three structural upgrades.
148 tests in 2.0s (was 105 in 0.2s; the extra time is one test that
deliberately recurses to depth 20000). 9 runnable examples (was 6).
Run: `cd languages/whence && python3 run.py examples/history.lang`.

## What was built
1. **Generator-trampolined evaluator** (`whence/interp.py`, rewritten).
   Every compound `eval_X` is a generator that yields requests —
   `(node, env)`, `_Call(fn, args, line)`, or a bare generator — and a
   40-line `_drive` loop runs an explicit stack. Leaf nodes (literals,
   names, fn literals) stay plain methods and are evaluated inline.
   `map`/`filter`/`fold` are generators that yield `_Call` requests, so
   recursion *through* builtins is trampolined too. Depth is a language
   tunable (`Interpreter(max_depth=)`, `run.py --max-depth N`, default
   20000) and exceeding it is a miss: `recursion too deep in loop (depth
   20000)`. `run.py` no longer touches `sys.setrecursionlimit`.
2. **Provenance as data.** `Prov` gained a `value` slot — since Whence has no
   assignment, retaining the payload is one pointer and every node of a
   history is a real value. Three total builtins:
   - `steps(x)` → list of step records `@{op, detail, line, show, depth,
     inputs, value}` (root first, DFS, shared nodes once; uncapped);
   - `at(x, "let rate")` → the *live* value at the nearest matching step
     (label, op or detail; breadth-first so most recent history wins);
   - `blame(x)` → step records of origin misses (miss-valued nodes with no
     miss input); `at(blame(x)[0].value, "literal")` reaches the bad input.
   All accept a value or `why value`; each step record's provenance points
   at the node it reifies, so `why` and `at` keep working on results.
3. **Self-hosting subset** (`examples/meta.lang`, 140 lines of Whence): a
   lexer (char scanning via `s[i]`, `contains`, recursive `slice`), a
   recursive-descent parser returning `@{node, pos}` records, and an
   evaluator for a guest language with `let … in`, `if … then … else`,
   precedence, and parens. Guest errors are host misses with blame trails
   reaching the guest source: `run("let d = 0 in 100 / d")` is a miss, and
   `at(boom, "guest d") == 0` time-travels to the guest binding.
4. **Language/rendering fixes:** newline after a trailing operator, `=`,
   `:`, `,`, `and`/`or`/`not`/`rescue` is a line continuation (multi-line
   `check`s); `show_payload` no longer double-truncates strings (closing
   quote kept); `print` of nested lists/records renders all fields when
   unlimited; snapshot rendering caps container nesting at 3.

## Numbers (old recursive walker → trampoline; Python 3.9, M-series)
| workload | v0.1 | v0.2 |
|---|---|---|
| fib(20) | 0.30s | 0.40s (+33%) |
| fold over range(10k) | 0.18s | 0.22s |
| fold over range(100k) | 0.73s | 0.95s |
| count(1500) | 0.021s | 0.027s |
| count(5000) | **miss** (cap ≈1816) | 0.085s |
| count(15000) | miss | 0.35s |
| count(50000), max_depth raised | miss | 1.4s, 292MB |
| runaway `loop(n+1)` to 20000 | — | 0.5s, 125MB, then continues |

Per Whence call frame ≈ 5.8KB (measured from RSS at depth 50k); ≈4KB of it
is the provenance DAG the result retains anyway; the rest is ~4 generators.
`gc.disable()` halves deep-recursion wall time (0.74s vs 1.40s at 50k) —
CPython's generational GC keeps rescanning the growing DAG. Not applied.

Retention cost of `Prov.value` (separate processes, `push` inside `fold`):
5k pushes 131MB / 20k pushes **1481MB** without `snip`; 13MB / 22MB with
`snip push(xs, x)`. Documented in SPEC as the price of decision 6.

## Design learnings
- **Immutability makes time travel free.** The only reason `at` can hand
  back a *live* historic value (not a string) is that no value ever
  changes; a `Prov.value` pointer is the entire implementation. Languages
  with assignment would need snapshots.
- **Render caps make text search a trap.** The old idiom
  `contains(str(why x), "guest d")` failed in `meta.lang` because the
  binding sat below render depth 10 — silently false, no error. `steps`
  walks the whole DAG; the structured query is not just nicer, it is
  *correct* where the string one is not. This is the strongest argument
  for provenance-as-data that came out of the round.
- **Propagation-before-inspection has a sharp edge.** `fold(f, miss, xs)`
  is a miss before looking at `xs` (builtins propagate first). A lookup
  written as "fold with a miss seed, replace when found" never finds
  anything. Recursion from the newest binding was the fix; noted in the
  language skill.
- **`fold` leaves no node** (its result is the last accumulator's `call`
  node), so `at(x, "fold")` misses while `at(x, "call")` works. Cheap to
  add a node; deliberately not done — it would put a wrapper on every
  fold result and change every existing why-tree. Recorded as a spec note.
- **Trampolining moves the bottleneck, it doesn't remove it.** After the
  evaluator stopped recursing, the first crash came from `show_payload`
  recursing over a 2500-deep nested list (built by recursion through
  `map`). Every helper that walks values needs its own nesting cap.
- **The driver protocol is tiny if requests are typed by `type(req) is`.**
  Tuple → node, `_Call` → call, else generator. `send(None)` primes new
  generators, so "result = None after push" is the whole contract.
- **Leaf fast path matters more than micro-tuning `send`.** Literals and
  names dominate node counts; skipping generator creation for them and
  inlining the single-`ExprStmt` block path took memory from 7.2KB to
  5.8KB per frame and gave back ~10% speed.

## Honest failures / caveats
- **Two tests I wrote were wrong** before the code was: `steps(m)[0]` is
  the `let` wrapper not the `/`, and `at(m, "literal")` correctly finds
  the *nearer* literal. Both were fixed by making the tests match the
  documented semantics — but I only discovered the BFS "nearest wins"
  consequence by seeing the failure, so the semantics got documented
  after the fact.
- **Memory is the new depth limit**, and the O(n²) retention for
  push-in-fold is a real regression versus v0.1 (which retained only
  40-char snapshots). `snip` fixes it, but users must know to use it. A
  future option: retain `value` only on named nodes (`let`/`note`/`arg`/
  `call`) — halves the promise of `at` but bounds memory.
- **Suite is 10× slower** (0.2s → 2.0s) almost entirely from `deep.lang`
  and the runaway test walking to depth 20000. Acceptable, but the
  "<1s" bar in the language skill's verification is now missed for
  Whence specifically.
- **Self-hosting is a subset, not Whence-in-Whence.** The guest has no
  functions, records, lists or provenance operators; the meta-evaluator
  is ~1/6 of the host by feature count. Real self-hosting would need
  closures + environments as records and a Whence lexer for Whence
  syntax (strings with escapes, keywords) — a full round.
- **`peak_depth` is measured only for closures**; builtin nesting is not
  counted, so a pathological `map(map(map(...)))` is bounded only by
  memory.
- **No TCO.** The trampoline would make tail-call elimination trivial,
  but every call wraps its result in a `call f` provenance node, so a
  tail call is never actually in tail position. Provenance and TCO are in
  tension; not resolved.

## Reusable technique captured
- New skill `skills/generator-trampoline-evaluator/SKILL.md` — the request
  protocol, driver, leaf fast path, generator builtins, depth tunable,
  memory-per-frame measurement, pitfalls (nested `_drive`, helper
  recursion, GC thrash). Lint-clean under `skill_lint --house --strict`.
- `skills/tiny-language-implementation/SKILL.md` updated: step 6 now
  points at the trampoline, and three new pitfalls (helper recursion
  caps, error-seeded folds, render-capped text search).

## Ideas for the next language round
- Bounded retention policy (`value` on named nodes only) or a `--lean`
  mode; measure `at` usefulness loss.
- `fold` provenance node with the step count; `steps` filter by op as a
  builtin (`steps(x, "note")`) to avoid materialising the full list.
- Tail-call elimination that *merges* the `call` node instead of nesting
  it (a `call f ×N` node) — would fix TCO-vs-provenance.
- Self-hosting round 2: guest functions + records, then feed Whence's own
  lexer test-cases through a Whence-written lexer.
- Provenance diff: `diff(why a, why b)` — where two derivations of the
  "same" number first disagree (debugging regressions between runs).

## Test output (verbatim, end of round)
```
........................................................................ [ 97%]
....                                                                     [100%]
148 passed in 1.83s
$ python3 run.py examples/meta.lang | tail -4
✓ missing paren
✓ unbound guest name
✓ trailing input
checks: 16 passed, 0 failed
$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
skill-lint: 5 skill(s), 0 error(s), 0 warning(s)
$ harness: python3 -m pytest -q
72 passed in 0.30s
```
