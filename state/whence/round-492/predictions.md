# Round 492 (language C) — predictions, banked BEFORE measuring (D-013)

Subject: round 488's next-step 1 — *"`scale_cases()` is still eleven
hand-written cases and the name axis is the only one this round derived.
The derived scale pass varies three tokens — a string literal, an
identifier, a digit run — because those are the three a Whence program can
make arbitrarily long. Nobody has asked what the OTHER axes are: arity,
nesting depth, the number of enclosing scopes (`Env`'s `depth` walk is
unbounded in principle), `Miss.reasons` length. **List the inputs each repr
interpolates and say which of them an author sizes.**"* Round 488's
next-step 4 is folded in: `test_cap_is_the_only_place_repr_cap_is_compared`
is a regex over source lines and was asked to become behavioural.

What I have READ before banking (reading is not measuring): `reprsweep.py`
in full; every `__repr__` in `whence/values.py`, `whence/interp.py`,
`whence/ast_nodes.py` and `whence/lexer.py`; `Interpreter.__init__`'s
signature; `tests/test_v48.py`'s cap tests. What I have NOT RUN: any
sweep, any repr, any test, any axis witness. Every number below is a bet.

## Baseline, adopted rather than re-measured
B1. The whence fast tier at HEAD is `2780 passed, 3 skipped, 116
    deselected in 386.22 s` (solo). PROVENANCE: round 488's own run,
    recorded in `state/research-state.md`'s round-488 entry. `git log
    --oneline 4c775c3 -- languages/whence` has `0aea7be` (round 488) as its
    newest commit, so HEAD's `languages/whence` IS the tree round 488
    measured. `nproc` is 1; contended times are not comparable.

## The enumeration — what a repr interpolates
P1. The sweep reaches 34 classes and ALL 34 define `__repr__` in their own
    `__dict__` (`_simple` builds each node class with a generated one, so
    the 22 AST classes each own a distinct function object). Distinct
    SOURCE texts behind those 34 functions: 13 — twelve hand-written
    (`WList`, `Prov`, `MergedProv`, `Miss`, `Guess`, `PMap`, `Record`,
    `Closure`, `Builtin`, `Explanation`, `Env`, `Interpreter`) plus the one
    `ast_nodes._simple.__repr__`.
P2. Deriving the interpolated expressions from those sources with `ast`
    yields between 45 and 65 expressions in total (point estimate 55).
P3. EXACTLY ONE reached class's `__repr__` does not route through
    `values._cap`, directly or through `values._frame`:
    `whence.interp.Interpreter`. Every other one does.

## The axis nobody could have varied
P4. `Interpreter.__repr__` interpolates `self.max_depth` with `%s`, and
    `max_depth` is a PUBLIC constructor parameter of the embedding API
    (`Interpreter(max_depth=...)`). `repr(Interpreter(max_depth=10**500))`
    is between 660 and 700 characters — an R2 violation (`REPR_CAP` 240)
    reachable by a caller with no Whence program at all.
P5. The constant part of `Interpreter.__repr__` at defaults (37 builtins,
    `max_depth` 20000) is between 170 and 185 characters.
P6. Every interpolated input classifies into exactly FOUR axis families:
    program TEXT (a string body, an identifier, a digit run — the three
    v0.48 varies), program STRUCTURE (arity, element count, statement
    count, nesting depth, enclosing-scope depth, `Miss.reasons` count),
    the EMBEDDING API (constructor arguments and host-built values), and
    IMPLEMENTATION CONSTANTS (not author-sized). The number of author-sized
    inputs whose family is NOT program text and NOT a bounded count is
    at least 1 and at most 5.
P7. NEGATIVE RESULT PREDICTED: zero new R2 violations along every program-
    STRUCTURE axis — arity, nesting depth, statement count, element count,
    `Miss.reasons` count, `Env` enclosing depth. The structural head-and-
    count cuts plus `_cap` already hold, so the derived structure pass
    finds nothing and that is the finding.

## The behavioural cap gate (round 488 item 4)
P8. Re-running the WHOLE sweep with `values.REPR_CAP` monkey-lowered to 40
    produces violations for exactly ONE class — `Interpreter` — and zero
    others, at HEAD. This is the behavioural replacement for the regex: a
    repr that ignores the cut fails it however the cut is spelled.
P9. With the fix applied, the same sweep at caps 40, 80 and 240 reports
    zero violations for all 34 classes and every axis witness.

## Blast radius
P10. The correctness fix is ONE routing change in `interp.Interpreter.
     __repr__` (wrap in `values._cap`). No other module needs a
     correctness change; `values.py` and `ast_nodes.py` need none at all.
P11. ZERO pre-existing whence tests change OUTCOME. Between 0 and 2 change
     EXPECTATION (a pinned repr string that now ends in a cut).
P12. `reprsweep.py --seeds` (R3) stays OK across the three seeds with the
     axis probe added.
P13. `probe_manifest()` computes `universe - found` and never
     `found - universe`, so its `gaps: 0` is scoped to three modules
     (`ast_nodes`, `values`, `interp`) out of the package's seven. Adding
     the other direction reports 0 at HEAD — a NEGATIVE CONTROL, not a
     finding. `lexer.Token` (which has a `__repr__`) is not reached.
P14. The fast tier ends green and the delta against B1 is EXACTLY this
     round's new tests: no pre-existing test disappears or is deselected.

## Open questions (bets are above; these are not bets)
Q1. `Env.__repr__` walks the parent chain to compute `depth`. The string is
    bounded; the WALK is not. Is a caller-reachable `Env` with a deep
    parent chain constructible after `run()` returns (a closure defined
    inside a deep recursion retains its chain), and if so, is "a repr
    whose COST is unbounded" a rule this file should carry? R1-R4 are all
    properties of the string.
Q2. Is an embedding-API argument inside the subject at all? Decision 58's
    rule is "a value this implementation HANDS A CALLER is a surface". The
    caller here handed the value IN. Say which, in the SPEC, rather than
    leaving it to whichever probe happens to exist.
