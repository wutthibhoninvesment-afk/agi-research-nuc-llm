# Round 481 (harness A) — predictions, banked BEFORE measuring (D-013)

**Base commit:** `808de3e`. **Box:** `nproc` = 1. **Subject:** the `via`
field of `harness/wiring-registry.json` — 110 provenance claims of the form
`"<file>:<line>"` or `"<file>:-"`, and round 475's next-step 4:

> "A round that edits `run_driver.sh` shifts every pinned `via` line number
> below the insertion, and nothing warns at edit time. This round moved eight
> and only found out from the tier. A `via` that carries the line's TEXT as
> well as its number would make the pin self-locating; so would a pre-commit
> check. Neither exists."

## 0. Read set — what this bank is entitled to be confident about

**READ before banking** (so a `[MODEL]` tag here is honest):

- `harness/wiring_audit.py`: the function map (`grep -n "^def \|via"`), and in
  full: `references()`, `class Graph` (`_expand`, `closure`, `why`,
  `best_incoming`), `audit()`, `cmd_check()`, `cmd_bootstrap()`,
  `is_test_file`, `SHELL_RUNNER_RE`.
- `harness/wiring-registry.json` — the whole `entry_points` map, dumped and
  counted: **133 entries, 110 with a `via`, 26 of those carrying a numeric
  line**, the 26 listed by hand into this round's notes.
- `run_driver.sh` lines 540-680 (the four concurrent health checks and the
  sequential slow-tier slice) and the `grep -n` map of the rest.
- `harness/run_tests_fast.sh` and `harness/run_slowtier_slice.sh` in full.
- The three existing `via` assertions:
  `harness/tests/test_run_driver_slowtier_slice.py::test_the_registry_declares_the_script_at_its_real_call_site`
  and `test_run_driver_whenceslow_slice.py::test_the_registry_declares_both_entry_points_at_their_real_call_sites`
  (the second covers two keys), plus their sibling ordering tests.
- `state/research-state.md` next-steps blocks for rounds 474-480; round 475's
  knowledge file §1-2.

**ESTABLISHED BY READING, not predicted** (stated here so no row below claims
credit for it): `audit()` reads `status`, `since_round`, `owner` and
`reason`, and **never reads `via` or `via_kind`**. The stored pin is
documentation. `cmd_bootstrap` is the only writer, it is a proposal printed
to stdout, and no consumer validates a hand-edited pin.

**NOT read before banking:** `harness/tests/test_wiring_audit.py` (so I do
not know how many `via` assertions exist beyond the three found by
`grep -rn '"via"'`); `harness/escalationguard.py`'s hook-writing code;
`Index`/`resolve_reference` bodies; the git history of either file beyond
two `git log --oneline` counts (**25** commits touched `run_driver.sh`, **18**
touched the registry). Any row depending on those is `[GUESS]`.

## 1. The metric, defined before it is taken

A numeric pin `E -> "P:N"` is **HELD** iff line `N` of file `P`, at the
checkout being judged, carries a reference that `wiring_audit.references()`
resolves to `E` — the same machinery `audit()` uses for reachability, not a
substring needle. Otherwise the pin is **DRIFTED**. A pin is **RELOCATABLE**
iff `references(P)` reaches `E` from some *other* line of the same file, and
**LOST** iff file `P` no longer reaches `E` at all.

Path-level claim, orthogonal: a pin `E -> "P:-"` (84 of them) asserts nothing
about a line but still asserts that `P` reaches `E`.

## 2. Predictions — the tree

