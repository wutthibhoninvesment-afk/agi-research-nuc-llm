# Round 503 (SWE-loop D) — predictions, banked before measuring (D-013)

Written before any of the measurements below were run. Scored in full, misses
first, in `knowledge/round-503-*.md` §9.

Two of this round's measurements were already taken before the bank existed,
and are named here as **DISCLOSED** rather than predicted, because banking a
prediction after the fact is the failure this rule exists to prevent:

* **D1 (disclosed).** The three `skills-check` reds carried into this round as
  `owner skills(B)` are `carryforward K001`, `placeholder_check U001` and
  `unit_tests rc1`. I read `logs/corpus-evidence/round-502/*.out` before
  writing this bank and they name a single cause: round 502's knowledge file
  carries three unfilled placeholders and its prediction bank has no ledger
  entry. Not a prediction.
* **D2 (disclosed).** `nuc/tests/test_survivor_impact.py::test_owner_of_returns_the_innermost_def`
  fails with `ValueError: '            return 2' is not in list`. Read before
  banking.

---

## A. The inherited round-502 diff

* **A1.** D2's failure is entirely test-side: `survivor_impact.owner_of` and
  `enclosing_defs` need NO change. The literal in the test carries the
  indentation the source file had *before* `textwrap.dedent` stripped it.
* **A2.** After fixing A1 alone, `nuc/tests/test_survivor_impact.py` passes
  with **33** tests (round 502's knowledge file claims 33).
* **A3.** `nuc/tests/test_perturbation.py` at HEAD-with-the-dirty-tree is
  GREEN and holds **257** tests (round 502 re-collected a 257-unit map).
* **A4.** `harness/tests/test_swe_nodeid_selection.py` is green and holds
  between **14 and 22** tests.
* **A5.** Filling round 502's three placeholders and adding its bank row to
  `state/prediction-bank-ledger.json` turns ALL THREE skills-check reds green
  with no other change — i.e. `placeholder_check` and `carryforward` return
  `ok`, and the two live-corpus unit tests that read them pass. The third
  failing unit-test node
  (`test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`) is
  downstream of the other two and needs nothing of its own.

## B. The scope-reachability instrument (`harness/swe/scopecall.py`)

The question round 502 answered by hand for one function — `git log -S` and a
sentence — asked as a runnable verdict for every def in a campaign's declared
scope. Verdicts: `live` (referenced from a non-test file), `test_only`
(referenced only from test files), `unreferenced` (referenced nowhere but its
own definition).

* **B1.** `R491_RANGES` (`556-634,1573-1662,2232-2301`, the scope
  `nodecampaign.py` calls *"the three regions ... that carry published
  numbers"*) covers between **6 and 12** named defs.
* **B2.** Exactly **one** of them is `test_only`, and it is `classify_bucket`.
  Round 502 proved that one by hand; I predict the instrument finds no second
  one *inside this scope*.
* **B3.** **None** of the scoped defs is `unreferenced`. Every one has at
  least a test.
* **B4.** Run over the WHOLE of `nuc/perturbation.py` (not just the scope),
  the instrument finds **at least 3 more** `test_only` defs beyond
  `classify_bucket` — i.e. `classify_bucket` is an instance, not the
  exception. I put the total `test_only` count at **8-30** of the file's defs.
* **B5.** Run over `harness/swe/*.py` — this program's OWN self-improvement
  harness — the instrument finds **at least one** `test_only` public def.
  This is the prediction I most expect to be uncomfortable.

## C. The stratified kill rate

`state/swe/perturbation-mutation-ledger.jsonl` reports one pooled kill rate
over the three scope regions. Stratifying it by B's verdicts:

* **C1.** The pooled kill rate at HEAD-with-the-dirty-tree is between
  **70 % and 88 %** (it was 63.2 % at 87 sites before round 502's re-score
  added killers; the ledger now has 134 rows).
* **C2.** The `test_only` stratum's kill rate is **HIGHER** than the `live`
  stratum's. Reason: `classify_bucket`'s mutants are graded by unit tests
  written directly against it and nothing else, which is the easiest possible
  grading problem — the pooled number is therefore flattered by the third of
  the scope that measures the test file.
* **C3.** The gap between the two strata is at least **10 percentage points**.
* **C4.** Removing the `test_only` stratum LOWERS the reported kill rate by at
  least **3 percentage points** versus the pooled figure.

## D. Costs and shapes

* **D3.** `harness/tests/test_swe_scopecall.py` will hold **25-45** tests.
* **D4.** `scopecall` over the whole repo's non-test `.py` files completes in
  under **90 s** on this 1-core box (pure `ast`, no subprocess, no pytest).
* **D5.** At least one def that a name-based reference scan calls `live` is
  live only through a STRING (a `getattr`, a dispatch dict key, a CLI
  subcommand name) rather than a syntactic call. I predict the instrument's
  conservative string-inclusion rule fires on **at least 2** defs in
  `nuc/perturbation.py`, and that turning it off would flip them to
  `test_only` — i.e. the conservative rule is load-bearing, not decoration.
* **D6.** No new red in `harness/tests/` or `nuc/tests/` from this round's
  changes.
