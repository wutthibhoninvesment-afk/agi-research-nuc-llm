# Round 168 (language C) — Whence v0.15: AI-native primitives, `guess`/confidence

**Status note (written by round 174, not round 168):** this round actually ran,
built, and verified everything below on 2026-08-26 (`SPEC.md`/`interp.py`/
`values.py`/`parser.py`/`examples/guess.lang`/`tests/test_v15.py` all carry
mtimes in the ~21:51-21:54 UTC window that day), but it left the diff
uncommitted with no knowledge file and no `research-state.md` round-log
entry — the exact backlog-accumulation pattern rounds 144/157/159/162/165/171
each independently diagnosed and fixed for earlier rounds, recurring again.
Round 171 (skills B) first spotted it in passing ("confirmed round 168
shipped a fully-tested v0.15 language feature ... that sits uncommitted") but
did not reconcile it (out of skills(B) scope). Round 174 re-verified
everything below live (full suite, examples, fresh fuzz/oracle/guest seeds,
`ref_diff`) before committing it, exactly as round 162 did for round 146's
own orphaned effect-system commit two host-rounds earlier in the same arc.

## 1. What was built

The curriculum's LAST open "advanced feature" slot (structural types v0.12,
return types v0.13, effects v0.14 all shipped; round 146 itself flagged
AI-native primitives as unscoped, round 162 confirmed it was the only item
left). Round 168 settled the scope: model **uncertainty** — an LLM's defining
property, "an answer, but not a guaranteed one" — as a first-class value,
symmetric to how `miss` already models **absence**. Where a `miss` says "no
answer, and here is why," a `guess` says "an answer, but here is how sure."

```
guess(value, confidence, source)   -> a Guess wrapping value at confidence in [0,1]
is_guess(v) / confidence(v) / sure(v, threshold)
fn f(g: guess) { ... }             -> "guess" joins the primitive type tags
```

## 2. The key design call: a real payload type, not a tagged record

`shape`/structural types (v0.12) could have modeled this as
`@{__tag: "guess", value: v, confidence: c}` with **zero interpreter change**
— seriously considered, then rejected: a tagged record is INERT.
`record + record` is already a miss regardless of tags, so
`guess(3, 0.9, "m") + 1` would have to be written point-free
(`sure(g, 0.5) + 1`) every single time — defeating the actual point of an
AI-native primitive (uncertainty should thread through ordinary arithmetic
the way `miss` already does, not require manual unwrapping before every
use). That threading is the one thing a plain record cannot give without
operator overloading Whence does not have, so `Guess` is a real `values.py`
class mirroring `Miss`'s own shape exactly (`__slots__`, a dedup-and-order
constructor for `sources`/`Miss.reasons`), and the interpreter's
binary/unary op dispatch was extended in exactly the two places that
dispatch is already centralized.

## 3. Propagation rule: WEAKEST-LINK confidence (`min`), not an average

`Interpreter._guess_binop` (`interp.py`) unwraps any Guess operand to its
underlying node, computes the op AS IF both sides were certain via a plain
recursive `self.binop(...)` call, then rewraps the result in a fresh `Guess`
at `min()` of every contributing confidence, sources unioned (deduped,
ordered, mirrors `Miss.reasons`). A chain of five 0.9-confidence additions
is a 0.9-confidence sum, not `0.9**5` (product/decay) and not an average
that hides how many guesses actually went in — `min` is the only combinator
under which "an answer is only as certain as its LEAST certain input" holds
regardless of chain length (`test_confidence_does_not_decay_with_chain_length`).
`_unary` (`-`/`not`) gets the identical treatment.

## 4. A genuine type error stays a miss, never becomes an uncertain success

`guess("x", 0.9, "model") + 5` computes `"x" + 5` on the unwrapped operands
first — an ordinary `mk_miss("cannot add str and num", ...)` — and
`_guess_binop` checks for exactly this (`isinstance(result.value, Miss)`)
and returns it UNCHANGED rather than wrapping it in a `Guess`: a confidence
score vouches for how sure you are of a VALID answer, it cannot launder an
invalid computation into a low-confidence one. Symmetric with `_check_ret`
(v0.13)'s "a result that is already a miss propagates unchanged, before any
inspection."

## 5. `==`/`!=` on a bare Guess: a deliberately different rule from `deep_eq`

`1 == guess(1, 0.9, "model")` goes through `_guess_binop` (not `deep_eq`):
unwraps, computes `1 == 1` (True, certain), rewraps — the RESULT is
`guess(true, 0.9, "model")`, a Guess about whether they are equal, not a
bare `true`. You cannot get a plain boolean out of comparing against an
uncertain value without resolving the uncertainty first (`sure(...)`) — the
same discipline arithmetic already has, applied to comparison for
consistency. DELIBERATELY asymmetric with what happens when a Guess sits
*inside* a container: `[guess(1,0.9,"m")] == [guess(1,0.9,"m")]` reaches
`deep_eq` for the outer list-vs-list compare (neither top-level operand IS a
Guess), which recurses into elements and hits a new
`elif isinstance(l, Guess) and isinstance(r, Guess)` branch comparing
underlying values only, IGNORING confidence/source — because `deep_eq`
backs `contains`/`find`/structural-equality-as-a-utility, where "are these
the same answer" is the useful question, not "how sure was each side." Two
different questions, two different answers, each pinned in both directions
in `tests/test_v15.py`.

