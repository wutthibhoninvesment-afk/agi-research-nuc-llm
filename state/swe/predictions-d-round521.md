# Round 521 (SWE-loop D) — predictions, banked BEFORE measuring (D-013)

Banked after the RED DEBT was reproduced and its cause was read out of
`logs/health_round_517.log`, and BEFORE a line of `harness/swe/mutation.py`,
`harness/swe/linkcopy.py`, `languages/whence/tests/test_polarity.py` or
`harness/crosstrack-registry.json` was edited, and before any new scanner
existed.

## What is already established at bank time (NOT predictions)

Read, not guessed — recorded here so no item below can be scored as a hit
for something that was already on screen:

* `harness/tests/test_redattrib.py::TestThisTree::{test_the_cli_audit_exits_zero_on_this_tree,
  test_the_registry_is_fail_closed_over_the_live_logs}` reproduce solo
  (`2 failed, 58 passed in 2.68s`), one cause: `R001` for
  `harness/tests/test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files`.
* That node passes solo now (`1 passed in 1.16s`) and was red in exactly one
  retained log, round 517's.
* Round 517's failure body: `_collect(... -m swe_slow)` got rc 2 because
  `ERROR collecting harness/tests/test_swe_oraclekill.py` —
  `shutil.Error: [('…/languages/whence/_r438_suffix.lang', …, "[Errno 2] No
  such file or directory")]`, raised from `swe/mutation.py:493`
  `shutil.copytree`, called at `test_swe_oraclekill.py:37`, **module scope**.
* `languages/whence/tests/test_polarity.py::test_the_two_counterexamples_disagree_when_actually_run`
  writes `_r438_suffix.lang` / `_r438_infix.lang` into the LIVE
  `languages/whence/` directory and `os.remove`s them in a `finally`.
* `harness/tests/test_snapshot_race.py` (round 343) already exists and is the
  READ side of this class: module-level snapshot + live root.

## Predictions

**P1 — the vanish is deterministically reproducible without a race.**
`shutil.copytree` raises `shutil.Error` (not `FileNotFoundError`) when an
entry it has already listed is unlinked before `copy2` reaches it, and I can
force this in a unit test with a source tree plus a `copy_function` that
deletes the next sibling — no timing, no sleep, no second process. The
exception's `args[0]` is a list of `(src, dst, why)` 3-tuples.

**P2 — `swe/linkcopy.py`'s `MasterTree` is vulnerable to the same vanish**,
because it makes sandboxes out of the same tree by the same walk. Predicted
BROKEN in the same way (raises rather than skipping) before this round.

**P3 — module-import-time copies are the amplifier, and there is more than
one.** The count of test modules under `harness/tests/` that call
`_copy_project` / `copytree` / `MasterTree` at MODULE SCOPE (so the failure
is a *collection* error that aborts the whole directory, not a test failure
that costs one node) is **≥ 2 and ≤ 6**. Point estimate **3**.

**P4 — the write side has more than one instance.** The number of DISTINCT
test functions in the repo that create a file inside a live checkout tree
(`languages/whence/`, `harness/`, `nuc/`, not a `tempfile` dir) and remove it
again is **≥ 2**. Point estimate **3**. `test_polarity.py`'s is one of them.

**P5 — a grep for the name cannot find the shape, again.** Grepping for
`_r438` finds exactly one file; a structural AST rule (a `open(..., "w")` /
`Path.write_text` whose path expression is rooted at a live-tree constant
used at function scope) finds strictly MORE call sites than a grep for any
one spelling of the filename. If it finds exactly the same set, P5 is
refuted and the grep was enough.

**P6 — the correct registry label for the tiering node is `whole-tree` with
`evidence: subject`, not `environmental`.** Reasoning banked in advance so it
cannot be back-fitted: the node's subject is *the collectability of the whole
`harness/tests/` directory as a subprocess*, which any module-scope failure
in any file in that directory — or in any tree those modules copy at import —
can abort. That is readable off the subject. R006 forbids `environmental`
unless the label was outcome-derived, and this one is not.

**P7 — adding that one entry closes both derived reds and nothing else.**
`python3 harness/redattrib.py audit` exits 0, and
`pytest harness/tests/test_redattrib.py` reports **60 passed, 0 failed**.
No R002 (the node HAS been red, so the entry is not orphaned).

**P8 — the vanish guard changes no existing outcome.**
`harness/tests/test_swe_mutation.py`, `test_swe_linkcopy.py` and
`test_swe_copyparity.py` pass unchanged after `_copy_project` becomes
vanish-tolerant; the guard is reached by zero existing assertions.

**P9 — moving `test_polarity.py`'s scratch program out of the live tree is
SAFE**: `run.py` resolves the program path independently of `cwd`, so writing
`_r438_<stem>.lang` into a `tempfile.mkdtemp()` and passing the absolute path
with `cwd=here` unchanged still yields `{"suffix": 0, "infix": 1}`.

**P10 — this is the ONLY retained episode of this exact abort.**
`Interrupted: N error during collection` appears in exactly one harness
health log (517) — already checked — and I predict the whence-side ones
(rounds 393, 394) are a DIFFERENT cause, not a vanished-file copytree.

**P11 — cost accounting.** One ~2-second filesystem window inside one
language(C) test has cost, at the moment this round starts, **4 rounds ×
2 red nodes** of RED DEBT (518, 519, 520, 521) in a suite whose owner did not
cause it — plus the whole `swe_slow` tier being uncollectable for round 517.
I predict no round between 518 and 520 named the copytree as the cause.

**P12 — the harness fast tier runs solo in 400-560 s** at HEAD on this box
(`nproc` 1). Re-derived condition, not carried: round 515 measured 462.25 s
over 1680 tests, and rounds 517-520 have added nodes since.

**P13 — NO BASIS.** I cannot predict whether `write_example_curation`
(called by `_copy_project` after the copytree) has its own vanish exposure,
because I have not read it. Recorded as unpredicted rather than guessed; the
answer goes in the round file either way.
