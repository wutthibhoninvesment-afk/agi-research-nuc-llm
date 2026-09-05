# Round 516 (language C) — predictions, BANKED BEFORE MEASURING (D-013)

Assignment: round 512's next steps #3, #4 and #6 — all three are the same
defect one level in from where round 512 stood. Round 512 measured ledger
FRESHNESS from OUTSIDE (`corpusledger.py`: a ledger is fresh iff re-running
its declared generator reproduces it byte for byte) and left three findings
about the ledgers' OWN `--check` verbs:

  * #3 `builtinlive`/`runlive` do not self-declare a regeneration command.
  * #4 `subjprov.py --check` returned 0 on a demonstrably stale ledger.
  * #6 `assertshadow.py`'s CLI prints headline totals nothing compares.

THE QUESTION THIS ROUND ASKS, which is one question and not three:
**for each generated ledger in `state/whence/`, which of the artefact's own
top-level keys can its `--check` verb actually SEE?** Measured by mutation:
perturb exactly one key, run the verb, record whether the verb notices.

Everything below is written from STATIC reading only. Nothing has been run
except `corpusledger.py --list` (which prints the registry and runs no
generator). No `--check` verb has been executed, no mutation has been made.

## A. Baseline

* **P1** `corpusledger.py --check` at HEAD reports **5 FRESH, 1 SKIP, 0
  STALE**. Rounds 513/514/515 touched `skills/`, `nuc/` and `harness/`;
  round 515's only edit under `languages/whence` was `corpusledger.py`'s
  `ROOT` line, which no generator reads.

## B. Key coverage of each `--check` verb (the round's measurement)

Verdicts: **SEES** (verb reports a finding / non-zero rc), **BLIND** (verb
prints its agreement line and exits 0), **CRASH** (verb raises).

* **P2** `assert-shadow-census.json` — 8 top-level keys. `--check` calls
  `check_census` (`nodes`), `check_coordinates` (`nodes`) and `check_costly`
  (`costly_nodes`). Predict **SEES 2** (`nodes`, `costly_nodes`), **BLIND 6**
  (`_what`, `_regenerate`, `_headline_predicate`, `totals`, `by_file`,
  `_history`). No CRASH — every read is a `.get` with a default.
* **P3** `subject-provenance.json` — 11 top-level keys. `check_ledger` reads
  `declared["totals"]` (SUBSCRIPT, not `.get`) and `declared.get(
  "costly_dataflow")`. Predict **SEES 2**, **BLIND 9** (`pairs`,
  `disagreements`, `_helpers_ignoring_arguments`, `costly_unguarded`,
  `_what`, `_regenerate`, `_lattice`, `_derived`, `_assumption`), and
  **`totals` CRASHes under DELETE while it SEES under CORRUPT** — the one
  key whose verdict depends on the mutation kind.
* **P4** `builtin-liveness.json` — 3 keys. `check()` reads `by_verdict` only.
  Predict **SEES 1**, **BLIND 2** (`counts`, `n_builtins`).
* **P5** `builtin-runtime.json` — 8 keys. `check()` reads `runtime`,
  `by_verdict`, `n_errors`. Predict **SEES 3**, **BLIND 5** (`_what`,
  `counts`, `n_builtins`, `n_ran`, `contract_checks`).
* **P6** `testcorpus-contributions.json` — the one ledger round 512 found
  CORRECTLY RED. Predict its verb is nonetheless **NOT total** either: it
  sees strictly fewer than all of its own top-level keys.
* **P7 (the headline)** Aggregate over all five generated ledgers: **fewer
  than 35% of top-level keys are visible to the ledger's own `--check`**,
  and **no verb in this tree is total over its own document** (0 of 5).

## C. Testability

* **P8** Two of the five verbs cannot be pointed at a candidate file at all:
  `subjprov.main` calls `load_ledger()` with no path and `assertshadow.main`
  calls `load_census()` with no path, so the ONLY way to run either against
  a mutant is to overwrite the real ledger. `builtinlive`/`runlive` take
  `--ledger`; `depthcensus` — unknown, predict it takes a path too.
  A check verb that can only read one hardcoded path cannot be tested
  without endangering the artefact, which is why nobody measured this.

## D. The repairs

* **P9** Round 512's next-step #3 names the WRONG FUNCTION. `_write` is
  shared with `--json`, which dumps the FULL census; the declaration belongs
  in `ledger_view`. Predict the fix is in `ledger_view` in both files.
* **P10** The `UNDECLARED` entry's stated reason — "a `_regenerate` key in
  the artefact would not survive its own regeneration" — is **FALSE**.
  `ledger_view` is a pure function of the census, so a constant it emits is
  reproduced on every run. Predict: after the change, `corpusledger --check`
  reports both `builtin-*` ledgers **FRESH** and `--list` reports
  **5 self-declaring, 0 declared here, 1 not generated**.
* **P11** Adding `_regenerate` to `ledger_view` does NOT redden
  `builtinlive`/`runlive`'s own `check()`, which reads only `by_verdict` /
  `runtime` / `n_errors`. Predict `--strict` stays rc 0 for both.
* **P12** No existing test pins the top-level KEY SET of
  `builtin-liveness.json` or `builtin-runtime.json`, so P11's change reddens
  nothing in the fast tier. (Predicting an ABSENCE — round 515's bank earned
  the rule that this is the most expensive prediction to get wrong, so it is
  written as a prediction and checked by grep rather than assumed.)
* **P13** After making `subjprov --check` and `assertshadow --check` total,
  both report **0 findings at HEAD** — the ledgers really are fresh (P1), so
  a total predicate must agree with the partial one on a fresh tree. If
  either reports a finding at HEAD, the ledger was stale in a way round
  512's byte-comparison could not have missed, and P1 is wrong.

## E. Suites

* **P14** `languages/whence/run_tests_fast.sh` at HEAD is green
  (round 515 measured 2999 passed / 3 skipped / 0 failed, 438.96s). Predict
  the same node count at HEAD and **> 2999 with this round's new tests**.
* **P15** This round adds ≥ 12 new test nodes.