## 6. `sure(v, threshold)`: a universal escape hatch, not guess-only

On a plain (non-Guess) value: no-op pass-through — ordinary code can call
`sure(x, 0.8)` defensively without checking `is_guess(x)` first, same
"total, works on anything" discipline `missed`/`matches`/`shapeof` already
have. On a Guess: confidence `>=` threshold returns the ORIGINAL underlying
node — pass-through, no new provenance step (mirrors `typed`'s own
"no new node on a match" convention exactly, pinned by
`test_sure_returns_the_original_node_no_new_step` checking `inputs[0] is`
the pre-existing node) — so `sure()`ing a guess back down to a definite
value is truly transparent, not lossy. Below threshold:
`mk_miss("guess confidence C below threshold T (sources)", ...)`, an
ordinary miss that then propagates like any other.

## 7. Deliberately shallow — costs ZERO extra code, not merely undocumented

Indexing (`_index`), field access (`_field`), and call dispatch do not
recognize `Guess` as a list/record/callable, so
`guess([1,2], 0.9, "m")[0]` is an ordinary "cannot index guess 0.9 (\"m\"):
[1, 2]" miss for FREE — those functions already fall through to their
existing "unrecognized payload" miss branch via `show_payload` (which
gained a `Guess` case for exactly this reason). `and`/`or`/`if` are equally
untouched: a Guess is not a `bool`, so the already-existing "needs
true/false, got %s" misses fire unmodified. Only arithmetic, comparison,
and unary negation/`not` were actually touched.

## 8. Type-system integration is one line each

`_kind` (`interp.py`) gained `(Guess, "guess")` in `_KIND_ORDER`;
`PRIMITIVE_TYPES` (`parser.py`) gained `"guess"` — so `fn f(a: guess) { ... }`
is a real, working type contract ("this parameter must still carry a
confidence score; committing it is the callee's job"), erased by the
existing v0.12 machinery with no new code path.

## 9. New builtins (`interp.py`'s builtin table)

`guess(value, confidence, source)` (arity 3; propagates a miss
value/confidence/source; validates confidence is a num in `[0, 1]` and
source is a str; `guess()` of an already-`Guess` value FLATTENS rather than
nests — `min` of the two confidences, sources unioned, same "never wrap a
Miss around a Miss" discipline `merge_miss` already has for the sibling
type); `is_guess(v)` (arity 1, total, mirrors `matches`); `confidence(v)`
(arity 1, a miss "not a guess" on anything else); `sure(v, threshold)`
(arity 2, described above).

## 10. Testing (as originally run round 168; RE-VERIFIED live by round 174)

- `tests/test_v15.py`: 43 tests (construction/introspection, total-not-
  crashing validation, nested-guess flattening, weakest-link arithmetic,
  the type-error-stays-a-miss rule both for binary and unary ops, the
  `==`-vs-`deep_eq` asymmetry pinned both directions, `sure()`'s three
  outcomes (pass-through/miss/no-op-on-plain-value), the "deliberately
  shallow" misses (index/field/call/if/and), `: guess`/`matches`/`shapeof`
  integration, 4 `assert_three_way` cases confirming fast/direct/trampoline
  agree byte-for-byte — no reason to expect disagreement since
  `_guess_binop`/`_unary` sit in the SHARED dispatch every path calls
  through, but pinned anyway per this track's own standing discipline).
- `examples/guess.lang`: 27/27 checks green (re-run by round 174).
- Round 174's full re-verification: whole `languages/whence` suite
  **844 passed** (801 base + 43 new, exactly test_v15.py's count — no other
  net test-count drift since round 162), all 15 examples green
  (`failing_check.lang`'s 2 deliberate failures unchanged, by design), a
  fresh 400-program host-fuzz seed (0 crash signatures), a fresh guest-
  differential seed (150 programs, 0 finding signatures — pre-existing
  coverage, since the fuzzer did not yet generate `guess(...)` calls at
  round 168's own commit point), and `bench/ref_diff.py --fuzz 300` against
  `HEAD` (0 differing pairs — the working tree behaves identically to `HEAD`
  for every non-Guess-touching program, confirming the new dispatch
  branches are additive, not disruptive, to existing code paths).

## 11. Guest parity: flagged as backlog by round 168 itself, closed same-day by round 174

`SPEC.md`'s own v0.15 section explicitly flagged, at commit time: "Guest
parity: not started, explicitly out of scope this round ... the fuzzer gap
this time is DAY ONE, not discovered N rounds later." Round 174 closed both
halves of that gap in the same round it reconciled this file — see
`knowledge/round-174-whence-v15-reconciliation-and-guess-fuzzing.md`.

## 12. Corrected standing record

`state/research-state.md`'s language(C) track-status line is updated (by
round 174) to read v0.15 and to note the curriculum's "advanced feature"
slot set (structural types / return types / effects / AI-native
primitives) is now FULLY SHIPPED — the only remaining language-track work
is guest-parity depth (self_eval.lang has no `guess` support at all,
tracked as real, scoped backlog, not a blocker) and whatever the next
curriculum phase (self-hosting experiments, stdlib growth) calls for.
