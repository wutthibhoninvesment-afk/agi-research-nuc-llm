---
name: repeats-are-not-replicates
description: Use when a verdict about a stochastic system rests on N samples that were all taken inside ONE batch, session, run, deploy or process — a benchmark loop, an eval harness, a flaky-test hunt, an A/B probe, a latency sweep, an LLM judge. Symptoms: a result that will not reproduce next week though nothing changed; two runs of a byte-identical configuration disagreeing on half their cases; a registry of durable verdicts each read off a single report; a "re-run to confirm" that was launched only because the first run failed; a knob labelled repeats/iterations/trials that is applied inside the run rather than across runs; a point estimate with no interval anywhere in the pipeline. Covers estimating the intraclass correlation so the cluster effect is a number, converting it to effective sample size, spending a fixed probe budget across runs instead of inside one, pooling to an interval instead of collapsing to a boolean, and telling a real defect from a draw before editing anything.
---

# Repeats inside one run are not replication

Ten samples from one run are not ten samples. If anything about the run —
the moment in time, the serving fleet, the warm cache, the queue depth,
the staged fixture directory — shifts the thing you are measuring, then
the run is the unit of independence and your ten samples are worth far
fewer. The failure is silent: you get a tight-looking interval around the
wrong centre, and the next run disagrees.

The number that decides this is the **intraclass correlation**, ρ. It is
the share of variance that lives *between* runs rather than *within*
them. Effective sample size for `n` samples taken inside one run:

```
n_eff = n / (1 + (n - 1) * rho)
```

At ρ = 0 repeats are free replication. At ρ = 1/3 — measured, see
Verification — six samples in one run are worth **2.25** independent
draws, and no repeat count ever beats the ceiling `1/rho`. The same six
samples spent as 3 runs × 2 are worth **4.50**. Same cost, twice the
information, and the only change is where the loop lives.

## When to use

Trigger on any of these:

1. A verdict, registry entry, or decision is about to be written from
   samples that all came from one run/batch/session/process.
2. Two runs of the same configuration disagreed and someone called it
   flakiness rather than measuring it.
3. A tool exposes `--repeats` / `--iterations` / `--trials` and it loops
   *inside* the run.
4. A result is a point estimate — "3 of 3", "fired every time", "p50 was
   40 ms" — with no interval attached.
5. You are about to re-run something *because it failed*. That is
   selection on the outcome and it is a different bias; see step 5.

Do NOT reach for this when the samples are genuinely independent by
construction (separate machines, separate days, randomised assignment),
or when you want within-run variance on purpose (jitter inside a request
burst is the measurement, not a nuisance).

## Steps

1. **Name the cluster.** Write down the thing that is shared by every
   sample in a batch and could move the measurement: process, wall-clock
   window, warm cache, staged directory, host population, model routing.
   If you cannot name it, you cannot claim it is absent.

2. **Design the crossing, not the total.** You need at least 2 runs *and*
   at least 2 samples per run. `R` runs × 1 sample cannot separate the
   levels — run and sample are confounded — and 1 run × `N` samples
   measures only within-run variance. Prefer `3 × 2` over `1 × 6` and over
   `6 × 1`.

3. **Hold everything else identical and run them sequentially.** Same
   inputs, same concurrency, same configuration. Any deliberate variation
   between runs turns the run effect into a treatment effect you cannot
   separate from it.

4. **Estimate ρ, do not assume it.** One-way ANOVA over cells indexed by
   (case, run):

   ```
   MSB = sum over runs of n_r * (p_r - p)^2 / (R - 1)      # between
   MSW = sum over runs of within-run deviation / (N - R)   # within
   rho = (MSB - MSW) / (MSB + (n0 - 1) * MSW)
   ```

   Report `MSB/MSW` alongside ρ: a ratio near 1 means the runs really are
   exchangeable and you can stop worrying.

5. **Do not estimate ρ from an archive of past runs.** Historical re-runs
   are usually conditioned on their own outcome — a `-reprobe`, a
   `-retry`, an isolation arm that exists *because* the first run failed.
   Regression to the mean then reads as a cluster effect. Estimate ρ from
   runs you designed before seeing their results.

6. **Report an interval, never a boolean.** Collapsing a run to
   pass/fail throws away the count and makes the estimator disagree with
   itself: if a run is "good" only when all `n` samples pass, that event
   has probability `p^n`, so the same true rate yields different verdicts
   at different `n`. Pool the raw counts and attach a Wilson interval.
   Classify three ways — **WORKS** (interval above the threshold),
   **REFUTED** (entirely below), **UNDECIDED** (straddling) — and expect
   UNDECIDED to be the common answer at small `n`.

