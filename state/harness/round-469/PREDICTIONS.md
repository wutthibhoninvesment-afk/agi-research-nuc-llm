# Round 469 (harness A) — predictions, banked BEFORE measuring (D-013)

**Question.** Round 468's next-step 3:

> The `--tests` tiering question is now a DIFFERENT question and should be
> answered rather than offered a seventh time. Rounds 456, 458, 462, 463 and
> 468 all raised it. `--harvest-only` (2.6 s) and `--residual` (2.7 s) are
> already covered by `tests/test_testcorpus_census.py` (5.8 s, fast tier)
> through its module-scoped fixtures — that half is DONE and nobody noticed.
> The only open item is whether a full suite-mode census (**80.3 s**, was
> 28.1 s at 559 programs and will keep growing with the corpus) is worth a
> slow-tier slot. harness(A).

This round owns it. The question presupposes that `whence_slow` HAS slots —
that putting a test there means something runs it and something records the
result. That presupposition is what I am measuring first, because the
program's own carried list has said the opposite for a long time ("the
unsampled `whence_slow` tier", carried as harness(A) at
`state/research-state.md:17420`, `:17640`, `:17983`, and named outright at
`:15424`: *"The `whence_slow` tier is where regressions hide, and nothing
samples it"*).

## Baselines — read at HEAD BEFORE writing this file, NOT predictions

Each carries the command that produced it, per `skills/prediction-banking`
step 1. Nothing below may be scored against these; they are the floor the
bands are measured from.

| # | quantity | value | command |
|---|---|---|---|
| B1 | `@pytest.mark.whence_slow` decorator lines in `languages/whence/tests/` | **104** across **28** files | `grep -rn "@pytest.mark.whence_slow" languages/whence/tests/*.py \| wc -l` |
| B2 | last fast-tier run reported by round 468 | 2446 passed, 3 skipped, **103 deselected**, 241.45 s | round 468's research-state entry (PROSE — re-derive) |
| B3 | recorded `whence-slow` runs, all of them | **2**, in `state/pristine-check-ledger.jsonl` | `grep whence-slow state/pristine-check-ledger.jsonl` |
| B4 | B3 reading #1 (2026-08-30T04:23Z) | 53 passed + 1 failed = **54 selected**, 1193 deselected, pair 586.3 s (live+pristine) | ledger row `suite: whence-slow` |
| B5 | B3 reading #2 (2026-08-30T17:53Z, `91acd9c5af97`) | **70 passed**, 1598 deselected, pair 1014.6 s, pytest's own line `70 passed, 1598 deselected in 509.47s` | ledger row `suite: whence-slow` |
| B6 | slow-tier ledger (`swe_slow`) size | 141 entries | `wc -l state/slow-tier-ledger.jsonl` |
| B7 | `state/whence-slow-ledger.jsonl` | does not exist | `ls state/` |
| B8 | driver's per-round checks | 5: harness-fast, whence-fast, skills, nuc, `run_slowtier_slice.sh` | `run_driver.sh:523-661` |

**B4/B5 are a RECORDED DISTRIBUTION of the whole tier's wall clock** — two
readings, 293 s/54 tests and 509 s/70 tests as single runs, i.e. 5.4 s and
7.3 s per selected test. Per `skills/prediction-banking` step 4 that is what
licenses P3 below; the prose figures floating in this repo (905 s at
`state/research-state.md:16346`, ~590 s at `:16964`) are NOT a distribution
and are not used.

## Predictions

Each line is tagged **STRUCTURAL** (a claim about the code as written,
checkable by reading it) or **RATE** (a claim about a count or a measurement
of live behaviour). Round 468's rule, which this bank is the first to apply:
*if your structural prediction has a count in it, bank it as a RATE.* Two
lines below name a structure and then a count; both are tagged RATE, not
structural, and that is the point.

### P1 — STRUCTURAL. There is no whence-slow evidence mechanism at all.
No module in `harness/` selects units by the `whence_slow` marker; no file
under `state/` records a per-unit outcome for any `whence_slow` test; and
`run_driver.sh` invokes `pristine_check.py` on no code path, so the tier's
only named runner (`SUITES["whence-slow"]`) is manual-only. *Basis:*
`slowtier.slow_tier_files` filters on the literal prefix `test_swe_`
(`harness/swe/slowtier.py:161-165`) and B7/B8. **Confidence: very high.**
*Falsified by:* any `state/*.jsonl` row naming a `whence_slow` test node, or
a `pristine_check` call site in the driver.

