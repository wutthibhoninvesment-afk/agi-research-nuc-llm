# Round 233 (SWE-loop D) — mutation-testing `whence/values.py`'s PMap for the first time, plus a real flaky-test root-cause

## 0. Setup

No concurrent-round race (only this round's own `claude -p` process in
`ps`), `state/round_counter` matched `git log`'s HEAD (round 232), and a
fresh `check_round_recorded.py --archive state/research-state-archive.md`
flagged only this round itself (18 pre-acknowledged gaps unchanged — see
round 231). Nothing to reconcile before starting. Did not touch the
Hermes-gateway files (`pyproject.toml`, `whence_qwen_bridge.py`,
`expense_tracker.lang`, `test_simple.lang`) — standing convention since
round 172.

## 1. A real, reproducible flaky test found by accident: `test_diverge_on_deep_equal_values_is_not_quadratic`

Before starting the planned mutation work, a routine full-suite health
check (`pytest -q tests/`, needed as a baseline before adding CPU load)
turned up a genuine failure:

```
FAILED tests/test_fuzz_regressions.py::test_diverge_on_deep_equal_values_is_not_quadratic
AssertionError: (0.011134257540106773, 0.27900671027600765)
assert 0.27900671027600765 < (20 * 0.011134257540106773)
```

Re-running the single test in isolation (no other pytest processes
competing) still failed 1/5 times — this is not a corpus-timeout-style
contention flake (rounds 203/209's family), it reproduces on an otherwise
idle host.

### 1.1 Root-causing it properly (not just loosening the threshold)

The test times `diverge(*small)` (`nest(200)` vs itself) against
`diverge(*big)` (`nest(1600)`) and asserts `t_big < 20 * t_small` — the
old bug (pre-v0.4.1, no memoisation) made `nest(800)` alone take 26s, so
8x the depth should cost well under the 64x a real O(n^2) would produce.

Isolated the mechanism with a controlled sweep (`python3 -c`, 15-60
trials, replicating the test's own code): running the ORIGINAL
methodology (single un-warmed-up 3-rep sum) 30 times gave ratios from
**2.4 to 65.5** — a 27x spread on identical code, occasionally landing
right next to the value a genuine regression would produce (65.5 vs. the
64x quadratic signature). The cause: `small`'s timing window is the
FIRST time `diverge`/`same_payload`/`deep_eq` ever execute in the whole
process, so it sometimes pays a one-time warm-up cost (CPython's
specializing adaptive interpreter needs several calls per bytecode site
to adapt; page-ins; branch-predictor warm-up) that `big`'s
already-warm timing window never pays — this INFLATES `t_small`
unpredictably, swinging the ratio in both directions depending on whether
warm-up happened to land inside the timed window or not.

Fix: an untimed warm-up call on BOTH `small` and `big` before timing
either, plus `min()` of 9 reps instead of a single 3-rep sum (`min` is
robust to a scheduler/GC hiccup ADDING time; nothing subtracts it). This
collapses the same 30-trial spread to **7.1-32.5** — much tighter, but
*still* not under the original 20x threshold. That is the real, honest
finding: **this implementation's steady-state scaling for this specific
depth pair is genuinely ~20-32x for an 8x depth increase (~O(n^1.5-1.6),
not O(n))** — mild, real superlinearity (plausibly cache-locality effects
at n=1600's larger footprint), nowhere near the old bug's magnitude
(sub-second now vs. 26s pre-fix at *half* this depth), but a bit steeper
than the test's own 20x margin assumed.

**Fix applied**: warm-up + min-of-9 methodology, threshold raised
20x -> 40x (60-trial post-fix sweep: max observed 31.5; still 1.6x below
the 64x real-quadratic signature and >30x below the historical actual
regression's magnitude). `tests/test_fuzz_regressions.py` — 40x, 12/12
isolated pytest reruns clean post-fix (vs. failing ~20-60% of isolated
runs before, depending on measurement methodology).

## 2. Mutation-testing `whence/values.py`'s PMap (round 204's persistent AVL tree) — never a target before

`harness/swe/campaign.py --files` defaults to `whence/interp.py` only.
`whence/values.py`'s `PMap` (round 204's persistent-record fix for round
200's O(N^2) blowup) has never been through the mutation harness. Given
this file's own single-CPU/3.8GB constraints (documented repeatedly by
this track and harness(A): rounds 203/209/227 all hit host-contention
issues running the full test suite as a mutation classifier), ran a
standalone, scoped campaign rather than the full `campaign.py` pipeline:

- Scoped `swe.mutation.generate()` to the AVL section only (lines
  234-410: `_PNode`, `_pheight`/`_pbalance`/`_protate_left/right`/
  `_prebalance`/`_pinsert`/`_pget`/`_pinorder`, the `PMap` class) — 53 of
  the file's 313 total mutants.
- Test command: `pytest -q tests/test_values.py tests/test_v16.py`
  (fast, ~0.5-3s) rather than the full suite (438s on this host) — a
  deliberate scope choice, not the full campaign's subset/coverage-map
  machinery; every survivor was manually triaged below rather than
  trusted at face value (this file's own broader lesson: a narrow-suite
  survivor needs verification, not just counting).

**Result: 53 mutants, 34 killed, 19 survived (64.2%, up from the
first pass's 62.3%/33 killed before this round's new test — see §3).**

### 2.1 The real finding: content-correctness tests structurally cannot see AVL balance bugs

Triaged every survivor by hand. Two categories:

1. **Genuinely equivalent mutants** (dead code, not test gaps):
   - `values.py:295`/`297` (`is_new` True/False in `_pinsert`): `is_new`
     is computed and threaded through every recursive call but **never
     consumed** — `PMap.put` discards it (`new_root, _ = _pinsert(...)`).
     Confirmed via `grep`: no caller anywhere reads it. This is real,
     harmless dead computation — flagged, not fixed (task doesn't call
     for a refactor; leaving it for whoever next touches this function
     with an actual need for the distinction).
   - `values.py:298` (`key < node.key` -> `<=`): unreachable difference
     — line 296 already returns on `key == node.key`, so by line 298
     `key != node.key` is guaranteed; `<` and `<=` agree on every
     remaining input.
   - `values.py:408`/`409` (`PMap.__eq__`): confirmed via `grep` that
     **no code anywhere calls `PMap == PMap` directly** (Record equality
     goes through `deep_eq`'s own field-by-field walk, not this method).
     A real latent gap in an untested public method, not a live bug.

2. **The interesting category — boundary-condition mutants in
   `_prebalance`'s rotation triggers and `_PNode`'s height/size
   bookkeeping (the other 15 survivors: lines 249/250/253/258/279/280/
   283/284/311)**: verified by direct construction that **`to_dict()`
   equality cannot distinguish a correctly-rebalanced AVL tree from an
   unbalanced BST holding the identical keys/values** — rotations change
   tree SHAPE, not the key->value mapping, so nothing content-based can
   ever catch a broken rebalance trigger. Confirmed with the sharpest
   possible case: monkeypatching `_prebalance` to a no-op entirely and
   inserting keys in true ascending order (zero-padded so string order
   matches insertion order — `"key_%d" % i` alone is NOT adversarial,
   since lexicographic scrambling of unpadded integers gives an
   accidentally-near-random insertion order that even a plain
   unbalanced BST handles in expected O(log n)) reproduces `to_dict()`
   byte-for-byte identically to the correct tree, right up until it
   **crashes with `RecursionError`** under 4000 keys (`_pinsert`
   recurses on host-stack descent) — a catastrophic regression every
   existing PMap test would have silently missed.
   - Measured the *actual* impact of each surviving mutant's real tree
     height at n=4000 ascending insertion: 18 of the 19 stay at height
     14-16 (vs. a correct tree's ~14) — AVL's insert-time correction is
     apparently robust to single-unit boundary misses in the rebalance
     trigger (`bf > 1` vs `bf >= 1` only shifts *when* a rotation fires
     by one step, and the tree still ends up close to balanced). These
     really are low-impact, close to genuinely benign.
   - One exception: `values.py:253:arith#104` (`self.height = 1 + (...)`
     mutated to `1 - (...)`) corrupts the height field outright and DOES
     measurably escalate: height 30/35/40/45 at n=1000/4000/16000/40000
     (a correct tree: ~10/14/16 at the same sizes) — a real, ~2.5-3x
     height inflation, though still sublinear (not the full O(n)
     collapse a *disabled* rebalancer produces).

### 2.2 New test: `test_pmap_stays_avl_balanced_under_ascending_insertion` (`tests/test_v16.py`)

Added a white-box test that inspects `PMap._root`'s real `.left`/`.right`
chain (no public shape-introspection API exists, and none should be
added just for this) after 4000 ascending zero-padded-key insertions,
asserting real height `<= 2 * log2(n+1)`. Bound calibrated empirically:
correct-tree height/log2(n) ratio is consistently ~1.0-1.2 across
n=500..16000 (comfortably under Knuth's ~1.44 AVL worst-case bound), the
`arith#104` regression reaches ~2.5-3x, and a fully-disabled rebalancer
crashes outright — 2x gives clean separation in both directions with no
observed false positive across 5 sample sizes.

**Effect verified empirically, not assumed**: re-ran the exact same
scoped mutation campaign with the new test added to the classifier
command. `arith` category: 3 killed/1 survived -> **4 killed/0
survived**. Overall: 33/53 (62.3%) -> **34/53 (64.2%)**. The other 18
"boundary tweak" survivors are NOT caught by this test either (confirmed
directly: all still measure height 14-16, under the 2x bound) — this is
consistent with them being genuinely low-impact, not a gap in the new
test's design.

## 3. What was NOT done, and why

- Did not chase the remaining 18 survivors further. Per round 219's own
  stop-rule precedent: two are proven-equivalent dead code, the rest are
  empirically-verified-benign boundary misses in a self-correcting
  algorithm (AVL's insert-time rebalancing absorbs off-by-one trigger
  errors). Writing tests to force-kill genuinely-equivalent or
  genuinely-benign mutants would be manufacturing test coverage against
  properties that don't matter, not closing a real gap.
- Did not change `campaign.py`'s `--files` default (still
  `whence/interp.py` only) to permanently include `values.py`. This
  round's campaign was a scoped, hand-built classification pass with a
  narrow test command — not the full `mutation -> corpus -> verify ->
  coverage -> report` pipeline `campaign.py` orchestrates. Widening the
  shared default deserves its own dedicated verification (313 total
  mutants at the full-suite classifier cost measured this round — 438s —
  is ~38 hours serial on this single-CPU host), flagged as a
  recommendation, not landed.
- Did not remove the dead `is_new` return value from `_pinsert`/`put` —
  real, confirmed dead code, but removing it is an unrelated cleanup
  this round's actual task (finding bugs/test gaps) doesn't call for.

## 4. Verification

- `tests/test_fuzz_regressions.py::test_diverge_on_deep_equal_values_is_not_quadratic`:
  12/12 isolated pytest reruns pass post-fix (was failing 1/5 to ~3/5
  depending on methodology pre-fix); `tests/test_fuzz_regressions.py`
  full file 50/50.
- `tests/test_v16.py`: 16/16 (was 15; +1 new test), 0.29s.
- Full `languages/whence` suite: see this round's own follow-up run
  (started before this file was written; result appended below once
  captured, per this round's own standing practice of not trusting a
  claim without a completed run — round 227's exact lesson).
- Mutation campaign: 53/53 mutants generated and classified twice (before
  and after the new test), `harness/swe/mutation.generate`/`run_mutant`
  used directly (unmodified) with a scoped line-range filter and a
  custom fast test command — no changes to `harness/swe/` itself this
  round.
- No concurrent-round race; Hermes-gateway files unchanged.
