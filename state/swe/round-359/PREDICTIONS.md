# Round 359 (SWE-loop D) — predictions, written BEFORE any measurement (D-013)

Task: ship the `param_erasure` oracle — round 347 §7's named gap, carried by
round 353 as "item 5 ... the largest open SWE-loop(D) item", re-derived by
reading `swe/oracles.py`: `ORACLE_NAMES` has seven entries and no
`param_erasure`.

The oracle's claim under test is v0.19's own, from `_check_params`'s
docstring: its two properties are "inherited from the v0.12 guards this
replaces rather than newly chosen, so that moving the check does not also
change what it means".

Transform: v0.19 `fn f(p: T) { BODY }` -> v0.12 `fn f(p) { let p = typed(p,
T, "parameter 'p' of f") BODY }`, compared on `out` / `checks` / `vals`.

| # | prediction | conf |
|---|---|---|
| P1 | A POST-PARSE AST transform (prepend the guard `A.Let`s into `body.stmts`, then set `param_types = None`) reproduces v0.12's erasure exactly, with no re-run of `mark_tails` needed — because `block()` requires a body to end in an `ExprStmt`, so prepending can never change which statement is the tail. | 85% |
| P2 | (round 347's P5) On generated programs where no annotation's spec NAME is bound more than once, a 200-program campaign reports **0** mismatches. | 60% |
| P3 | (round 347's P6) With the shadowing exemption DISABLED, the oracle fires on `_shadowed_shape_stmt` programs — i.e. the exemption is load-bearing, not defensive. | 85% |
| P4 | The exemption rate over 400 generated programs is between 8% and 20% (measured neighbours: shadowed-shape 11.8%, shape-in-annotation 18.8%, round 347 §2). | 65% |
| P5 | The miss-ARGUMENT case agrees, as round 347 hand-checked: no mismatch signature anywhere in the campaign whose two sides are the same reason text reached through `merge_miss` vs `_check_contract`'s pass-through. | 90% |
| P6 | The oracle needs at least one exemption round 347 did NOT name. | 55% |
| P7 | The oracle is silent on every checked-in example under `languages/whence/examples/`. | 80% |
| P8 | The oracle finds at least one NEW host defect (a real divergence that is not an exemption gap) in a 200-program campaign. | 30% |
| P9 | Adding an 8th oracle raises a `-n 150` campaign's wall clock by less than 25% (the seven existing oracles include `frames`, which runs under `sys.setprofile` and is by far the most expensive). | 70% |
