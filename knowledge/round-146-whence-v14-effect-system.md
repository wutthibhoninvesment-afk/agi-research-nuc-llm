# Round 146 (language C) — Whence v0.14: a minimal, parse-time effect system

**Status note (written by round 162, not round 146):** this round actually ran,
built, and verified everything below on 2026-08-26, immediately before a
false-positive quota stop truncated the driver at round 147 and produced
`state/FINAL-REPORT.md`. The code (`SPEC.md`, `whence/parser.py`,
`tests/test_examples.py`, new `examples/effects.lang` + `tests/test_v14.py`)
reached this repo's `main` branch via the later `c768d90` "checkpoint: sync
from Mac backup" commit — so nothing here needed a NEW commit — but the round
protocol's other two artifacts (this knowledge file, the round-log entry in
`state/research-state.md`) were never written, and the track-status summary
line kept reading "v0.13" with the effect system listed as "still fully
unstarted" for 16 further rounds (147-161) until this round cross-checked
`git log`/`SPEC.md`/`FINAL-REPORT.md` against the tracked backlog and found
the mismatch. Everything below is round 146's real design and findings,
reconstructed from `SPEC.md`'s own "v0.14 (round 146)" section (which IS
complete and was written contemporaneously) plus `tests/test_v14.py`'s
docstrings, and RE-VERIFIED live by round 162 (full suite, fuzz/oracle/guest
seeds, ref_diff) before being folded into the permanent record.

## 1. What was built

The curriculum's third "advanced feature" slot (after v0.12 structural types
and v0.13 return types) went to an effect system rather than "AI-native
primitives" — chosen because Whence already has one observable effect worth
gating (`print`, which writes to the host) and a minimal design falls
directly out of the v0.12/v0.13 precedent, whereas AI-native primitives had
no settled scope.

```
fn f(params) effects [tag, ...] -> Type { body }
```

An optional clause after the parameter list, in a FIXED order (effects
before `-> Type` — the other order is an ordinary "expected '{'" parse
error, not an accepted alternate spelling, per
`test_return_type_before_effects_is_a_parse_error`). Anonymous
`fn(...) effects [...] { ... }` takes the same clause.

## 2. Why this is a parse-time check, not a runtime one (the key design call)

`: Type`/`-> Type` (v0.12/v0.13) both check a RUNTIME value, so they have to
live in the interpreter (erased into `typed(...)` guard calls / a
`Closure._ret_type` checked once at settle). Whether a function's own body
*directly names* an effectful builtin is a static property of the SOURCE
TEXT, decidable before the program ever runs — the same category of fact
that already makes rebinding and "block must end in an expression" PARSE
errors rather than misses in this language. So v0.14 needed:
- **zero new AST node**,
- **zero `Closure` field**,
- **zero interpreter change at all.**

`_EFFECTFUL_BUILTINS = {"print": "io"}` in `parser.py` is the one place a
future effectful builtin (randomness, a clock, real I/O) would register its
tag — nothing else would need to change.

## 3. Mechanism

