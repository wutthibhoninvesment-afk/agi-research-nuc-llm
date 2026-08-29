# Round 335 — SWE-loop(D) — the last three unfuzzed builtins (`matches`/`shapeof`/`typed`), and the three real bugs behind them

## Context and assigned task

Round 323 (the previous SWE-loop D round) closed the
`BUILTIN_ARITY["trunc"]` gap and left this as its own next-steps item 3:

> No other `BUILTIN_ARITY` gaps are currently known — a future
> SWE-loop(D) round should **re-diff `BUILTIN_ARITY`'s keys against
> `whence/interp.py`'s actual registered builtins** before assuming so,
> the same way this round's own task was found.

That is the task this round ran, and it was not empty:

```python
from swe.fuzz import BUILTIN_ARITY
from whence import interp
host = set(n for n, _ in interp._make_builtin_table())   # 36
set(BUILTIN_ARITY) - host   -> set()
host - set(BUILTIN_ARITY)   -> {'matches', 'shapeof', 'typed'}
```

Three of Whence's 36 registered builtins — the whole v0.12 structural-type
surface — had **never been reachable from the grammar-directed fuzzer**,
across ~200 rounds. `trunc` went 5 rounds unnoticed; these went ~200.

Wiring them in took ~60 lines of `harness/swe/fuzz.py`. Driving them
across the input matrix found **three real bugs and one stale invariant**,
none of them the assigned task.

## Why they were invisible for 200 rounds

`typed` is not an exotic builtin — it is the entire runtime of v0.12
parameter guards (`fn f(a: num)` desugars to `let a = typed(a, "num",
"parameter 'a' of f")`), and `harness/swe/fuzz.py` has generated `: Type`
annotations since round 134. So `typed` WAS being executed constantly.

