# Round 518 (language C) — predictions, BANKED BEFORE MEASURING (D-013)

Assignment: round 516's next steps **#2**, **#3** and **#4**, carried forward
unchecked by round 517 (its next-step #5).

  * #2 `runlive.check`'s `a is not None` guard makes `by_verdict` — a whole
    key of `builtin-runtime.json` — unobservable to the gate that guards it.
    Measured, named and LEFT STANDING by round 516 because deleting the
    guard changes what `--strict` reddens on.
  * #3 the post-repair `checkscope --scope` sweep was never run. Round 516
    published an as-found table and repaired two gates; nothing has measured
    the tree since.
  * #4 `checkscope` is now imported by `subjprov` and `assertshadow`, two of
    the gates it measures. "Benign, but a real edge and nothing tests for it."

Everything below is written from STATIC READING ONLY: `checkscope.py`,
`runlive.py`, `builtinlive.py`, `assertshadow.py`, round 516's round file and
its banked `checkscope-as-found.json`. **No `--check` verb has been run this
round, no sweep has been started, no mutation has been made.**

## A. The artefact round 516 banked

* **P1** `state/whence/round-516/checkscope-as-found.json` is the
  **CONFOUNDED** run, not the corrected one. It reports `totals` = 32 keys /
  9 seen over **five** `ok` ledgers, including `testcorpus-contributions.json`
  as `ok` with both keys `SEES`; the knowledge file publishes **30 keys / 7
  seen over four**, and its own §"the apparatus lied twice" refutes exactly
  the contributions row the JSON credits. No row in the JSON carries the
  `encoding` / `encoding_control` fields `scope_one` writes today, which
  dates it before the encoding fix. Predict: **nothing** — not the JSON's
  `_what`/`_method`, not the knowledge file, not any test — says the banked
  artefact is the run its own round file refutes.

## B. The BEFORE sweep, at HEAD (the round's first measurement)

Verdicts: SEES (gate exits non-zero), BLIND (exits 0), CRASH (traceback).

* **P2** `builtin-runtime.json` — 9 top-level keys today (`_regenerate` was
  added by round 516 after the as-found run). Status `ok`. Predict **sees
  2/9**: `n_errors` and `runtime` SEES; `_regenerate`, `_what`, `by_verdict`,
  `contract_checks`, `counts`, `n_builtins`, `n_ran` BLIND. **`by_verdict` is
  BLIND under BOTH `delete` and `corrupt`** — `a = old.get("by_verdict",
  {}).get(v)` is `None` in both cases and `a is not None` swallows it.
* **P3** `builtin-liveness.json` — 4 keys today. Predict **sees 1/4**:
  `by_verdict` SEES (both kinds); `_regenerate`, `counts`, `n_builtins`
  BLIND.
* **P4** `assert-shadow-census.json` — 8 keys. Round 516's `_residual` is a
  `document_diff` over the whole document minus `nodes`/`costly_nodes`
  (reported by other codes) and four history-only totals. Predict **TOTAL,
  8/8**, every key SEES under both kinds.
* **P5** `subject-provenance.json` — 11 keys. Round 516's S003 is
  `document_diff(declared, build_ledger(...), ignore=("totals",
  "costly_dataflow"))` and both ignored keys have their own code. Predict
  **TOTAL, 11/11**, and `totals` now **SEES under DELETE** rather than round
  516's CRASH (the subscript became a `.get`).
* **P6** `testcorpus-contributions.json` — 2 keys. Under the CORRECTED
  apparatus (mutant written in the ledger's own encoding, second control on a
  re-serialised copy) predict the row is **`ok`, not CONFOUNDED**: the file is
  written `indent=1, sort_keys=True` and `detect_encoding` reproduces it, so
  the re-serialised control is byte-identical and passes. Predict **2/2
  SEES** — and that this totality is **earned by one node**,
  `test_the_ledger_on_disk_round_trips_through_its_own_encoding`, which fires
  on any change whatever. Sub-prediction **P6b**: re-running that gate with
  that node deselected drops it below 2/2.
* **P7** `checkscope.py --scope --strict` at HEAD exits **1** (two gates not
  total).
* **P8** The full five-ledger sweep costs **300–900 s** of wall clock on this
  one-core box, dominated by `builtin-runtime.json` (20 gate runs, each an
  interpreted run of every program in `examples/`).

## C. The repair (#2)

* **P9** The right fix is NOT deleting the `a is not None` guard. It is round
  516's own move, applied to the two gates it did not reach: replace the
  hand-enumerated key comparison with `checkscope.document_diff(declared,
  ledger_view(c))`, the predicate that is total by construction because
  `ledger_view` is a pure function of the census. Predict that makes **both**
  gates total: `builtin-runtime.json` **9/9**, `builtin-liveness.json` **4/4**.
* **P10** The price is ZERO on this tree: `runlive.py --strict` and
  `builtinlive.py --strict` both still exit **0** after the change, because
  `corpusledger.py --check` reports both ledgers FRESH — freshness is exactly
  the property `document_diff` tests.
* **P11** After the repair `checkscope.py --scope --strict` exits **0** and
  `render_scope` prints all five ledgers under `total gates:`.
* **P12** The AFTER sweep's headline: **34 keys, 34 seen** (8 + 11 + 4 + 9 +
  2), against the BEFORE sweep's 34 keys / 24 seen.
* **P13** No EXISTING test in `languages/whence/tests/` has to be edited for
  the repair — only added to. (The risk being that some test pins the
  `MOVED  <name> a -> b` / `VERDICT SET MOVED` line text that
  `document_diff` replaces. Predict the pins are on `check()`'s boolean, not
  on its prose.)
* **P14** Tests added this round: **≥ 12**.

## D. The import edge (#4)

* **P15** Exactly **two** modules under `languages/whence/` import
  `checkscope` today (`assertshadow._residual`, `subjprov.check_ledger`),
  both **lazily inside a function body** rather than at module scope, and
  each uses exactly **one** attribute: `document_diff`. After this round it
  is **four** modules and still one attribute.
* **P16** WHY it is benign, stated so it can be falsified: `document_diff`
  is a pure function of its two arguments — its body reads no module-level
  name except the two private renderers `_summarise` / `_short`, no path, no
  environment variable, no file.
* **P17** The edge is not benign for any OTHER attribute, and this is the
  fact worth pinning: `checkscope.LEDGER_DIR` is computed at import from
  `AGI_RESEARCH_ROOT`, which `run_gate` SETS to the mirror root for the
  pytest gate. A gate reaching for `checkscope.LEDGER_DIR` would read the
  MUTANT directory while being measured. Predict: true today, and untested.
