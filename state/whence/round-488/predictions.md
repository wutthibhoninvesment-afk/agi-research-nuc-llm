# Round 488 (language C) — predictions, banked BEFORE measuring (D-013)

Subject: round 482's next-step 3 — *"`reprsweep.py`'s `PROBE` is a
hand-written program — the one list left in this design. A value kind no
line of it constructs is not audited; the crawl is exhaustive over what
the probe BUILDS, not over what the language can build. The closing move
is to derive the probe from the builtin table."*

What I have READ before banking (reading is not measuring): `reprsweep.py`
in full; `tests/test_v47.py`'s `PINNED_REACHED` (19 entries, 7 of them
`whence.ast_nodes`); `whence/ast_nodes.py`'s `_simple(...)` call sites;
`_make_builtin_table()`'s 37 `(name, arity)` rows; `values.py`'s class
list. What I have NOT run: any derived probe, any sweep, any test.

## Baseline, adopted rather than re-measured
B1. The whence fast tier at HEAD is `2714 passed, 3 skipped, 116
    deselected`. PROVENANCE: `logs/driver.log`, round 487
    `whence-health-check PASS (... in 1403.23s)` at 07:19:00, which
    `run_driver.sh:563` shows is exactly `languages/whence/run_tests_fast.sh`.
    `git log b8dff22..HEAD -- languages/whence` is EMPTY, so that run's tree
    and HEAD's are the same tree for this suite. It is a CONTENDED time
    (four concurrent suites, `nproc` 1) and is not comparable to a solo run.

## The universe
P1. `whence/ast_nodes.py` defines 23 CONCRETE `Node` subclasses (24 classes
    including the `Node` base). The current `PROBE` reaches 7 of the 23.
P2. A probe that puts each construct inside a FUNCTION BODY reaches at
    least 20 of the 23 — `Closure.body` is the public door and the crawl
    already goes through it.
P3. `Program` is NOT reachable by a public path from `run()`: nothing
    public on `Env` or `Interpreter` holds the top-level program node. I
    predict EXACTLY ONE unreachable concrete node class, and it is
    `Program`.
P4. Total reached classes rises from 19 to at least 30.

## What the enlarged sweep finds
P5. At least one NEW R2 violation (`len(repr) > values.REPR_CAP`, 240)
    among the newly reached AST node classes. Named in advance:
    `ast_nodes.Str` holding a long string literal — `_node_field` cuts
    Nodes by depth and lists by breadth and falls through to bare
    `repr(v)` for a host scalar, so a 5 000-character literal renders at
    5 000+ characters. R2 is a bound or it is not.
P6. ZERO new R1 (host-leak) violations from the AST family: the generated
    repr interpolates `type(v).__name__`, host scalars and nested node
    reprs, and no module path.
P7. ZERO new R4 violations from the AST family: `_simple`'s generated repr
    names its own class by construction.
P8. `values.FullRendering`, `values._FullCtx` and `values._Bare` are NOT
    reached even by a probe that calls `show`/`print` — they are internal
    to one `full_show` walk and are stored on no value.
P9. `reprsweep.py --seeds` (R3) stays OK across the three seeds with the
    enlarged probe.

## Blast radius
P10. Adding the derived probe turns EXACTLY ONE pre-existing test red
     before I update it: `tests/test_v47.py::TestTheRule::
     test_the_reached_set_is_exactly_the_pinned_one`. No other pre-existing
     whence test changes outcome.
P11. The R2 fix P5 predicts is confined to ONE function,
     `ast_nodes._node_field`. No node class and no `values.py` class needs
     a repr change.

## Cost
P12. `run_tests_fast.sh` run SOLO on this box (nothing else in flight)
     completes in under 700 s — i.e. the 1403.23 s in B1 is contention,
     not work, and the ratio is between 2x and 4x (round 487 measured the
     four-suite contention factor at 3.27x as a FLOOR).

## Honest no-basis declaration (round 435 next-step 7)
I have NO basis for a prediction about how many of the 37 builtins the
derived probe will fail to call, because I have not read the argument
types each one accepts. I will report what it holds rather than guess.
