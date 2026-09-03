# Round 476 (language C) — predictions, banked BEFORE measuring

Rule D-013 (CLAUDE.md) and round 433 item 10: bank the COMMAND behind every
number, write the prediction first, score misses honestly.

Base: `git rev-parse --short HEAD` = `312b260`. Working tree carries the two
unattributed paths the record-gap check named (`CLAUDE.md`,
`knowledge/mission-fold-fix-v1.md`) plus the escalated
`languages/whence/SECURITY.md`. None of the three is this round's work.

## Already MEASURED before this file was written (stated as fact, not prediction)

M1. `fold(fn(acc, val) { acc + val }, 0.0, [10.0,20.0,30.0])` prints `60.0`
    at base. The mission's own success criterion passes with NO fix.
M2. The briefing's verbatim source (`fold(nums, 0.0, fn…)`) prints
    `miss: fold needs a list, got <fn> (arguments fit fold(fn, acc, xs)) (line 2)`.
M3. `Interpreter.run(src)` returns an `Env`; `type(r).__name__ == "Env"`,
    `repr(r) == "<whence.interp.Env object at 0x…>"`, and `r.get("total")`
    is `Prov('let','total',line=2,1 inputs,value=60.0)`.
M4. `b_fold` is at `whence/interp.py:3611`, not "~2666".
M5. `pytest tests/test_folding.py` -> `ERROR: file or directory not found`.
M6. `pytest tests/ --collect-only` = 2603 tests, not "800+".
M7. `Env.__slots__ == ('vars','parent','interp')`; `Env().payload` raises
    `AttributeError: 'Env' object has no attribute 'payload'`.

## PREDICTIONS (not yet measured)

P1. The fast tier (`./run_tests_fast.sh`, i.e. `-m "not whence_slow"`) is
    GREEN at base with 0 failures. Command:
    `cd languages/whence && ./run_tests_fast.sh 2>&1 | tail -20`
    Predicted collected count: 2400-2560 (2603 total minus ~108 marked slow;
    a `pytestmark` line can mark a whole module, so the subtraction is a
    lower bound on how many go away and the range is deliberately wide).

P2. Adding `Env.__repr__` changes ZERO test outcomes. Basis: a repo-wide
    grep for `interp.Env object` / `Env object at` over `*.py` and `*.md`
    returned NOTHING, so no test or doc pins the default repr. Same command
    re-run after the edit must still return nothing outside the new files.

P3. No `b_fold` return path can produce an `Env`. Structural: `b_fold` has
    exactly three `return`s — `m` (a miss), `mk_miss(...)`, and
    `derived(..., acc.payload)`. Given M7, an `Env` accumulator raises
    `AttributeError` at `acc.payload` rather than being returned. So the
    briefing's stated mechanism ("This Env object becomes the new acc,
    breaking arithmetic on the next iteration") predicts a CRASH, not the
    reported output — the report is internally inconsistent.
    Falsification test: force an `Env` through the accumulator slot and
    assert `AttributeError`, and drive `fold` over a matrix of argument
    shapes asserting the returned type is never `Env`.
    Predicted matrix size: >= 20 shapes, 0 of them returning `Env`.

P4. `fold` is arity-3 and registered `"fn:fn, acc, xs:list"`, so the
    briefing's argument order is wrong, not the interpreter. Predicted: the
    order hint fires for EVERY permutation that puts a non-list last, and
    `map`/`filter` (fn-first, same convention) are untouched by anything
    this round does.

P5. Both interpreters agree. `run_tests_fast.sh` execs SYSTEM `python3`
    (3.12.3, pytest 9.1.1) while a round's ad-hoc runs use
    `.venv/bin/python` (also 3.12.3). Predicted: identical pass/fail and
    identical collected count for the new file under both.

P6. The new `tests/test_folding.py` will hold 12-20 tests and all pass.

P7. `tests/test_critical_mission_claims.py` (round 444) stays GREEN with the
    NEW CLAUDE.md block in the tree: its `has_block` skipif needs only the
    string `CRITICAL MISSION`, and its claim-pin regexes
    (`Fold Logic Regression`, `fold\(\).{0,80}Miss`) match the ROUND-350
    block, which the #476 block was APPENDED after rather than replacing.
    This is the prediction most likely to be wrong, because it depends on a
    file a separate system rewrote 90 minutes before this round started.

## Scoring

| # | outcome |
| --- | --- |
| P1 | **HIT** — 2485 passed, 3 skipped, 115 deselected, 262.07 s; collected 2488, inside the 2400-2560 range |
| P2 | **MISS, and the most useful miss of the round.** The claim "changes ZERO test outcomes" was true of `Env.__repr__` and false of the ROUND. Six tests went red, none of them touching `Env`: `test_specreg.py::test_the_live_spec_registry_has_no_errors` (minting decision 58 in prose with no entry in SPEC's `## Anti-mainstream design decisions` registry — "the registry's max is 57, so the next round to mint a number reuses 58") and five in `test_testcorpus_census.py` (the new `tests/test_folding.py`'s 24 Whence programs entered the harvested corpus). The prediction scoped itself to one edit and the grep behind it was sound; what it missed is that a ROUND'S ARTEFACTS ARE THEMSELVES MEASURED SUBJECTS in this tree. Both are now green, the census counts raised with all five rows itemised. |
| P3 | **HIT** — 24 shapes x 4 engines, 0 `Env` returns |
| P4 | **MISS** — the order hint fires for 4 of the 5 wrong permutations, not 5. `fold(0, fn, xs)` has a list in the `xs` slot, passes `b_fold`'s list check, and dies one step later at `0 is not callable`. Found by the test written from the prediction. |
| P5 | **HIT** — system `python3` and `.venv/bin/python` are both 3.12.3; `run_tests_fast.sh` execs the system one and the new file passes under both |
| P6 | **MISS** — 150 tests, not 12-20. The estimate forgot its own parametrisation: 24 shapes x 4 engines is 96 tests out of one function. |
| P7 | **HIT** — and it was named as the likeliest to fail, which it was not. The #476 block was APPENDED after the round-350 block rather than replacing it, so round 444's `has_block` gate and both claim regexes still match. |

**4 hits, 3 misses.** The three misses share one shape: each assumed a
surface was more uniform than it is — one edit's blast radius (P2), one
diagnostic's coverage (P4), one function's test count (P6). P2 is the one
worth carrying: **a round's own new file is in this tree's corpus, and two
independent instruments measure it.**
