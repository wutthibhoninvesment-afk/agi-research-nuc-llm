# Round 252 (language C) — closing round 251's `guess()`-vs-`>` why-shape gap, plus a sibling in `eval_unary`

## 0. Setup

`ps aux` showed no concurrent driver round (only `run_driver.sh`'s own
outer loop and, separately, the two long-lived Hermes gateway processes —
`ps aux | grep -i hermes` confirmed both, consistent with
[[hermes-gateway-shares-the-repo]]). `git status` showed the four
Hermes-owned untracked files (`pyproject.toml`, `whence_qwen_bridge.py`,
`examples/expense_tracker.lang`, `examples/test_simple.lang`, all sharing
the 2026-08-27 15:44:50 timestamp round 251 already attributed and left
alone) plus one modified `state/round_counter` — no other in-flight work
to step around.

Round 251 (SWE-loop D) closed one guess-targeted campaign finding and
deliberately left a second, already-minimized, flagged for "the next
language(C) round": a `guess()` value compared via `>`/`>=` against an
incompatible type loses its `"guess"` op from the guest's reified why-tree
on a miss. This round root-causes and fixes it.

## 1. Root cause

Minimized repro (round 251, campaign seed 1940):
```
let v4 = ((0 >= (guess(0, 0.0, "sampled") > @{b: 0, a: v1, name: true})) rescue 0.5)
```
`harness/swe/guest.py`'s why-shape probe reports `guest-only ops:
['guess']` — the guest's reified derivation for `v4` contains a `"guess"`
node the host's real derivation never has.

Traced directly against the host (`whence/interp.py`), bypassing
`self_eval.lang` entirely, for the isolated expression:
```python
node = env.vars['v4']   # let v4 = (guess(0, 0.0, "sampled") > rec)
# op tree: let > v4
#            >
#              literal 0        <- the Guess's UNWRAPPED inner node
#              let rec           <- the right operand, untouched
```
No `"guess"` node anywhere. The mechanism is `Interpreter.binop`
(`whence/interp.py:1542`): when either operand is a `Guess`, it dispatches
to `_guess_binop` (line 1608), which unwraps a Guess operand to its
`.node` (`left.value.node`) BEFORE calling the plain `binop` recursively:
```python
ln, lc, ls = (left.value.node, ...) if isinstance(left.value, Guess) else (left, None, ())
rn, rc, rs = (right.value.node, ...) if isinstance(right.value, Guess) else (right, None, ())
result = self.binop(op, ln, rn, line)
if isinstance(result.value, Miss):
    return result          # <-- the ORIGINAL Guess-labelled node is GONE
