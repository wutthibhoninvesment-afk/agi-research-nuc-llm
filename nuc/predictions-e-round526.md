# Round 526 (NUC-integration E) — predictions, banked BEFORE measuring

Rule D-013. Written after READING `nuc/perturbation.py:1576-1663` and round
520's `state/nuc/round-520/survivor-impact.json`, and before running a single
line of the arithmetic below. Every number here is a claim I can be wrong
about.

## Subject

The five mutants that SURVIVE at `subject_digest 3b3923df…` (= HEAD's
`nuc/perturbation.py`, re-derived this round with `sha256sum`), all of them in
the statistics kernel that computes this track's published p-values:

| id | line | mutation | round 520's verdict |
|---|---|---|---|
| `perturbation.py:1586:cmp#162`   | 1586 | `h <= 0` → `h < 0`            | `reached_but_identical` |
| `perturbation.py:1642:const#983` | 1642 | `range(1, N+1)` → `range(2, N+1)` | `reached_but_identical` |
| `perturbation.py:1642:arith#984` | 1642 | `range(1, N+1)` → `range(1, N-1)` | `reached_but_identical` |
| `perturbation.py:1660:const#1547`| 1660 | `testable[0]` → `testable[1]`  | `unreached_by_battery` / `branch_not_taken` |
| `perturbation.py:1661:const#1601`| 1661 | `testable[-1]` → `testable[-2]` | `unreached_by_battery` / `branch_not_taken` |

**The thesis.** Those five carry ONE verdict vocabulary between them and they
are not one thing. I predict they are three: one provably equivalent mutant,
two real suite gaps that a test can kill today, and two mutants on a branch NO
input can reach. The report has no word for the third class, so it spends the
battery's word (`unreached_by_battery`) on it, which reads as a coverage gap
you could close by testing harder.

## Predictions

**P1 — `cmp#162` is a genuinely EQUIVALENT mutant.** Line 1584 already raises
on `h < 0`, so `if h <= 0: return 1.0` differs from `if h < 0: return 1.0`
only at `h == 0`, where the fall-through sums Vandermonde's identity over the
full range and must return exactly `1.0`. Exhaustive check over every valid
`(N, K, n)` with `N <= 40`: **0 differing pairs**, and every fall-through value
`== 1.0` exactly (not just within 1e-12).

**P2 — `best_case_p(N, K, d)` is U-shaped in `d`, with its minimum at `d = K`.**
For `d < K` it is `C(K,d)/C(N,d)`, strictly decreasing; for `d >= K` it is
`C(d,K)/C(N,K)`, strictly increasing. Exhaustive over `1 <= N <= 60`,
`0 <= K <= N`: **0 unimodality violations**.

**P3 — therefore the `testable` set is ALWAYS contiguous, and the third `why`
branch (lines 1659-1661) is DEAD.** A sublevel set of a unimodal function is
an interval. Exhaustive over `1 <= N <= 80`, `0 <= K <= N`,
`n_units_tested in 1..20` (≈ 65 000 calls): **0 non-contiguous testable sets**,
i.e. `testable[-1] - testable[0] + 1 == len(testable)` in 100 % of non-empty
cases. `const#1547` and `const#1601` are therefore NOT killable by any test,
and round 520's `branch_not_taken` is true but understates it: the branch is
not merely untaken, it is untakeable.

**P4 — `const#983` (`range(1, N+1)` → `range(2, N+1)`) IS a real gap, killable
today.** `min_testable_occupancy == 1` is attainable: I predict
`best_case_p(N, K, 1) = K/N`, so any record with `K/N <= 0.05/n_units_tested`
puts occupancy 1 in the testable set. Concrete witness I expect to work:
`power_floor(N=1000, K=1, n_units_tested=1)` → `min_testable_occupancy == 1`.

**P5 — `arith#984` (`range(1, N+1)` → `range(1, N-1)`) IS a real gap too, but
the obvious witness does NOT work.** `d = N` is never testable
(`best_case_p(N, K, N) == 1.0` exactly, for every `K >= 0`), so no case can
push `max_testable_occupancy` to `N`. `d = N - 1` IS attainable:
`best_case_p(N, K, N-1) = (N-K)/N` for `K <= N-1`, so a high-`K` record clears
the bar. Witness I expect: `power_floor(N=100, K=99, n_units_tested=1)` →
`max_testable_occupancy == 99`. Killing this mutant requires `max >= N-1`;
`max == N-2` would NOT kill it.

**P6 — `test_perturbation.py` is green at HEAD and larger than 200 tests.**
I predict `>= 200 passed, 0 failed`, and a wall time under 200 s.

**P7 — after this round's new tests, the survivor set goes 5 → 3.**
`const#983` and `arith#984` killed; `cmp#162`, `const#1547`, `const#1601`
still survive, because P1 and P3 say nothing can kill them. I predict the
re-scored slice reports exactly `killed 2 / survived 3` over the 5 ids.

**P8 — the ledger's suite digest moves, and nothing is removed.** Adding tests
changes `test_perturbation.py`'s digest, so the 87 rows at `3b3923df` become
"scored under another suite" in round 520's sense. I predict the nodeid count
GROWS (round 520 measured 239 → 245 → 257 with 0 removed) and that **0**
existing nodeids disappear.

**P9 — the carried debt "`test_perturbation.py` has STILL never been
mutation-tested" (state/nuc-missions.md, round-490 next-steps item 5, four
rounds old when written) is STALE.** The ledger's own rows say
`"path": "nuc/perturbation.py"` for all 221 of them. I predict re-derivation
shows the module has been mutation-tested since round 497 and the debt line
should be struck, not paid.

**P10 — `survivor_impact.py` has no verdict for "unreachable by construction".**
I predict `grep` over the module finds `unreached_by_battery`,
`reached_but_identical` and `branch_not_taken`, and NO term distinguishing a
branch this battery missed from a branch no input can take.

**P11 — the box stays down.** Seventh consecutive down E-window; `LastSeen`
`2026-09-04T02:14:05.1Z` unchanged from rounds 490/496/502/508/520. Already
observed this round before this file was written; recorded here so the scoring
is complete, not as a prediction I can claim credit for.

## Scoring

Scored honestly in `knowledge/round-526-*.md` §7. A prediction that names a
number is a MISS if the number is wrong, even when the direction is right.
