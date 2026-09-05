# Round 502 (NUC-integration E) — predictions, banked BEFORE measuring

House rule D-013. Written and committed before any of the work below was
run. Scored honestly in the round file, misses first.

## Context already OBSERVED before this file was written (not predictions)

* Two tailnet SSH probes at 2026-09-05T04:20:5xZ and 04:21:0xZ, both
  `rc 255 Connection timed out`. CLAUDE.md's two-failure rule fired; no box
  work attempted, port 8001 never contacted.
* `tailscale status --json`: `Online false`, `LastSeen 2026-09-04T02:14:05.1Z`,
  relay `sin`, tx 1404 rx 0.
* `reachability_check.py coverage --strict` exits **1**, `missing: [496]` —
  round 496 (NUC E) never appended its own row.
* `nuc/perturbation.py` digest is `8082749f713ee07f...`, byte-identical to the
  `subject_digest` on all 87 ledger rows. `nuc/tests/test_perturbation.py`
  digest is `2cd94b15`, equal to the `suite_digest` on round 497's 32 rows and
  absent from round 491's 55.
* Ledger: 87 rows, 55 killed / 32 survived. 15 of the survivors are round
  491's (no `suite_digest`), 17 are round 497's.

## Predictions

**P1 — the stale survivors.** Re-scoring round 491's 15 survivors against the
CURRENT suite flips exactly **8** to `killed` and leaves **7** `survived`.
Basis: round 491's own prose says it added six tests and killed 8 of the 9
mutants it aimed at, the ninth (`1582:cmp#161`) being provably equivalent, and
its next-step #3 names 7 as open. Scored on the flip count.

**P2 — the number the ledger publishes is wrong today.** After the re-score the
survivor count over the 89-site scope falls **32 -> 24** and the campaign-wide
kill rate rises from **63.2 % (55/87) to 72.4 % (63/87)**. Any published
survivor count taken from this ledger between rounds 491 and 502 was too high.

**P3 — twelve survivors are unreachable ON THIS RECORD, not merely untested.**
Lines 1654-1657 sit inside the ELSE branch of `power_floor`'s `why` string,
taken only when `testable` is non-empty. Round 412 established this box's
record has no power at all (K=1, 16 units, N=218 => `testable == []`), so the
first branch is the only one the record ever takes. All **12** survivors on
1654/1655/1656/1657 will classify `unreached_by_record`: the mutated line never
executes in any published derivation.

**P4 — the classify_bucket defaults are reached and inert.** `558 fconst`
(10.0 -> 11.0), `559 const` (50_000 -> 50_001) and `560 fconst` (50.0 -> 51.0)
ARE executed on the real record but change **no** published channel count: the
box idles at `pgpgin/s` 0.00-0.20 and apt's surge is ~333 MB, both orders of
magnitude from the thresholds. All three classify `reached_but_identical`.

**P5 — at least one survivor moves a published number, and I name it.**
`2246:cmp#662` (`u["n_fires"] >= min_fires` -> `>`) regrades `verdict_floor`'s
`min_fires` gate. I predict it changes `pass_counts["min_fires"]` on the real
record. If NO survivor moves any published number, P5 is a MISS and the whole
32 are a test-shape problem rather than an evidence problem.

**P6 — the two frozen dataclasses are inert.** `633:const#334` and
`1661:const#382` are both `@dataclass(frozen=True)` -> `frozen=False`. Nothing
in the module rebinds a `ReclaimEvent` or an `AttributionEvidence` field, so
every derivation's output is byte-identical. Both classify
`reached_but_identical`; both are killable only by a test that asserts
immutability, which no published number depends on.

**P7 — the impact battery is cheaper than the pytest oracle.** 32 mutants
through the whole battery, in process, completes in **under 180 s** — at least
2x cheaper per mutant than the ~9-13 s/mutant pytest oracle, because it never
starts an interpreter.

**P8 — re-score cost.** The 15-mutant re-score costs **150-260 s** wall
(round 497 measured ~9.2 s/mutant linked, plus master staging and subset
probes).

**P9 — suite.** `nuc/tests/` finishes green at the end of this round, at
**200-320 s** run solo on this 1-core box (round 496: 1147 passed in 228.60 s).

**P10 — gates.** After backfilling round 496's row and appending round 502's:
`coverage --strict` **0**, `precision-audit --strict` **0**,
`lastseen-drift --strict` **1** (the documented round-436/472 disagreement).

**P11 — the outage does not move under me.** `LastSeen` still reads
`2026-09-04T02:14:05.1Z` at the end of the round: same outage as rounds 490 and
496, ~26 h at first probe, no tailscale recomputation within the round.