7. **Only then edit anything.** A defect is a case whose interval sits
   below the threshold across ≥2 runs. Make ONE change, re-measure the
   same way, and if it does not improve, stop and record the verdict
   rather than editing again. An edit changes the thing being measured,
   so two draws either side of an edit are two draws of two instruments.

## Exact commands

Estimate the cluster effect and the sample-size consequence:

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "skills/skill-authoring/scripts")
import trigger_eval as te
cases   = te.load_cases("skills/trigger-cases.json")
catalog = te.load_catalog(["skills"])
runs    = [r for r in te.load_reports("state/trigger-eval")
           if "round-393-run" in r[0]]          # ONLY the designed runs
rv = te.run_variance(catalog, cases, runs)
print(rv)                                        # msb, msw, ratio, icc, cases, runs
print("6 in one run :", te.effective_draws(6, rv["icc"]))
print("3 runs x 2   :", 3 * te.effective_draws(2, rv["icc"]))
PY
```

Spend a probe budget across runs rather than inside one — three
invocations, not one with `--repeats 6`:

```bash
for T in A B C; do
  python3 skills/skill-authoring/scripts/trigger_eval.py \
    skills/trigger-cases.json --skills skills \
    --mode native --model sonnet --protocol strict \
    --repeats 2 --concurrency 3 --only "$CASES" \
    --json state/trigger-eval/round-NNN-run$T.json
done
```

Read the pooled verdict instead of the newest report:

```bash
python3 skills/skill-authoring/scripts/case_coverage.py | tail -1
# ... POOLED 95%: 17 WORKS (5 of them on a single run), 28 UNDECIDED, 1 REFUTED
```

## Pitfalls

- **`--repeats N` looks like replication and is not.** It is the single
  most expensive mistake here, because it costs full price for a fraction
  of the information. Check where the loop lives before trusting the knob.
- **Estimating ρ from an archive inflates it.** This corpus's archive
  gives 0.67–0.74; restricted to designed replicates it gives 0.43–0.86;
  measured prospectively it is 0.333. Selection on the outcome roughly
  doubled it.
- **A boolean collapse manufactures disagreement.** Before this skill,
  the corpus reported "27 of 45 cross-report verdicts DISAGREE" — of
  which **16.4 are expected** under a perfectly stable selector, purely
  because `all(fires)` has probability `p^n` and the reports had different
  `n`. Most of that alarming number was the estimator arguing with itself.
- **ρ is not portable.** It is a property of *this* system on *this* box
  at *this* cluster definition. Re-derive it; do not quote someone else's.
- **A case that pools to exactly 0 or 1 carries no dispersion** and drops
  out of the ANOVA. If most of your cases are saturated you cannot
  estimate ρ at all, and should say so rather than reporting a number
  computed from two cases.
- **Editing changes the digest, and the old samples stop applying.**
  Keep the pre-edit and post-edit measurements separate and labelled; do
  not pool across an edit.
- **UNDECIDED is a real answer, not a checker being unhelpful.** Do not
  suppress it into a warning per subject — 28 of 46 here were undecided,
  and 28 warnings is a check that gets uninstalled. Put the count in the
  summary line and warn only on refutations.

## Verification

Measured on this repo, round 393, `skills(B)`. 23 trigger cases × 3
separate `trigger_eval.py` invocations × `--repeats 2` = 138 probes, 0
errors, $7.60, sonnet, `--protocol strict`, identical configuration, run
sequentially (`state/trigger-eval/round-393-run{A,B,C}.json`):

| quantity | value |
|---|---|
| MSB (between-run) | 0.381 |
| MSW (within-run) | 0.190 |
| MSB/MSW | **2.00** |
| ANOVA ICC | **0.333** (7 informative cases) |
| n_eff, 6 probes in one run | **2.25** |
| n_eff, 6 probes as 3 runs × 2 | **4.50** |
| cases where the 3 runs disagreed at majority | 6 of 23 |
| cases fully split (2/2 in one run, 0/2 in another) | 3 |

Re-derive both, offline and free:

```bash
python3 -m pytest skills/skill-authoring/scripts/test_pooled_estimator.py -q
# 33 passed
python3 skills/skill-authoring/scripts/case_coverage.py | tail -1
```

`test_pooled_estimator.py::TestLiveCorpus::test_the_round_393_experiment_reproduces_its_icc`
re-computes the ICC from the reports on disk and fails if it moves, so
the table above cannot rot silently. The figure is evaluated against the
descriptions currently on disk — a stale digest removes a case from the
pool, and while an edited description was briefly staged the same three
reports gave 6 cases and ρ = 0.200.