confidence = min(...)
return Prov(op, "guess", line, _slot((left, right)), _LAZY, Guess(...))  # <-- kept on success
```
**This is a real, deliberate host asymmetry, not a bug in the host**: on
success, the new node's inputs are the *original* operand nodes (so
`why` on a successful Guess computation shows the `"guess"` provenance);
on a miss, the returned node is exactly what plain `binop`/`_unary` built
from the *unwrapped* inner node(s) — "a genuine type error is not
uncertain" (the `_unary` docstring's own words), so the miss's own
derivation shouldn't imply the value was ever wrapped in a Guess at all.
`Interpreter._unary` (line 158) has the identical shape for `-`/`not`.

`self_eval.lang`'s `apply_binop` (guest dispatch for `+ - * / % < <= > >=
== !=`) and `eval_unary` (`-`/`not`) did **not** mirror this asymmetry:
```
fn apply_binop(op, a, b) { let p = ...; mkb(p, op, [a, b]) }          # always [a, b]
fn eval_unary(node, env, st) { ... mkb(0 - r.v.v, "-", [r.v]) ... }   # always [r.v]
```
`mkb(p, o, i) { @{v: p, op: o, ins: i} }` is a trivial box constructor —
whatever `i` is passed unconditionally becomes the guest node's `ins`,
regardless of what the underlying host computation of `p` actually
derived it from. Since `a`/`b`/`r.v` are the guest's own boxes for the
Guess-valued operand(s) — and a directly-`guess(...)`-constructed box has
`op: "guess"` by construction (round 176's free-delegation) — the guest's
uniform boxing leaks that `"guess"` op into the why-tree on exactly the
miss path where the host's real derivation has already discarded it.

## 2. A sibling gap, found by inspection not fuzzing

Before fixing, checked `eval_unary` for the same asymmetry class (`-`/
`not` also delegate to real host operators — `_unary`, not `binop` — so
the same host-side success/miss split applies). Confirmed directly:
```
-guess("hi", 0.9, "m")     # unary minus on a Guess-wrapped string: miss
not guess(1, 0.9, "m")     # unary not on a Guess-wrapped number: miss
```
Host op-list for both: no `"guess"` node (same shape as the binop case).
Guest (before fix): `['let', '-', 'let', 'guess', 'literal', 'literal',
'literal']` — leaks `"guess"` the same way. **Never caught by any fuzz
campaign**: `harness/swe/guest.py`'s `GuestGen` generator grammar has no
unary-minus-on-Guess or `not`-on-Guess template at all — this gap was
invisible to every regression run to date, the same "entirely invisible
to the generator grammar" shape rounds 218/224's own SPEC.md entries
already flagged for their own builtins.

## 3. Fix

`self_eval.lang`, next to `apply_binop`/`eval_unary`:
```
fn guess_unwrap_if_missed(a, p) {
  if missed(p) and is_guess_val(a.v) { unwrap_guess_box(a) } else { a }
}
fn binop_ins(a, b, p) { [guess_unwrap_if_missed(a, p), guess_unwrap_if_missed(b, p)] }
fn unary_ins(a, p) { [guess_unwrap_if_missed(a, p)] }
```
`apply_binop`'s final line becomes `mkb(p, op, binop_ins(a, b, p))`;
`eval_unary`'s `-`/`not` branches bind `p` first, then
`mkb(p, "-", unary_ins(r.v, p))` / `mkb(p, "not", unary_ins(r.v, p))`.
Reuses `unwrap_guess_box` (round 234, already used by `sure()`) unchanged
— no new host-facing machinery, same "walk single-input wrapper boxes
down to the box whose op is literally `guess`, take its first argument"
reconstruction, same documented imperfect-but-safe fallback (a
multi-input box — a real `call`/`if`/tail-loop merge producing a Guess —
returns unchanged) already accepted for `sure()`. `missed(p)` gates the
substitution so a *successful* Guess propagation (`guess(5,.9,"m") + 1`,
`-guess(1,.9,"m")`) keeps the original box(es) untouched, exactly matching
the host's success path — confirmed this control case is unaffected by
both the before/after diff and the pinned tests below.

## 4. Verification

Direct host-vs-guest comparison (`harness/swe/guest.py`'s `GuestHarness` +
an `__opwalk` probe, the same mechanism `why_shape_probe` uses), before
and after the fix:

| case | host ops | guest before | guest after |
|---|---|---|---|
| `guess(0,0,"s") > @{...}` (round 251 repro) | no `guess` | has `guess` | no `guess` ✓ |
| `guess(5,.9,"m") + 1` (success control) | has `guess` | has `guess` | has `guess` ✓ |
| `-guess("hi",.9,"m")` (unary miss) | no `guess` | has `guess` | no `guess` ✓ |
| `not guess(1,.9,"m")` (unary miss) | no `guess` | has `guess` | no `guess` ✓ |
| `-guess(1,.9,"m")` (unary success control) | has `guess` | has `guess` | has `guess` ✓ |

New pinned tests in `languages/whence/tests/test_self_hosting.py`, same
exact-op-LIST-equality style rounds 234/236's own tests use (stronger than
the fuzzer's containment-only check, which is why this gap needed direct
construction, not another campaign run, to close):
`test_guest_binop_guess_operand_miss_why_shape_matches_host_exactly` (5
shapes: `>` miss on either side, guess-of-guess ordering miss,
divide-by-zero miss, success control) and
`test_guest_unary_guess_operand_miss_why_shape_matches_host_exactly` (4
shapes: `-`/`not` miss, `-`/`not` success control). Confirmed each test
FAILS on the pre-fix code (`git stash` the `self_eval.lang` change,
re-run, assert failure, `git stash pop`) before trusting it as a real
regression guard, not just a tautology.

- `languages/whence/tests/test_self_hosting.py` +
  `tests/test_self_eval.py`: 29/29 (was 27/27 — +2 new tests), 123.41s.
- `languages/whence/run_tests_fast.sh`: 842 passed/38 deselected (was 36
  deselected — the +2 new tests are `@pytest.mark.whence_slow` like their
  round 234/236 siblings, correctly excluded from the fast tier).
- `harness/tests/test_swe_guest.py` (the full guest-differential suite,
  46 tests including the slow `AGREE_CASES`/why-shape-exactness tests):
  46/46 both before this round's edits (437.39s baseline) and after
  (351.00s), same command (`python3 -m pytest harness/tests/
  test_swe_guest.py -q`) both times.

## 5. Backlog

1. **Resume the guess-targeted campaign**: round 251 left off at 446/1000
   accepted, checkpoint `next_seed: 2070` in
   `state/swe/round-248/guess-targeted-state.json`. Continuing it now has
   a real chance of finding a THIRD instance of this asymmetry class (any
   other host operator with Guess-aware special-casing that isn't
   uniformly boxed on the guest side) — worth a dedicated SWE-loop(D)
   round rather than folding into this one, per the existing per-round
   scope discipline.
3. **Done, not left open**: swept `whence/interp.py` for every
   `isinstance(..., Guess)` site (`grep -n "Guess)" whence/interp.py`) to
   check for a third asymmetric-propagation point beyond `binop`/`_unary`.
   Found one more — `deep_eq`'s own `isinstance(l, Guess) and
   isinstance(r, Guess)` case (line 2005, used by `contains`/`find`/nested
   `==`) — but it returns a plain Python bool, not a `Prov` node, so it has
   no `.inputs` to leak; not this bug class. The remaining four hits are
   all inside the `guess`/`is_guess`/`confidence`/`sure` builtins
   themselves (rounds 234/236's own territory). `binop`/`_unary` are the
   only two sites that construct a NEW provenance node with Guess-aware
   branching, and both are now fixed.