### P2 — STRUCTURAL. A naive port of `slowtier.py` would be wrong, and wrong in a specific way.
`slowtier.py` gets two INDEPENDENT staleness rules — `checkout_digest` over
`languages/whence/` and `dep_digests` over the test's `swe.*` closure —
only because its test tree and its subject tree are disjoint. For
`whence_slow` they are the SAME tree (`languages/whence/tests/` is inside
`languages/whence/`), so a straight port collapses both rules onto one
digest and every commit that touches any `.py`/`.lang` file under that tree
— including a test file belonging to some OTHER unit — invalidates every
unit at once. **Confidence: very high.** *Falsified by:* showing
`checkout_digest`'s walk excludes `tests/` (it does not; the walk is
`os.walk(root)` with only `__pycache__`-class dirs pruned).

### P3 — RATE. Whole-tier wall clock, solo, one process.
**450–1100 s, point estimate 760 s.** *Basis:* B4/B5's recorded per-test
rates (5.4, 7.3 s) times the tier's current selected size; the band's width
is the spread between those two readings, extended down because the tier has
grown mostly by cheap `test_v*.py` marks and up because it has grown 49%
since B5 was taken. Precondition: this box has `nproc` 1 and nothing else
CPU-bound running — the number is meaningless if any other suite overlaps.
**Confidence: moderate.**

### P4 — RATE. `-m whence_slow` selects **103** nodes, not 104.
B1 counts 104 decorator lines and B2's last recorded fast run deselected
103. I predict the collected count is 103 and that the gap is exactly one:
one of the 104 grep hits is not a collected test node — a decorator on a
non-`test_` helper, a stacked/duplicated decorator on one node, or a hit
inside a string. I predict specifically that **no** `whence_slow` test is
parametrized into more than one node, because if any were the two numbers
could not be one apart in that direction. **Confidence: moderate** — B2 is
PROSE and is itself the thing being re-derived.

### P5 — RATE. Currently red whence_slow tests: **0**.
*Basis:* B5's most recent whole-tier reading was 70 passed / 0 failed, and
B4's single failure
(`test_self_eval.py::test_shape_needs_three_adjacent_tokens_on_both_sides`)
is named in the state file as since-resolved. This is the weakest line in
the bank: a 0-of-103 prediction over a tier nothing has run in the 4 days
since B5, across which every language round has edited the subject. If it
misses it will miss upward and that is the round's most valuable single
finding. **Confidence: low.**

### P6 — RATE. Cost concentration: the 4 most expensive FILES are ≥ 70% of tier wall clock.
*Basis:* `test_self_hosting.py` (12 marks), `test_self_eval.py` (11),
`test_polarity.py` (10), `test_miss_message_differential.py` (8),
`test_v29.py` (8) are the mark-count leaders and the first two run the
guest interpreter over whole programs, which is what B5's 7.3 s/test average
is made of. **Confidence: moderate.**

### P7 — RATE. Per-unit granularity costs 60–200 s of extra wall clock.
Running the tier as 28 separate pytest processes instead of one costs one
interpreter start + one collection per file. **Confidence: moderate.** This
is the price of making the tier's evidence per-unit, and it must be paid
visibly rather than discovered later.

### P8 — RATE. Re-derivation of round 468's three census figures.
Suite-mode `depthcensus.py --tests` **72–89 s** (claim 80.3, ±10%);
`--harvest-only` **2.1–3.3 s** (claim 2.6); `--residual` **2.2–3.4 s**
(claim 2.7); `tests/test_testcorpus_census.py` **4.5–8.0 s** at **45**
passed (claim 5.8 s / 45). *Basis:* all four are round 468's own numbers,
one round old, and nothing since has touched `depthcensus.py`.
**Confidence: high** — and if one of these misses, five consecutive rounds'
finding that a carried number is stale extends to a number only one round
old, which is a different and worse claim.

### P9 — RATE, and this one is a bet against my own design instinct.
My instinct is that a per-unit digest split (one shared digest over the
non-test sources + one digest over the unit's own test file) rescues most
units from most commits. I predict it does NOT: over the last 40 commits
that touch `languages/whence/`, **more than 60%** touch at least one
non-test `.py` or `.lang` file, so the split changes the verdict for fewer
than 40% of them. If P9 is right, the refinement is worth having but is not
the fix, and the honest report says so. **Confidence: moderate.**

### P10 — the answer to round 468's item 3, banked as a prediction so it can be scored.
I predict the honest answer is **"the slot does not exist"**: that the
census's ~80 s is a small fraction of the tier's total (P3), and that the
fraction is irrelevant because the tier's measured recall at HEAD is
**0 of 28 units (0%)**, so a test moved into `whence_slow` today is a test
that runs zero times per round and whose result is recorded nowhere. The
deliverable this earns is therefore not a marker on the census test but the
missing mechanism. **Confidence: high on the recall, moderate on the
framing.**

## What would make this round's report wrong

- If P1 is falsified, the round has duplicated something that exists and
  should stop and use it instead.
- If P5 misses upward, the reds are the finding and the mechanism is the
  supporting evidence, not the other way round.
- If P8 misses, every number quoted forward from round 468 needs re-deriving
  before it is used, including by this round.
