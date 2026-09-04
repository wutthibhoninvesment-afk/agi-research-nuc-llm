# Round 497 (SWE-loop D) — predictions, banked BEFORE any measurement

**Rule:** CLAUDE.md D-013. Written and committed before a single number below
was measured. Scored honestly in the round's knowledge file.

**Subject:** round 491's next-step #1 — *"The next lever is the COPY, not test
selection. `_copy_project` is 4.87 s of every 12.78 s mutant — 38 % of the
remaining 6.2 h — and it is invariant to every selection improvement, because
it copies a 562 MB checkout per mutant."* Plus its #5 (`nodecampaign.py` has
no CLI) and #2 (the ledger is 55 of 1794).

## Already OBSERVED before banking (NOT predictions — do not score these)

Rounds 493/494/495/496 each separated read facts from predicted ones; same here.

* O1. `harness/swe/mutation.py:_copy_project` is a single `shutil.copytree`
  with `ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".venv",
  "research-env", "*.egg-info", ".git", "node_modules")` plus a
  `write_example_curation` call. Read from the source.
* O2. `run_mutant` writes the mutant with `open(dst/m.path, "w")` — a
  truncating open on a path inside the copy. Read from the source.
* O3. `du -sh` at HEAD, run while orienting: repo 1.3 G, of which
  `node_modules` 468 M and `.git` 52 M are ignored; `logs` 439 M,
  `languages` 100 M, `state` 73 M, `nuc` 25 M, `harness` 11 M,
  `skills` 6.8 M, `knowledge` 5.9 M are not.
* O4. `state/swe/perturbation-mutation-ledger.jsonl` has 55 records; the
  round-491 slice reported 12.78 s/mutant, 40 killed / 15 survived,
  12 distinct subsets all clean, and left 34 of 89 in-scope sites unrun.
* O5. `nproc` on this box is 1. Every measurement below is planned solo.

## Predictions

### The cost that is being attacked

* **P1.** Re-derived at HEAD, `_copy_project(repo_root)` costs **4.0–7.0 s**
  (round 491 measured 4.87 s; `logs/` grows every round, so the honest band
  is "at least as slow as round 491's, not much more").
* **P2.** `logs/` is **≥ 55 %** of the bytes the copy moves.
* **P3.** The copied tree contains **5,000–20,000 regular files**.

### The proposed lever: hardlink the tree instead of copying its bytes

* **P4.** A hardlink copy of the same tree costs **≤ 1.0 s**, i.e. **≥ 5x**
  faster than the byte copy. (Prediction is about the ratio; a link copy does
  a `link(2)` per file and no data movement.)
* **P5 (control, expected TRUE — bank it so the guard is justified by a
  demonstration, not by an argument).** With a naive hardlink copy and
  `run_mutant`'s existing truncating `open(..., "w")`, writing the mutant
  source **modifies the file it was linked from**. If this is FALSE the whole
  safety half of this round is unnecessary and I will say so.
* **P6.** With `unlink`-before-write, the source file is byte-identical after
  a mutant is written and run. Verified by digest, not by argument.

### What the tests do to a tree they think is theirs

* **P7.** Over a slice of ≥ 20 mutants, a stat witness over the linked-from
  master tree reports **ZERO** drifted files. I.e. `nuc/tests/test_perturbation.py`
  never writes into the tree it runs in. If this is non-zero, the drifted
  paths are the round's finding and the linked copier must be reported as
  unsafe for this subject.
* **P8.** pytest's own scratch (`.pytest_cache`, `__pycache__`) causes **no**
  drift, because both are in the ignore list, so the sandbox creates them
  fresh rather than linking them.

### Soundness: does the cheaper copy change any verdict?

* **P9.** Replaying **≥ 10** already-scored mutants from the ledger under the
  linked copier reproduces the ledger's `status` for **100 %** of them.
* **P10.** The replay's per-mutant seconds are **< 60 %** of the ledger's
  recorded seconds for the same mutant ids.

### The campaign

* **P11.** A linked slice reports `seconds_per_mutant` **< 8.0 s**
  (from 12.78 s).
* **P12.** The linked slice's kill rate lands within **72.7 % ± 15 pp** on the
  mutants it newly scores.
* **P13.** The projected cost of the remaining ~1739 sites falls **below
  4.0 h** (from 6.2 h).
* **P14.** Round 491's next-step #4 gets a second data point and it is again
  **0 poisoned subsets** — `nodeguard` still never fires on this suite.
* **P15.** The slice scores **≥ 40** new mutants inside its budget, taking the
  ledger past **95** records total.

### Pre-registered, NOT scorable by this round

* **P16.** The `logs/`-exclusion lever (copy less) and the hardlink lever
  (copy nothing) are alternatives. I predict hardlinking wins outright and
  that no exclusion of `logs/` is needed. A later round that measures a
  `logs/`-excluded byte copy can falsify this; this round will measure the
  byte total but not build the second lever.
