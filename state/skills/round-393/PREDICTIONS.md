# Round 393 (skills B) — predictions, banked before the live experiment

Banked in ONE block before any probe of the round-393 experiment was
launched. Rule D-013. §0 lists what was ALREADY measured offline before
this file was written, so none of it is scored as a prediction.

## §0 OBSERVATIONS ALREADY MADE (not predictions, not scored)

These came from re-analysing the 27 archived reports in
`state/trigger-eval/` and from the pre-flight, all BEFORE this file:

1. `case_coverage` reports `27 of 45 cross-report case verdicts DISAGREE`.
2. `replication_rows` collapses a report to `all(fires)` — a boolean whose
   probability is p^n, so the SAME true rate yields a different verdict at
   n=1 and n=3. Under a null of one stable rate per case, the expected
   number of `all()`-disagreements among those 45 is **16.4**, not 0.
3. Between-report deviance dispersion over same-digest pairs: G/df = 2.79.
4. ANOVA ICC at the RUN level: 0.737 over all same-digest pairs; 0.665 on
   the subset usable for the ANOVA estimator (22 cases).
5. Several archived pairs are SELECTION-CONDITIONED (a `*-miss-reprobe` /
   `*-isolation` / `*-reprobe` run exists because the earlier run missed),
   which inflates 4. Restricted to designed replicates: rbr-run1 vs
   rbr-run2 ICC 0.857 (3 cases); batch vs armH 0.481 (12); the four
   round-381 full-corpus runs 0.428 (12).
6. `fired == []` and `turns == 1` are the same event in 495 of 496
   archived probes — round 381's "turns==1 correlate" is an identity, not
   an independent signal.
7. Positive-case misses across the archive split 32 abstention (nothing
   fired) / 31 displacement (a different skill fired). Abstention rate by
   run ranges 0% to 67%.
8. Dropping abstentions lowers the clean-set ICC 0.428 -> 0.310: it helps
   and does not solve.
9. Canary at session start: sonnet/default 3/4 and sonnet/strict 4/4, both
   IN BAND; haiku/strict 1/5 with 1 error = DRIFT on a deliberately wide
   band. The experiment below is sonnet-only.
10. `nproc` = 1 on this box. Round 381's anomalous run was 87 probes at
    `--concurrency 3` on this same single core.
11. The owed probe debt is 5 skills / 18 positive cases: `exemption-census`
    (r383), `derived-subject-set` (r392), `errors-that-name-the-fix`
    (STALE), `expiring-fixture-window` (never), `replay-scope-is-read-scope`
    (never).

## The experiment being banked against

23 cases (18 positives for the five owed skills + 5 negatives), probed as
**3 separate `trigger_eval.py` invocations, each `--repeats 2`**, same
model (sonnet), same protocol (strict), same corpus, same concurrency, run
sequentially. 138 probes. Crossing run x repeat is what separates
between-run from within-run variance; 3 runs x 1 repeat cannot, because
run and probe are then confounded.

## Predictions

**P1.** The fresh, non-selection-conditioned between-run ICC will be
> 0.25 — i.e. the run-level effect replicates on data that was not
selected on its own outcome.

**P2.** The 3 runs will disagree at majority level (per-run `all(fires)`
verdict differing) on >= 3 of the 23 cases.

**P3.** The per-run abstention rate (positive-case probes firing nothing)
will differ by >= 15 percentage points between the highest and lowest of
the 3 runs.

**P4.** Between-run variance will exceed within-run variance: the ANOVA
mean-square ratio MSB/MSW will be > 1.

**P5.** Effective independent draws for a 6-probe single-run design,
computed from THIS round's ICC, will come out < 3.0 (against the nominal
6).

**P6.** `derived-subject-set` (round 392's skill, never probed) will fire
on >= 2 of its 3 positive cases at pooled majority.

**P7.** `dss-neg-unrun` will NOT fire `derived-subject-set` on any of its
6 probes; round 392 wrote it expecting `unrun-checker-latency`.

**P8.** `exc-neg-single` will select `measured-exemption` on a majority of
its probes — round 383's boundary claim, never tested.

**P9.** At least one of the 5 owed skills will show a within-case
between-run split (3/3-style verdict in one run, 0/3-style in another) —
the round-381 shape, reproduced prospectively rather than found in an
archive.

**P10.** Total spend 138 probes, $8-$13; mean cost/probe $0.055-$0.095.

**P11.** At least one of the 5 owed skills will score BELOW 50% pooled
recall — i.e. the batch finds at least one genuinely weak description and
not just noise.

**P12.** After this round's changes, `skills/run_checks_fast.sh` will
report 0 errors, and the case_coverage warning count will DROP from 16.

**P13.** The three P004 warnings (`errors-that-name-the-fix` STALE,
`expiring-fixture-window` never, `replay-scope-is-read-scope` never) will
all clear, and `state/known-unprobed-skills.json` will be EMPTY again.

**P14.** Whole-round diff 900-2000 lines.

**P15.** Re-running the drifted haiku/strict canary sentinel once more
will put it back IN BAND (>= 0.33) — i.e. it was a draw, this round's own
thesis applied to its own pre-flight.
