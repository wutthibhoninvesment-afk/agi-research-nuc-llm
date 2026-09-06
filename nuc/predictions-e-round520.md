# Round 520 (NUC-integration E) — predictions, banked BEFORE measuring (D-013)

Banked 2026-09-06T02:12:00Z, before the rescore slice ran and before any test
in this round was executed. Box DOWN (two tailnet ssh probes, 02:00:36Z and
02:01:14Z, both rc 255 `Connection timed out`), so every prediction below is
about offline artefacts in this repo.

## The population, RE-DERIVED from its origin — not copied from a report

Round 514's headline was that a prediction's DENOMINATOR is a carried claim.
So this round's denominator is re-derived from the ledger itself, not from
`state/nuc/round-514/survivor-impact.json` and not from round 514's prose:

```sh
python3 -c "
import json
rows=[json.loads(l) for l in open('state/swe/perturbation-mutation-ledger.jsonl')]
OLD='8082749f713ee07f05e1f9187324280156c547673e35fa39017ef67200173ea1'
lw={}
for r in rows: lw[(r['id'], r['subject_digest'])]=r
import collections
print(collections.Counter(lw[k]['status'] for k in lw if k[1]==OLD))"
# -> Counter({'killed': 82, 'survived': 5})     87 distinct ids
```

**82** is the population: the mutants scored at round 502's subject digest
`8082749f…` whose last-wins verdict is `killed`, and which round 514
remapped onto HEAD (`3b3923df…`) but did **not** re-score. Round 514 §8 calls
its own survivor set "a lower bound" for exactly this reason.

Timing basis, also re-derived: those 82 cost **310 s in total** at the old
digest (median 3.96 s, mean 3.78 s, max 7.3 s), all 82 under the `subset`
oracle, median 39 units selected. The 5 survivors cost 131 s for five,
because a survivor has to exhaust its unit set.

## Predictions

| # | claim | how it will be scored |
|---|---|---|
| P1 | The slice runs all 82 in one go: `n_run_this_slice == 82` and `n_left_unrun_by_budget == 0` under a 1500 s budget | the slice report JSON |
| P2 | **>= 78** of the 82 come back `killed` at HEAD | `by_status` |
| P3 | **Exactly 0** of the 82 flip `killed -> survived`; `verdict_changes` is `[]` | `verdict_changes` |
| P4 | Wall clock for the slice lands in **350-800 s** (310 s of old-digest mutant time + staging + a fresh subset baseline) | `seconds` |
| P5 | `oracle == {"subset": 82, "full": 0}` — the map at HEAD is fresh and covers every remapped line | `oracle` |
| P6 | After the rescore, `nuc/survivor_impact.py --strict` still exits 0 with `n_survivors_standing == 5` and `moves_published_number == []` — i.e. round 514's report turns out to have been exact, not merely a lower bound | the regenerated report |
| P7 | `n_ledger_rows_scored_under_another_suite` stays **exactly 55** after the rescore, because the 55 stale rows are keyed at the OLD subject digest and a rescore at the NEW one appends a different key rather than replacing them | the slice report |
| P8 | **0** test nodeids present in suite digest `2cd94b15…` are absent from the live suite `7ac31f49…` — i.e. `nuc/tests/test_perturbation.py` grew monotonically, so the "a stronger suite only overturns SURVIVED" premise behind survivor-only `--stale` happens to hold on this history even though nothing enforces it | `git show` of the two blobs, nodeid diff |
| P9 | `reachability_check.py coverage --strict` reports `missing: [514]` before this round and **still** reports `missing: [514]` after row 520 is appended — round 514's hole needs its own `backfill`, which appending 520 does not touch | two `coverage` runs |
| P10 | A guard test asserting that the stale-verdict selector covers non-`survived` rows **fails against HEAD** before this round's fix and passes after | pytest, run in both orders |
| P11 | `median_units_selected` for this slice differs from the old digest's 39 — the subject moved 243 lines, so the by-test map selects a different unit count | slice report |

## The thing being tested, stated so a miss is visible

`harness/swe/nodecampaign.py` computes

```python
stale = [r for r in done.values()
         if r.get("suite_digest") not in (suite, None) or "suite_digest" not in r]
stale_survivors = sorted(r["id"] for r in stale if r.get("status") == "survived")
```

and publishes `n_ledger_rows_scored_under_another_suite = len(stale)` — but the
only verb that can pay that number down, `--stale`, selects
`stale_survivors`. On this subject today that is **55 vs 0**: fifty-five
verdicts produced by a suite that no longer exists, and a repair verb that
covers none of them. P2/P3 measure what those stale kills are actually worth.

## Known risk to P5

If the by-test coverage map at `state/swe/perturbation-cov-by-test.json` does
not carry a unit for some remapped line, `MapPrioritizer` returns basis
`"line-miss"` (or the subset baseline is dirty) and that mutant runs the FULL
suite at ~48 s. Ten such mutants would put P4 out of range on their own. P5
and P4 therefore fail together or not at all, and I am predicting neither.
