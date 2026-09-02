# Round 443 (SWE-loop D) — PREDICTIONS, written before any measurement of the new code

House rule D-013. Written 2026-09-02 02:12 UTC, BEFORE a line of
`harness/swe/killers.py` was edited and BEFORE any of the runs in §C were made.

## Baselines, re-derived at HEAD this round, each with its command

| baseline | command | value at HEAD |
|---|---|---|
| the carried red, alone, venv | `.venv/bin/python3 -m pytest harness/tests/test_swe_campaign.py::test_review_stage_and_report -q` | **1 passed in 47.92s** |
| same, system python | `python3 -m pytest harness/tests/test_swe_campaign.py::test_review_stage_and_report -q` | **1 passed in 43.64s** |
| curated examples | `cd languages/whence && git ls-files examples \| grep -c '\.lang$'` | **18** |
| uncurated (`listdir`) examples | `ls languages/whence/examples/*.lang \| wc -l` | **33** |
| foreign `.lang` files present | per-file `git ls-files --error-unmatch` | **15** (14 named in `.gitignore` + `agi_buy_and_hold.lang`, untracked, dropped 2026-09-01 23:12) |
| round 437's retry constant | `grep -n TIMEOUT_RETRY_FACTOR harness/swe/killers.py` | **3.0** |
| round 437's `compare` pins | `grep -c "^def test_" harness/tests/test_swe_killers.py` | 7 of them monkeypatch `behaviour`; **all are unit tests of `compare`** |

## What is already ESTABLISHED before this file (stated, not predicted)

- The carried next-step "`test_review_stage_and_report` is red, two candidate
  shapes, do not guess" is **stale twice over**. Round 437 ran it, refuted
  BOTH shapes with artefacts, diagnosed the real cause (an asymmetric timeout
  guard in `find_killer`), and fixed it. Rounds 438-442 carried the item
  forward anyway, verbatim, as "carried, NOT re-derived".
- Round 437's stated honest limit: *"this round did not observe the spurious
  kill. It cannot — the race is not schedulable."* Its evidence is
  circumstantial (path exists, 3.3x margin, 3x measured contention).
- `compare()` at HEAD re-measures a MUTANT-only timeout at `3.0x` the budget.
  `find_killer` still handles the ORIGINAL's timeout with a single
  measurement, `continue`, and `orig_cache[src]` — and `stage_corpus` passes
  ONE `cache` dict across every mutant in the campaign.

## Predictions

### A. The race is schedulable after all (making 437's circumstantial case direct)

- **A1** [computed, narrow] Monkeypatching `TIMEOUT_RETRY_FACTOR` to `1.0`
  removes exactly the headroom round 437 added, so a stubbed mutant-only
  timeout that would settle at 3x still times out at 1x and `compare` returns
  **`"differs"`** — the pre-437 verdict, reproduced deterministically.
- **A2** [computed, narrow] Driven END-TO-END through a real `Campaign` on the
  inert `interp.py:604:const#366` mutant, that same setup makes
  `killers.json` read **`found: 1, no_killer: 0`** — byte-for-byte round
  433's symptom, `assert (0 == 1)` at `test_swe_campaign.py:310`.
- **A3** [computed, narrow] The identical setup with the constant left at
  `3.0` gives **`found: 0, no_killer: 1`** — green. A2 and A3 differ in one
  monkeypatched float and nothing else, which is what makes it an observation
  of the race rather than an argument about it.
- **A4** [machine-state] The new pin runs in **< 15 s** (stubbed `behaviour`,
  no interpreter work), warm or cold. If it needs a real `_copy_project` of
  the whence tree the floor rises to ~2 s but not past 15 s.

### B. The defect round 437's fix did NOT reach

- **B1** [computed, narrow] `orig_cache` is shared across every mutant of a
  campaign (`stage_corpus` builds `cache = {}` once, outside the loop), so a
  SINGLE spurious original-side timeout on program *p* removes *p* from the
  corpus of **every later mutant in the run**, not just the current one.
- **B2** [computed, narrow] Nothing counts it. With 3 programs where the
  original times out on one, `find_killer` returns `tried == 3` and
  `undecided == 0`: a `no_killer` claimed over 3 programs of which **2** were
  measured, spelled identically to one where all 3 were. This is the exact
  weakness round 437 invented `undecided` to expose, on the other side.
- **B3** [computed, narrow] The fix is symmetric with round 437's: re-measure
  the original at `TIMEOUT_RETRY_FACTOR` x budget before believing its
  timeout; count what stays unmeasured. Predicted cost on the paths that
  matter: **zero extra `behaviour()` calls** when the original completes
  first time — i.e. every program in the current corpus.
- **B4** [base rate] I expect the whence corpus to trip B1 **0 times in a
  solo run** (max solo example is 0.655 s against a 2 s budget) and to be
  reachable only under the 3x contention the driver itself produces. So B1 is
  a latent-denominator bug, not a currently-firing one, and I predict the new
  counter reads **0** on a real green run. If it reads non-zero on this box
  solo, my margin model is wrong.

### C. The runs this round will make

- **C1** [machine-state] `pytest harness/tests/test_swe_killers.py -q` at the
  end: **all pass, < 90 s**. It was not timed at HEAD before this file, so
  this band is a guess from the file's shape (mostly stubs) and is the
  shakiest line here.
- **C2** [computed] `test_review_stage_and_report` stays green and its
  `killers.json` still reads `no_killer: 1` after B3's change, because B3
  adds calls only on a path the corpus never takes (B4).
- **C3** [machine-state] I will NOT re-run the whole 592 s
  `test_swe_campaign.py` file; the round's wall clock (deadline ~03:00 UTC,
  banked at 02:12) does not hold it alongside the work. Recorded here in
  advance as a deliberate omission, not a result.