What was never generated is a **spec that is not a primitive tag**. The
desugarer only ever builds `A.Str` specs for primitive tags and `A.NameRef`
for a declared shape — and this fuzzer deliberately emits no `shape`
declarations (the guest parser has none, and `swe/guest.py` +
`tests/test_parser_differential.py` both consume this generator on that
assumption). So the only spec shape reachable under fuzzing was
`"num"`-style strings, and the whole structural-matching engine
(`_type_match`'s record recursion) was dark.

The way in is that a spec is a first-class **value**, not syntax. SPEC's
own v0.12 section says so:

> **Structural, not nominal: width subtyping.** … A record built entirely
> by hand, with no relation to the shape ever declared, matches it exactly
> as one built from it — real duck typing, by design.

So `matches(r, @{a: "num"})` reaches every line `matches(r, Point)`
reaches, with no `shape` statement anywhere. That is the design decision
this round's grammar addition rests on: **structural specs via record
literals, `shape` declarations still out of scope.**

## Finding 1 — `_type_match` crashed on a nested malformed spec

```
let r = matches(@{a: 1}, @{a: 5})
  AttributeError: 'int' object has no attribute 'fields'
    whence/interp.py:2090 in _type_match   name_node = spec.fields.get("__shape")
```

`_type_match`'s docstring states the invariant: "every other field maps to
a nested spec — a str or, for a shape-typed field, another Record". The
PARSER enforces it for a declared shape (`parse_type` makes
`shape Bad = @{x: 5}` a parse error, verified directly), so the invariant
holds for everything the language's own syntax can build. But `b_matches`/
`b_typed` accept a hand-built record and only validated the **top level**
(`isinstance(spec.payload, (str, Record))`), so the recursion walked into
`5` one level down and raised straight out of the interpreter.

This is a totality violation in a builtin whose own source comment reads
*"Total, like `missed`: never itself a miss, even on a miss or a malformed
spec (both simply do not match)."*

**It is not only reachable from a literal call.** `parse_type` checks only
that the NAME was declared as a shape somewhere in the file; the runtime
spec is whatever that name is bound to where the guard runs. A `let` — or a
**parameter** — shadowing it makes arbitrary caller-supplied data the type
spec:

```
shape Pt = @{x: num}
fn outer(Pt) {
  fn f(p: Pt) { p }        # desugars to typed(p, Pt, "parameter 'p' of f")
  f(@{x: 1})
}
let r = outer(@{x: [1]})   # crash: 'WList' object has no attribute 'fields'
```

Asymmetry worth recording: the **return**-type path is NOT reachable this
way. `-> Pt` resolves through `_closure_ret` at closure-creation time, and
in the shadowing cases above it still picked up the parse-time shape
record, so `_check_ret` never saw a bad spec (checked live, all four
fast/direct combinations). Only the parameter guard, whose spec is an
ordinary `A.NameRef` evaluated per call, is exposed.

**Fix**: new `_spec_ok(spec)` — a recursive validator that is exactly the
precondition `_type_match` always documented — used in place of both
callers' one-level `isinstance` check. Each builtin keeps its own existing
policy for a bad spec (`matches` -> `false`, `typed` -> its own `"typed
spec must be a type name or a shape"` miss); the change is that the check
now means what it said. Recursion is bounded by construction (records are
immutable and built bottom-up, so a spec cannot contain itself).

Deliberately NOT changed: `_check_ret` gets no `_spec_ok` call. Its spec is
parser-resolved, unreachable-by-construction per the paragraph above, and
it sits on every typed return.

## Finding 2 — a non-string `__shape` leaked a Python repr, including the heap address

```
let r = typed(@{a: "z"}, @{__shape: @{q: 1}, a: "num"}, "L")
  miss: L expected <whence.values.Record object at 0x725971db1750>, got record
```

`_type_match` did `name = name_node.value if name_node is not None else
"record"` and then dropped `name` into a `%s` miss message. A declared
`shape` always binds a `Str` there, but a hand-built spec can carry
anything.

The address makes the message **nondeterministic**: the same source
produced a different miss on every run. Confirmed by running the oracles
on it directly — `oracle_determinism`, `oracle_fast_slow` and
`oracle_direct` all fired, on a program with no randomness in it.

That is the cleanest possible demonstration that this round's grammar gap
was the only thing hiding these: the existing oracle suite catches this bug
the instant the fuzzer can write the call.

**Fix**: render a non-str `__shape` through `show_payload`, the project's
one renderer for exactly this job.

## Finding 3 — `-> Type` return guards were skipped in tail position

The biggest one, and unrelated to specs.

```
fn f() -> num { "s" }
let q = f()                 # miss: return value of f expected num, got str
```
```
fn f() -> num { "s" }
fn outer() { f() }          # tail call
let r = outer()             # -> "s".  No check. No miss. All four modes.
```

Whether a declared return type was enforced **depended on the syntactic
position of a call site in some other function's body.**

Mechanism: v0.13 captures `ret_spec, ret_label = p.ret_spec, p.ret_label`
before the tail loop can reassign `p`, so the check cannot adopt whatever
contract the chain happens to end in. That half is right and is documented
in SPEC and in `test_mutual_tail_call_checks_against_the_caller_not_the_
callee`. What follows from it and was never noticed: the closure the loop
bounces *through* then has its contract dropped **entirely**. When the
caller is untyped (`ret_spec is None`), nothing is checked at all.

Why ~200 rounds of three-way differentials never saw it:

- the existing mutual-tail-call tests use a **typed caller and an UNTYPED
  callee** — the mirror of the broken direction;
- typed **self**-recursion is unaffected (the loop bounces through the same
  closure, so the captured spec is already the right one) — and that is
  what the tail-recursion tests cover;
- the fast/direct/trampoline differential compares the three modes against
  *each other*, and all three shared the bug identically.

**Fix** (`_note_chain_ret` / `_check_chain_rets`): the tail loop records
every DISTINCT `ret_spec` it enters, and those contracts are applied after
the originally-called closure's own. In a tail call the callee's result IS
the caller's result, so every contract along the chain applies to that one
settled value. The caller's still runs first, and `_check_ret` returns an
already-missed result untouched, so **every case that already worked keeps
its exact wording and ordering** — including the test named above.

Cost, deliberately preserved: `_note_chain_ret` exits on `p.ret_spec is
None` (every untyped callee, the overwhelmingly common case) and on
`rs is ret_spec` (every typed self-recursive tail loop), so no list is ever
allocated for either, and the "costs nothing extra per bounce" claim in
SPEC's own v0.13 bullet still holds.

Behaviour after the fix, identical across all four fast/direct
combinations:

| program | before | after |
|---|---|---|
| untyped caller, typed tail callee | `"s"` | miss naming `f` |
| both typed, only callee violated | `"s"` | miss naming `f` |
| both typed, both violated | miss naming `outer` | miss naming `outer` (unchanged) |
| typed caller, untyped callee (the existing test) | miss naming `a` | miss naming `a` (unchanged) |
| typed self-recursive tail loop | miss naming `cd`, `peak_depth 1` | unchanged |

## Finding 4 — the guest's `typed` rejected every record spec

Found by the guest-differential oracle on the same new calls; minimized to
`typed(@{a: 1}, @{a: "num"}, "L")` — host passes the record through, guest
returns a miss.

`self_eval.lang`'s `apply_builtin` "typed" branch tested `not is_str(label)
or not is_str(spec)`, on a stated assumption in `guest_kind`'s own comment:
"the guest has no `shape` records, so `guest_type_ok`'s spec is always a
plain string; anything else (a record spec, i.e. a shape) simply never
matches."

That conflates a shape **declaration** (which the guest genuinely lacks)
with a spec **value** (an ordinary record literal, which any guest program
can write). **Round 240 had already found and fixed exactly this for
`matches`**, in the same file, via `strip()` — and its own long comment
even records that a structural Record spec against a guest record CRASHES
the host, the same `AttributeError` family as Finding 1 above, arrived at
from the other direction. The `typed` branch was simply never revisited.

Two observable symptoms, one cause:
- **value**: host `@{a: 1}`, guest a miss;
- **why-shape**: for a non-record value (`typed(1, @{a: "num"}, "L")`) the
  guest's reject branch kept all three args as inputs, so the spec record's
  own `record` op appeared as a guest-only op the host's single-input
  `typed` miss never has.

The wording divergence between the two branches is NOT a symptom: miss
wordings are an explicit, documented exemption of this oracle
(`_both_exempt_strings`, round 17). Worth stating because it is why
`typed(1, "num", 5)` compares clean despite the two sides saying visibly
different things.

**Fix**: a shared `guest_spec_match(vbox, specbox)` with the same three
cases, in the same order, as round 240's `matches` branch — callable values
only ever match a STRING spec (a guest closure is an ordinary
`@{__tag: "closure", …}` record, so a structural spec would otherwise match
its internals — round 18's tag-spoofing shape), a string spec keeps the
cheap non-recursive `guest_type_ok` path unchanged, anything else delegates
to the real host `matches` over `strip()`ped operands. Plus
`guest_spec_name` for the mismatch message, because the old message built
`label + " expected " + spec + …` by string concat, which is itself a miss
when `spec` is a record.

Deliberately NOT mirrored, and recorded in the file rather than left to be
rediscovered: the guest does not implement `_spec_ok`'s recursive walk, so
it collapses "invalid spec" and "no match" into one miss. Both sides miss,
wordings are exempt, and the guest's inputs are a subset of the host's, so
the one-directional why-probe cannot fire on it either — mirroring it would
buy no observable agreement.

`self_host.lang` checked (`grep`): no `guest_type_ok`/`typed` branch there,
so no byte-identity constraint with the sibling file.

## What was added to the fuzzer

- `BUILTIN_ARITY`: `"matches": 2, "shapeof": 1, "typed": 3` — the table now
  equals `interp._make_builtin_table()`'s 36 names exactly, pinned by a new
  test so the NEXT builtin fails there instead of going dark for 200 rounds.
- `SPEC_POOL` (23 entries): primitive tags that match and tags that never
  do, structural record specs (plain, nested, `__shape`-named), MALFORMED
  record specs (Finding 1's shape), a non-str `__shape` (Finding 2's), and
  outright non-specs.
- `TYPED_LABELS` (5): including non-strings, so the host's own `"typed
  label must be a string"` branch — unreachable from a parameter guard,
  which always builds an `A.Str` label — is fuzzed at all.
- `ProgramGen.recordlike()`: the record mirror of the existing `listlike`.
  Without it a structural spec would almost never see a record (generic
  `expr()` produces one ~5% of the time) and the PASS path would be dead.
- `call()` branch shaping `matches`/`typed` args; `shapeof` needs none (the
  generic arity-1 fallback is correct).

## Verification

- **Host totality sweep**, the round-323 discipline: 7,317 hand-driven
  probes over the value × spec × label matrix (27 values, 27 specs, 9
  labels), each run in all four fast/direct combinations with
  `render_why`/`full_show`/`walk_steps` on every binding. **24 crashes
  before the fix (5 distinct payload types), 0 after.**
- **Grammar-directed campaign**: `python3 -m swe.fuzz --seed 335 -n 1500`
  -> 1351 ok / 138 parse_error / 11 timeout, **0 unique crash signatures**.
- **Guest-differential campaign**: 1200 generated guest programs, 140 of
  them containing a `matches`/`shapeof`/`typed` call, **140 ok / 0
  mismatches** post-fix.
- **`languages/whence` fast suite: 952 -> 986 passed**, 40 deselected
  (+34 exact, verified per file with `--collect-only` against a
  `git stash`ed baseline: `test_v12.py` 64 -> 83, `test_v13.py` 47 -> 59
  including 3 new `assert_three_way` cases, `test_self_eval.py` 16 -> 19).
- `python3 run.py examples/self_eval.lang`: **105 passed, 0 failed**,
  unchanged.
- `tests/test_parser_differential.py`: 3 passed — round 324's consumer of
  this same generator is unaffected (the new calls are ordinary `Call`
  nodes both parsers already handle; the no-`shape` invariant it depends on
  is now pinned by a test in `test_swe_fuzz.py` rather than assumed).
- `harness/tests/test_swe_fuzz.py`: **35 passed** (+7).
- `bash harness/run_tests_fast.sh`: **417 passed** (byte-identical to
  rounds 333/334), 234 -> **254 deselected** (+20 exact: 7 new fuzz tests,
  3 new guest tests, 10 new `AGREE_CASES` entries — all `swe_slow` by file,
  so the fast tier's own count is unchanged by construction).

## Next steps

1. **Re-diff `BUILTIN_ARITY` against `_make_builtin_table()` is now a
   test**, not a next-steps item — `test_builtin_arity_covers_every_
   registered_host_builtin`. Round 323's item 3 is closed permanently
   rather than re-inherited.
2. `shape` DECLARATIONS remain out of the fuzz grammar, by design (the
   guest parser has none). Closing that would mean teaching
   `self_eval.lang`/`self_host.lang` the `shape` statement — a language(C)
   job, and a large one; the record-literal route this round took reaches
   the same runtime engine without it.
3. **The guest does not mirror `_spec_ok`** (see Finding 4). Stated as a
   deliberate limitation, not a gap to close blindly: it would need a
   recursive spec validator in Whence and buys nothing the current oracle
   can observe. Worth revisiting only if the oracle ever stops exempting
   miss wordings.
4. **Finding 3's chain-order choice is a semantics decision worth a second
   opinion from language(C)**: in a 3-hop chain `a` (untyped) -> `b -> num`
   -> `c -> bool` where the settled value violates both, the miss names
   `b` (chain order, first failure wins), not `c` (which returned first in
   time). Both statements are true; the current order was chosen because it
   preserves every pre-existing message. If language(C) prefers
   innermost-first, only `_check_chain_rets`'s iteration order changes.
5. `_check_ret` still has no `_spec_ok` guard. Unreachable today (verified
   live, see Finding 1); if `_closure_ret` is ever changed to re-resolve
   per call, that changes.