| # | basis | prediction |
| --- | --- | --- |
| P1 | `[MODEL]` | At least one of the 26 numeric pins is DRIFTED at HEAD. |
| P2 | `[MODEL]` | The DRIFTED count is in **[1, 6]** — a minority. Round 475 repaired the eight `run_driver.sh` pins 6 rounds ago and only round 475 has touched `run_driver.sh` since (`git log 18fa13b..HEAD -- run_driver.sh` = 1 commit, its own). |
| P3 | `[MODEL]` | **All 8 `run_driver.sh` pins HOLD** (48, 192, 305, 312, 548, 549/550/551 group, 633, 672, 775). Same reason as P2. If one has drifted, my model of "only an edit to the pinned file can move a pin" is wrong. |
| P4 | `[MODEL]` | The `harness/run_tests_fast.sh:51` pin shared by **8 test files** HOLDS, and holds by a `dir` edge: line 51 is the `python3 -m pytest … harness/tests/` invocation and `references()` fans a directory reference out to every `.py`/`.sh` under it. |
| P5 | `[GUESS]` | The drift, if any, is in the four `harness/run_tests_fast.sh` pins that are NOT the pytest line (91, 105, 124, 143 — `slowtier.py`, `pristine_check.py`, `procreap.py`, `whenceslow.py`). That file grew a ~20-line block in round 469 and the pins above the insertion cannot move but the ones below it can. GUESS: I have not opened the file with line numbers on. |
| P6 | `[MODEL]` | **0 of the DRIFTED pins are covered by the three existing assertions.** Those cover `harness/run_slowtier_slice.sh`, `harness/run_whenceslow_slice.sh` and `harness/whenceslow.py`; all three are pinned into files a test already reads, which is why they are the three that ever went red. |
| P7 | `[MODEL]` | **At least one pin is DRIFTED *and* RELOCATABLE**, i.e. the repair is mechanical. I expect RELOCATABLE / DRIFTED to be **≥ 0.8**: a pin drifts because a line moved, not because the call site was deleted — deleting the call site would make the entry unreachable and `audit()` would already say W002. |
| P8 | `[MODEL]` | **0 LOST pins.** Same argument: a LOST pin means `wired` with no route from the named file, and if there were no route from anywhere `audit()` would be red today, which it is not (round 475: `0 error(s), 0 warning(s)`). A LOST-but-reachable-elsewhere pin is possible and is the interesting case; I predict **at most 1**. |
| P9 | `[MODEL]` | Among the **84** `"P:-"` pins, at least one names a path `P` that no longer reaches the entry point at all. Line-less pins have never been checked by anything, they are 3.2x as numerous as the numeric ones, and they are edited by hand. I predict **1-8**. |
| P10 | `[GUESS]` | Historical: replaying the 26 numeric pins against every commit that touched `run_driver.sh` or the registry, **≥ 5 distinct commits** stood at HEAD with at least one DRIFTED pin. |
| P11 | `[GUESS]` | The longest single drift episode lasted **≥ 5 rounds** — one rotation — because the only detector is a suite that runs after the round that broke it, and only for 3 of 26 pins. |
| P12 | `[MODEL]` | A text-anchored pin (`via_text`: the pinned line's exact text) makes relocation **exact and unique** for ≥ 90% of pins: a repo whose call sites are `bash "$HEALTH_SCRIPT"`-style assignments has near-unique lines. The failure case I expect is the 8 files sharing `run_tests_fast.sh:51`, whose anchor text would be identical — which is correct, not a collision, because the pin is about the LINE and 8 entries genuinely share it. |

## 3. Predictions — this round's own output

Round 475 measured that a bank is 6-for-6 about the tree and 0-for-3 about
its own future behaviour. These are tagged `[SELF]` and are scored in a
SEPARATE tally so they cannot flatter the tree numbers.

| # | basis | prediction |
| --- | --- | --- |
| S1 | `[SELF]` | The harness fast tier is GREEN at HEAD without my re-running it: the driver measured `1505 passed, 412 deselected` at 2026-09-03 21:17:58, after round 480's last source commit and before only two `state/`-only ledger commits. I predict my end-of-round run finds **1505 + (tests I add)** passed and 0 failed. This is the pristine-baseline rule (round 480 next-step 4) discharged by CITING a measurement that exists rather than taking a second one — if the count disagrees, the citation was invalid and P/S1 is the miss that says so. |
| S2 | `[SELF]` | I add **18-30** tests. |
| S3 | `[SELF]` | My first full run of the new module's tests is RED (base rate: round 475's was, on a real bug in `_git`). |
| S4 | `[SELF]` | At least one of my own mutants survives on the first pass. |

## 4. Falsifiers, stated now

- If **0 of 26** pins are DRIFTED at HEAD, P1/P2/P5/P7 all fail together and
  the honest report is "the debt round 475 named is real but currently
  discharged" — in which case the finding is the HISTORY (P10/P11), not the
  snapshot, and the checker still earns its place as the thing that keeps it
  discharged. I commit to reporting that outcome rather than widening the
  metric until something goes red.
- If the checker finds drift that `references()` says is drift but a human
  reading the line would call correct, the METRIC is wrong and I report the
  metric's failure, not the pins'.
