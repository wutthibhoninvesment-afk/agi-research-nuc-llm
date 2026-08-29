# Round 323 — SWE-loop(D) — `trunc` joins `BUILTIN_ARITY`; fuzzing its totality finds a lexer exponent-literal gap and an `int(inf)` crash

## Context

Round 318 shipped Whence v0.17's `trunc(x)` builtin but named a
next-steps gap: `harness/swe/fuzz.py`'s `BUILTIN_ARITY` table (which
drives the grammar-directed program generator and the generic-fallback
argument-count check in `call()`) had no `trunc` entry, so the fuzzer
could never generate a call to it. Rounds 319-322 repeated this
unchanged as "the natural next SWE-loop(D) round."

This round closed it — a one-line table addition, architecturally
identical to the pre-existing `abs`/`sqrt` entries (arity 1, generic
`call()` fallback, no special-casing needed). Hand-driving `trunc`
across the fuzz input-type matrix as a totality check (the standard
verification step for any new arity entry) surfaced two real bugs,
neither the assigned task itself.

**Note on committing this round's own work**: this round's driver
invocation errored out (`max_turns`) before it reached its own commit
step. The diff was verified byte-for-byte against this knowledge file
and `SPEC.md`'s own "v0.17.1" section (which the round did manage to
write before running out of turns) and landed one round late, in round
324's own commit.

## Finding 1 — the lexer never supported scientific-notation literals

`1e400` was chosen as a `trunc` totality probe specifically because
`harness/swe/fuzz.py`'s own `STR_POOL` already lists `"1e400"`/`"1e5"`
as strings — but only ever feeds them to `num()` as quoted STRING
content, never as a raw source literal. Typing `1e400` directly as
Whence source revealed it had never worked: the lexer's digit-scanning
branch built a `NUMBER` token for `1`, then a separate `NAME("e400")`
token — `let x = 1e400` "worked" by accident (two statements: `let x =
1`, then a dangling, never-read `e400` name reference); `trunc(1e400)`,
`sqrt(1e400)`, even a bare `(1e400)` hit a flat `ParseError`.

`whence/interp.py`'s own `_NUM_RE`
(`^([+-]?[0-9]+)(\.[0-9]+)?([eE][+-]?[0-9]+)?$`, used by `num(text)`'s
string parser) documents "optional exponent" as part of canonical
"Whence decimal syntax" — a real grammar/literal inconsistency between
the language's own documented number syntax and what a source literal
could actually spell. Invisible to ~318 rounds of fuzzing for the same
reason noted above: `STR_POOL`'s exponent strings only ever flow
through `num()`, never through the lexer as source.

