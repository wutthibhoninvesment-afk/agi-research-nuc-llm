# Round 395 (SWE-loop D) — predictions, banked before measurement (D-013)

Banked 2026-08-31 ~10:00Z, before writing any new code and before running
any command in §P below.

Task: round 392's next-step item 3 — *"`bench/ref_diff.py` was dead for six
rounds (386-391) ... Any round between 386 and 391 that quoted it quoted a
command that could not run; a sweep of `knowledge/round-38*.md` and this file
for citations of it is worth one SWE-loop(D) pass. `--fuzz` has never been run
against v0.33 or v0.34."*

## §0 OBSERVATIONS ALREADY MADE (not predictions — do not score)

These were read while choosing the task, before this file existed. Recorded so
that nothing below can be scored as foresight it did not have.

- O1. `extract_head` occurs exactly twice in the repo outside
  `state/swe/round-137/orig-proj/`: its own `def` and its own call site, both
  in `bench/ref_diff.py`. No test names it.
- O2. `grep -n ref_diff knowledge/round-38{6,7,8,9}-*.md
  knowledge/round-39{0,1}-*.md` → 0 hits. The same grep over
  `state/research-state.md`'s `### Round 386` … `### Round 392` span → 0 hits.
- O3. Rounds whose knowledge file cites `ref_diff`: 108 110 113 144 146 155
  162 168 174 176 188 192 204 206 294 296 300 302 303 306 312 318 320 324 326
  330 347 350 353 392.
- O4. `languages/whence/whence/foreign.py` was ADDED in commit `4c05cf4`
  ("Round 387 (skills B): … and round 386, landed").
- O5. `MODULES` was the literal `("__init__", "ast_nodes", "interp", "lexer",
  "parser", "values")` at every revision of `ref_diff.py` before `1b18b2c`
  (round 392), which replaced it with an `os.listdir` derivation.
- O6. `whence/timetravel.py` was added in `8637795` and was never in the
  literal `MODULES`.
- O7. `whence/interp.py:54` and `whence/parser.py:11` both `from .foreign
  import …`.
- O8. All five `ref_diff` tests in `languages/whence/tests/test_v10.py` pass
  `--ref <dir>`.
- O9. `nproc` = 1; load average 0.28; 1.5 GiB of 2.0 GiB swap in use.

## §P PREDICTIONS

### The liveness sweep (does the published dead interval reproduce?)

- **P1.** Executing `ref_diff.py`'s liveness precondition (`extract_head` +
  `load`) at EVERY commit in the repo's history that touched
  `languages/whence/whence/**` or `languages/whence/bench/ref_diff.py` finds
  **exactly one** dead interval — there is no earlier, unknown one.
- **P2.** That interval's first dead commit is **`4c05cf4`** and its last is
  **`21538a8`**. The tool was therefore dead at the HEAD of rounds **387-391
  — five rounds, not the published six.** Round 386's session ran against a
  HEAD (`3772ac6`) whose `interp.py` did not yet import `.foreign`, so the
  tool was ALIVE for the whole of the round that wrote the module.
- **P3.** The dead interval is **≤ 10 commits** long.
- **P4.** The probe returns ALIVE at every commit from `8637795` (which added
  `timetravel.py`) to `4c05cf4`, despite `timetravel` never appearing in
  `MODULES` — a module absent from a hand-written list costs **nothing** until
  something in the extracted set imports it.
- **P5.** The full-history liveness sweep completes in **< 180 s** wall clock
  on this box.

### The citation sweep (is there anyone to warn?)

- **P6.** Deriving the citation set from `ref_diff.py`'s OWN OUTPUT STRINGS
  (its `print` format literals, read out of the source rather than typed by
  hand) instead of from its filename finds **zero** additional citing rounds in
  386-391. Round 392's item 3 has an **empty subject set under both
  derivations**.
- **P7.** The newest citation of the tool anywhere in `knowledge/` or
  `state/research-state.md` before round 392 belongs to round **353** — a
  **39-round** gap in which the tool was not invoked by any round, of which
  only the last five are the ones round 392 named.

### The fix that moved the failure rather than removing it

- **P8.** Round 392's derived `MODULES` introduces a NEW failure mode:
  a `whence/*.py` present in the WORKING TREE but not at HEAD makes
  `extract_head` die with `subprocess.CalledProcessError` from `git show`,
  because `MODULES` is derived from the working tree while the extraction
  reads HEAD. The round that ADDS a module now breaks the tool for itself.
  Demonstrated hermetically, in a copy, without touching the real tree.

### The differential that has never been run across a version

- **P9.** `ref_diff.py --counters --ref <v0.33>` over all `examples/*.lang`
  in all three modes: **0 differing (file, mode) pairs and 0 NEWSYNTAX
  lines.**
- **P10.** `ref_diff.py --fuzz 395 -n 120 --modes direct,fast,slow --ref
  <v0.33>`: **0 (program, mode) pairs differ.**
- **P11.** P10's reason is structural, not luck. `--fuzz` calls `parse(src)`
  and `continue`s on `ParseError`/`LexError`, and v0.34's entire behavioural
  delta is in ParseError messages and hints. **The fuzz differential is blind
  to v0.34 by construction: 100 % of the version's changed surface is
  unreachable from a corpus of programs that parse.**
- **P12.** The same command against **v0.21** (round 350's version, the last
  round that cited the tool) yields **> 0** differing pairs.
- **P13.** Neither fuzz run finds a real Whence interpreter bug. Round bug
  count: **0 in the language, ≥ 1 in the tooling.**

### Costs and baselines

- **P14.** The new `extract_head` liveness test measures **< 3.0 s**.
- **P15.** `languages/whence/run_tests_fast.sh` at HEAD today is **1758
  passed, 3 skipped, 81 deselected** (round 392's figure), unchanged.
- **P16.** `harness/run_tests_fast.sh` at HEAD today is **780 passed, 268
  deselected** (round 392's figure), unchanged.
