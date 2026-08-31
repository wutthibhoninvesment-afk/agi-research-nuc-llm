# Round 401 (SWE-loop D) — predictions banked BEFORE any measurement

Banked 2026-08-31, before running anything new. Rule D-013.
Task: round 389's next-step items **5, 4(remainder), 1, 2** — in that order of
interest, not of cost.

Sources read before banking (prior rounds' recorded data, not new measurement):
`state/research-state.md` rounds 383/389/395/398/399/400, `harness/swe/exemptmap.py`,
`harness/swe/oracles.py::oracle_tail_transparency`, round 389's `armA2.log` /
`armB2.log` / two sweep JSONLs. NOT read before banking: the whence
runaway-tail-loop guard (round 366), the three seeds' program text, `git log`
for `harness/swe/fuzz.py`, `exemptaudit.py`/`fuzz.py`/`guest.py` internals.

---

## A. Item 5 — what ARE seeds 140, 273, 341?

**P1.** All three are **unbounded (non-terminating) tail recursion**, not merely
deep-but-terminating recursion. Evidence expected: the shrunk program's fn calls
itself in tail position with no reachable base case.

**P2.** The host Whence terminates the *tail* side of these programs **quickly**
(armA row for seed 140 shows every oracle `ok` in ~0.01-0.04 s) because round
366 made a runaway tail loop a **`miss`** — i.e. there is an ITERATION budget on
the tail-merge loop. So `a` (tail) returns a miss payload; `b` (lifted, tail
flags cleared) grows host/guest depth and trips `peak >= max_depth`. That
asymmetry — **iteration budget on one side, depth budget on the other** — is why
T-SPACE fires.

**P3.** Therefore the T-SPACE exemption for these three seeds is **not
convertible by raising `max_depth` alone at any reachable value**: it converts
only when `max_depth` exceeds the runaway-tail-loop iteration budget. Round
383's "unbounded past 25 000" and round 389's "survivors at 5 000" are the same
fact. I predict the runaway budget is **>= 25 000** iterations.

**P4.** The three seeds are **one generator shape, not three** — the same
production in `ProgramGen` emits the self-recursive tail call in all three.
Shrinking any one produces the same skeleton.

**P5.** It is an **accident of the grammar, not a design intent**: nothing in
`ProgramGen` names "emit a non-terminating tail loop". No comment in `fuzz.py`
mentions unbounded/infinite recursion as an intended shape.

**P6.** Running a shrunk witness through `languages/whence/run.py` at the
language's own `DEFAULT_MAX_DEPTH = 20000` exits **0** (a miss is a value, not a
crash) and prints a miss, not a `RecursionError` and not a hang > 10 s.

**P7.** The three seeds' shrunk sources are each **<= 8 lines**.

## B. Item 4 (remainder) — the digest guard for `exemptaudit`, `fuzz`, `guest`

**P8.** `grep -c oracles_sha` over `harness/swe/exemptaudit.py`, `fuzz.py`,
`guest.py` returns **0, 0, 0** — none records any instrument digest today.

**P9. (the one I most expect to be interesting)** Round 389's `oracles_sha`
guards the **oracle** but not the **GENERATOR**. `sweep_record` keys every row
by `seed`, and `seed` only denotes a program *given a fixed* `ProgramGen`. An
edit to `harness/swe/fuzz.py` silently changes WHICH program `seed 140` is, so a
seed-paired A/B across such an edit compares two different programs while
reporting `oracles_sha` unchanged. I predict `sweep_record` records no
generator digest (confirmed by reading it) and that the correct guard is a
`gen_sha` over `fuzz.py` alongside `oracles_sha`.

**P10.** `git log --oneline -- harness/swe/fuzz.py` shows **at least one commit
between round 383's sweep and round 389's sweep**. If true, round 389's control
("arm A vs round 383's rows on 300 shared seeds, every site's fire SET
identical, all eight") was run across a generator edit — and its identity result
is then *evidence the edit did not perturb these seeds*, which is a weaker
claim than the one that was published. Confidence 0.55; this is the prediction
I expect to be least safe.

**P11.** A digest over `fuzz.py` alone is **not** sufficient for `guest.py` and
`exemptaudit.py`: their instrument includes the whence tree under test. I
predict at least one of the three already records SOMETHING version-ish (a rev,
a tag, a path) that is not a content hash — and that a content hash is strictly
stronger.

## C. Item 1 — the paired A/B: `--max-depth 5000 --timeout-s 12`

**P12.** Of round 389's 10 `ok -> timeout` flips (armA 500/3.0 -> armB 5000/3.0:
totality 0->0, fast_slow 0->1, direct 0->3, determinism 1->3, render 0->0,
frames 2->3, tail_transparency 0->1, param_erasure 0->0 — i.e. armA had 3
timeouts and armB 14, net +11 by these tables), **>= 7 of the added timeouts are
recovered** at `timeout_s = 12`.

**P13.** T-SPACE's fire rate at (5000, 12) is **unchanged from armB's 0.9 %**
(3 seeds: 140, 273, 341). Timeout does not touch the space exemption.

**P14.** **0 new mismatches** in the (5000, 12) arm — same as round 389 found at
(5000, 3.0). Raising the ceiling buys coverage, not bugs.

**P15.** Wall clock for a 360-seed (5000, 12) arm is **between 1.5x and 4x**
armB's, and **under 1 800 s** — i.e. it fits inside one round if launched early.

**P16.** `R-CAP` fire% and `F-SLACK` distance are **byte-identical** to both
prior arms (38.6 % / max 98 of 140), because neither depends on either knob.

## D. Item 2 — `FRAME_SLACK`'s ceiling at `under = 1`

**P17.** `deepest_undercharged_run(under=1)` reproduces round 389's **plateau at
excess 247**, and the run survives past guest depth 1 200.

**P18.** At `under = 1` the plateau is reached because direct mode's `_hleft`
runs out and the trampoline takes over; so the plateau value is **independent of
`under`** for `under = 1` and `under = 2`? NO — I predict it is **NOT**
independent: round 389 measured 247 at `under = 1` and pinned a different bound
at `under = 2`. I predict the `under = 2` plateau is **strictly smaller** than
247 (reaching the same host budget in half the levels).

**P19.** The bisection costs **30-90 s**, i.e. round 389's "~40 s" is right to
within a factor of 2 on today's load.

## E. Process

**P20.** `run_tests_fast.sh` is green at round start (round 389 recorded 748
passed; rounds 390-400 will have added files). Predicted count at round start:
**> 780 passed, 0 failed**.

**P21.** `languages/whence/SECURITY.md` is still dirty and still not this
track's file to commit (round 399's item 9). It stays dirty at round end.