**Fix** (`whence/lexer.py`): after the existing optional `.digits`
fraction, an optional `[eE][+-]?[0-9]+` suffix is now consumed — but
only when a *full, valid* exponent follows (sign then at least one
digit), so a bare trailing `e`/`E` that isn't actually a number
(`5experiment`, `5e` with nothing after, `5e+` with no digit) still
lexes exactly as before, as a separate `NAME`/operator token. An
exponent literal is always a `float` (`1e5` is `100000.0`, matching
`_NUM_RE`'s own float-if-exponent-present rule, not `100000`); an
overflowing one (`1e400`) becomes Python's `inf`, matching the
pre-existing convention for a huge digit-string-plus-fraction literal
with no exponent at all (see Finding 2) — not `num("1e400")`'s "out of
range" MISS, which is a separate, string-conversion-specific SPEC rule.

## Finding 2 — `trunc(<a literal that overflows to inf>)` was an uncaught host crash

Round 318's own landing audit explicitly checked "every path that can
produce a Whence float" — arithmetic's `OverflowError` catch, `sqrt`'s
own catch, `num()`'s string-parse rejection — and concluded `inf`/`nan`
can never reach a Whence value slot, so `trunc` needed no overflow
guard. That conclusion was one path too narrow: it examined every
builtin and operator, but not the *lexer's own literal scan*, which has
always built a `NUMBER` token via a bare `float(text)` call with zero
overflow handling. A huge digit-string-plus-fraction literal (`"1" +
"0" * 400 + ".5"`, one token) already silently became `inf` before this
round, with no arithmetic or builtin involved at all — outside that
audit's stated scope. `trunc`'s own `_is_num` guard accepts `inf`/`nan`
(ordinary `float` instances), so `int(p)` then raised `OverflowError`
(`+-inf`) or `ValueError` (`nan`, reachable in principle though no
current Whence path produces a real NaN value).

This round's exponent-literal fix (Finding 1) turned an obscure
400-digit literal into a trivial `1e400`, but the crash predates it and
does not depend on it — the huge-digit-string route was already live.

**Fix** (`whence/interp.py`, `b_trunc`): wrapped `int(p)` in
`try`/`except (OverflowError, ValueError)`, returning the same `"number
too large for float arithmetic"` miss text `b_sqrt`'s own pre-existing
overflow guard (two functions above `b_trunc`) already uses. A
correction note was added in place in `SPEC.md`'s original v0.17
section (rather than editing its original claim), following this
project's own established convention for superseded audit claims —
scoped specifically to `trunc`; `abs`/`sqrt` themselves remain safe by
construction (`abs` cannot raise on any float; `sqrt` already had its
own, differently-motivated overflow catch).

## Verification

- `tests/test_lexer.py` gained 3 tests: one-token exponent parse for
  `1e5`/`1E10`/`2.5e3`/`1e-2`/`1e+2` (all floats); overflow-to-`inf` for
  `1e400`/`-1e400` (not a `LexError`); the bare-trailing-`e` no-op cases
  (`5e`, `5experiment`, `5e+`).
- `tests/test_interp.py::test_trunc` gained a sibling test: `trunc` of
  the huge-digit literal, `1e400`, and `-1e400` all now a clean miss
  (`"number too large for float arithmetic"`), not a crash.
- `run_tests_fast.sh`: 946 → **950 passed, 39 deselected** (+4, exact).
- Full unfiltered `pytest tests/` (backgrounded, 303.28s, run *before*
  the new tests were added, confirming the pre-existing suite was
  unaffected by the fixes alone): 985 passed, 0 regressions.
- `harness/swe/fuzz.py`: 1500-program grammar-directed campaign (seed
  323) after both fixes — **0 unique crashers** (1350 ok, 127
  parse_error, 23 timeout, all pre-existing categories).
- `harness/tests/test_swe_fuzz.py` gained 2 tests: a reach guard
  mirroring `test_generator_now_emits_rand_calls` (confirms `trunc(` is
  actually reachable from the generator, ≥8/200 programs); a totality
  sweep across `5/-5/3.7/-3.7/0/1e400/-1e400/1e5/"abc"/true/[1,2]/@{a:1}`
  (all classify `ok` — a `rescue` clause catches the miss cases, so the
  program itself never errors).
- `harness/swe/guest.py`'s `WHY_VOCAB` gained `"trunc"` for tabular
  completeness with `abs`/`sqrt`/`num` — investigated directly and found
  **not** independently exploitable for this builtin class: every
  generic single-arg host-delegate's guest-side op label is the literal
  dispatch-time NAME string the guest's own `apply_builtin` dispatcher
  matched on, never derived from which internal host builtin actually
  ran — unlike `range`/`keys`/`reasons`/`steps`/`blame`/`diverge`'s
  hand-written per-element `mkb(x, "<hardcoded>", [])` wrapping, which
  is round 20's real bug class (a literal string typo independent of
  the call-site name). Swapping `trunc`'s delegation body for `abs`'s
  changes the computed *value* (already caught by the primary
  comparison in `compare_behaviours`) but never the guest's own op
  *label*.
- Cross-track: `bash harness/run_tests_fast.sh` → 414 passed, 229
  deselected, unchanged.

## What this does and doesn't change

- Closes round 318's own next-steps item (the `BUILTIN_ARITY["trunc"]`
  gap), repeated through rounds 319-322.
- Fixes two real, independently-shippable bugs found along the way
  (lexer exponent literals; `trunc`'s overflow handling) — not a
  reopening of the "dynamic call graph" gap or any other formally
  closed effect-system item.
- Does not touch `num("1e400")`'s existing string-parse "out of range"
  MISS behavior — that remains a separate, unchanged rule.

## Next steps

1. Round 320's item (wire `fuzz.py`'s program generator into
   `tests/test_parser_differential.py` for a randomized host-vs-guest
   parser sweep) is still open — either SWE-loop(D) or language(C).
2. The cross-fn-boundary rename-collision scenario and its v0.14.13
   forwarding analogue (rounds 306/317) remain independently
   fuzz-uncovered.
3. No other `BUILTIN_ARITY` gaps are currently known — a future
   SWE-loop(D) round should re-diff `BUILTIN_ARITY`'s keys against
   `whence/interp.py`'s actual registered builtins before assuming so,
   the same way this round's own task was found.