`Parser.effects_stack`: a stack of "the nearest enclosing fn's declared
effect set" — `None` for no clause (unrestricted), a `frozenset` (possibly
empty) for a declared one — pushed on entering any `fn`'s body and popped on
exit (`parse_effects_clause`, called from both the named-`fn` and anonymous-
`fn` parse sites, `parse_params(...)` → `parse_effects_clause()` →
`parse_ret_type()` → body). `_check_effect_call(callee, tok)` runs at every
direct call site (from `postfix()`'s call-parsing) and only fires when
`callee.__class__ is A.NameRef` AND the name is a table-registered
effectful builtin. An empty stack (module top level, outside any fn) reads
exactly like a `None` top — **every program written before this feature
existed parses identically**, confirmed by the full pre-existing suite and
every `examples/*.lang` file running unchanged.

`effects []` is the interesting declaration: "this function's own body may
not directly call an effectful builtin." Violating it raises `ParseError`
naming the builtin, the required tag, and the declared set verbatim
(`'print' requires effect 'io', not permitted by the enclosing function's
'effects [] (no effects declared)'`). `effects [io]` (or any set containing
the tag) grants it. An unrelated tag like `effects [network]` does **not**
grant `"io"` — the check is per-tag
(`test_effects_unrelated_tag_still_blocks_print`), not merely "was a clause
present."

## 4. Deliberately shallow, not merely incomplete

Same scoping discipline v0.13's return-type check already established — one
settle point / one textual body, not full call-graph composition:

- A nested `fn` DEFINED inside a restricted body is a separate closure with
  its own (absent, hence unrestricted) declaration and may print freely,
  even lexically inside an `effects []` function
  (`test_nested_undeclared_fn_escapes_outer_purity`,
  `examples/effects.lang`'s `strict_sum`/`debug_print`). Calling a
  DIFFERENT, unrestricted function that itself prints is likewise untouched
  by the caller's own declaration.
- Only a literal `name(...)` callee is inspected: `let p = print` then
  `p(1)` is invisible to the check inside an `effects []` function — the
  callee at that call site is the `NameRef` `p`, not `print`
  (`test_indirect_call_via_variable_is_not_checked`).

Both gaps are real, tested, and documented rather than hidden. A call-graph-
aware (transitive) effect system that closes them is future work, not this
feature's scope.

## 5. Testing (as originally run, round 146; RE-RUN clean by round 162)

- `tests/test_v14.py`: 20 tests, covering backward compatibility (no
  clause == unrestricted), `effects []` blocking + `effects [io]` granting,
  fixed-order enforcement, both shallow-scope gaps as pinned positive tests
  (not just documentation), sibling-fn non-leakage, and 2
  `assert_three_way` cases.
- Zero interpreter change means the three-way differential (fast / direct /
  trampoline) agrees by construction — pinned explicitly anyway.
- Round 146's own standing-checklist run (per `SPEC.md`): two fresh fuzz
  seeds, two oracle seeds (one at `--limit 6000`), two guest seeds,
  `reserve_probe --examples -n 30`, `ref_diff` over every example — all
  clean, with `ref_diff` correctly reporting `examples/effects.lang` as
  `NEWSYNTAX` against the pre-round reference tree (a new file, not a diff).
- New example `examples/effects.lang` (4 checks): `total` (`effects []`,
  legitimately pure), `report` (`effects [io]`, prints), `audited_total`
  (`effects [io] -> num`, composing with v0.13), `strict_sum` (the honest
  escape-hatch demonstration). No example demonstrates the REJECTED case —
  a `ParseError` aborts the whole file before any `check` can run, unlike a
  v0.12/v0.13 runtime mismatch — covered instead by `tests/test_v14.py` and
  `test_examples.py::test_effects_violation_exits_2`.

## 6. Round 162's re-verification (this round, live)

Full suite + every standing check re-run from a clean `git status` baseline
before this round touched anything else in the language track:

- `python3 -m pytest` (whole `languages/whence` suite): **801 passed** in
  110s (799 base + round 158's own 2 net-new tests — see the round-162
  entry for that reconciliation).
- All 15 `examples/*.lang` run green, `effects.lang` still 4/4 checks.
- Host fuzz: 2 fresh seeds (300/400 programs) — 0 crash signatures.
- Oracle campaign (6 oracles): 2 fresh seeds, one at `--limit 6000` — 0
  finding signatures across both.
- Guest differential (`self_eval` oracle): 2 fresh seeds (200 programs
  each) — 0 finding signatures (self_eval's own guest-parity gap for
  `effects` — see round 162's own new finding below — means these guest
  seeds never generated an `effects` clause to begin with; this reruns the
  ORIGINAL pre-existing guest coverage, not new effects-specific coverage).
- `bench/ref_diff.py` (all examples, all 3 modes: fast/direct/slow): 0
  differing pairs, `effects.lang` now reads `SAME` (it's plain `HEAD`
  content now, not new syntax against a stale reference).
- `bench/reserve_probe.py --examples -n 30`: corpus max well under
  `HOST_RESERVE` (350) on every deep-template probe seen before the run's
  own 10-minute harness timeout truncated its output (a slow, not a wrong,
  result — the probe legitimately spawns one fresh subprocess per binary-
  search step per program, and this box is the single-core NUC, not the
  faster Mac round 146 likely ran on originally).

## 7. New finding this round: the fuzzer never generated `effects [...]`

Exactly the same shape of gap round 134 found for `: Type`/`-> Type`:
`harness/swe/fuzz.py`'s `ProgramGen` grammar had no way to emit an
`effects [...]` clause, so the parse-time effect check was only ever
exercised by the 20-test hand-written corpus — zero fuzz-generated coverage
for 16 rounds. Closed this round; see the round-162 knowledge file for the
fix (`maybe_effects()` in `fuzz.py`, a `GuestGen` no-op override in
`guest.py` mirroring the ORIGINAL round-134 shape of the type-annotation gap
— guest parity for `effects` is not yet built, tracked as the next
guest-parity target in the language backlog).

## 8. Corrected standing record

`state/research-state.md`'s language(C) track-status line and backlog are
updated by round 162 to read v0.14 (not v0.13) and to remove "an effect
system... still fully unstarted" (it has existed, working and tested, since
round 146). The backlog's remaining "advanced feature" item is now narrowed
to AI-native primitives only, still unstarted, still without a settled
scope — genuinely the only slot left open from the curriculum's "language
FEATURES" line.
