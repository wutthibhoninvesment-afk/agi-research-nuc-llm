# Round 491 (SWE-loop D) — predictions, banked BEFORE measuring

Subject: `nuc/perturbation.py` (5339 lines, 251 KB) and its suite
`nuc/tests/test_perturbation.py` (2889 lines, 233 tests, 96.0 s green).
Item: round 490 next-steps #4 — "`test_perturbation.py` has STILL never been
mutation-tested", four rounds old (472 #4, 478, 484 #6, 490 #4), assigned
"NUC(E) or SWE-loop(D)".

Measured before banking (not predictions): 1794 mutation sites from
`harness.swe.mutation.generate` (const 703, cmp 329, arith 301, ifneg 239,
bool 95, not 68, fconst 59); suite 233 passed in 95.98 s; `nproc` 1.

**P1.** `prioritize.MapPrioritizer.covering()` — round 113's cost-reduction
mechanism, the only one this program has — returns a covering set of exactly
ONE test file for every covered mutant on this subject, because the whole
suite is one file. Subset ratio 1.00, i.e. the mechanism buys ZERO here.
That, not neglect, is why the item is four rounds old.

**P2.** Per-test (nodeid) granularity drops the MEDIAN covering set below 20
of the 233 tests.

**P3.** Measured per-mutant wall clock under nodeid subsetting comes in under
15 s against the 96.0 s full-suite baseline — a speedup of 6x or better.

**P4.** At least one selected nodeid subset FAILS on UNMUTATED code (a test
that only passes when its file-mates ran first). I.e. nodeid subsetting is
NOT sound without a per-subset baseline; file-level subsetting never needed
one because running a whole file preserves intra-file order and fixtures.

**P5.** The scoped campaign's kill rate on `perturbation.py` lands BELOW 85%,
against the 100% (32/32, 29/29, ...) the NUC track reports for its
hand-written `MUTATIONS` lists. Those lists name a mutation AND the test that
kills it by construction; an AST campaign does not get to choose.

**P6.** Survivors cluster on the `const` operator (703 of 1794 sites = 39.2%
of the population) — it will be over-represented among survivors relative to
39.2%.

**P7.** The full campaign is infeasible in one round and the number says so:
1794 mutants x 96.0 s / 1 core = 47.8 h against this session's 3300 s cap.
Even at P3's 6x it is 7.9 h. No single round closes this item; the honest
deliverable is the mechanism plus a ledgered slice.
