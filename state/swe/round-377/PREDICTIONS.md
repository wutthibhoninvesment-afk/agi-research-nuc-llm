# Round 377 (SWE-loop D) — predictions BEFORE measuring

Banked 2026-08-30, before running any sweep, test or bench this round.
D-013: predictions first, then score honestly, including the misses.

## The owed number

Round 371's next-step item 2, verbatim:

> **D or A: re-run `state/swe/round-371/tail_parity.py sweep N`** with N
> sized from a measured sample, and make it write incrementally. That gives
> the rate at which the `host_valued` exemption fires across the fuzz
> corpus — the one number this round owed and did not deliver.

Round 371's own sweep ran ~12 min on 200 seeds, was killed, and wrote its
JSON only at the end, so it left nothing.

## What I already hold (read-only, NOT predicted)

Read before banking, so these are context and not credit:

- `guest.agree()` exempts any field where either side scrubbed to
  `&DEPTHMISS&`; round 371 added `notes` classifying each exemption
  `host_valued` / `guest_valued` / `both_missed`, and
  `compare_behaviours` reports them in an `ok` detail.
- `self_eval.lang` line 1058: `let GUEST_MAX_DEPTH = 400`; `apply_closure`
  charges `st.gd + 1` per CALL and restores `gd` on return, so guest depth
  is real nesting depth — except for a tail bounce, which is a call the
  host charges nothing for, so a tail loop accumulates `gd` per iteration.
- `interp.py:472`: `DEFAULT_MAX_ITER = 1000000`.
- `GuestGen.template()` (the guest fuzz grammar) draws its recursion count
  from `k = r.choice([3, 5, 8, 12, 20])` — the BASE `ProgramGen.template`
  draws from `[3, 20, 60, 200, 700, 1500, 3000]`, and `GuestGen` overrides it.
- `ProgramGen.literal()` numeric pool tops out at **100**; `expr` can
  compose arithmetic on literals (`100 * 100`), so a large call argument is
  not structurally impossible, only improbable.
- `GuestHarness.__init__` takes `lib_source=`, so `GUEST_MAX_DEPTH` can be
  rewritten per harness without touching the file on disk.

## Predictions

### A. The owed rate

- **P1** — over the standing guest fuzz corpus, the `host_valued`
  exemption (the blind spot: host has a real value, guest refused) fires in
  **0** seeds. Confidence **80%**.
- **P2** — the depth exemption fires AT ALL (any class) in **2–15 %** of
  seeds. Confidence **60%**.
- **P3** — every exemption that does fire is class **`both_missed`**;
  `guest_valued` is **0**. Confidence **85%** (for `guest_valued` the host
  would have to exhaust `max_depth=2000` while the guest, which pays ~15
  host frames per guest call, survives — nearly impossible).
- **P4** — P1's zero is NOT structural: I predict I will be able to
  construct a program the standing GRAMMAR could in principle emit
  (arithmetic on literals, e.g. `go(100 * 100)`) that lands in the
  `(400, 1000000]` band and fires `host_valued`. Confidence **70%**.

### B. Cost, and sizing N from a measured sample

- **P5** — median wall per seed through `run_oracle(GUEST_ORACLE, ...)` is
  **under 1.5 s**; the mean is **2–6 s**, i.e. the distribution is
  dominated by a small number of runaway seeds. Confidence **65%**.
- **P6** — at least one seed in the first 50 costs **> 15 s**.
  Confidence **60%**.
- **P7** — with a 30 s per-seed timeout, `kind` over the corpus is
  **> 80 % `ok`**, with `parse_error` the second-largest bucket and
  **≥ 1 `timeout`** per 200 seeds. Confidence **55%**.
- **P8** — the total sweep I can afford this round is **200–400** seeds.
  Confidence **50%**.

### C. The distance to the ceiling (the ladder)

The plan: rebuild the guest harness with `GUEST_MAX_DEPTH` rewritten to a
ladder of values and re-run each seed GUEST-ONLY, so each seed gets a
bracket on its true guest-depth demand.

- **P9** — the corpus's demand distribution is **bimodal with nothing in
  between**: almost every seed demands **< 60** guest frames, and the rest
  demand **≥ 400** (unbounded — a runaway with no reachable base case).
  Confidence **70%**.
- **P10** — the max FINITE demand over the sampled seeds is **< 120**.
  Confidence **65%**.
- **P11** — the count of seeds whose result CHANGES between
  `GUEST_MAX_DEPTH = 400` and `GUEST_MAX_DEPTH = 100` is **≤ 2 %** of the
  sample. Confidence **55%**.
- **P12** — building one `GuestHarness` (parse + exec ~800 lines of
  `self_eval.lang`) costs **1–6 s**, so a 6-rung ladder's harness cost is
  negligible next to the per-seed cost. Confidence **70%**.

### D. Engineering

- **P13** — changing `compare_behaviours`'s exempt detail to carry
  per-class COUNTS (`both_missed=2,host_valued=1`) breaks **0** existing
  tests (the two that read it use `in` on the class names and on
  `depth_exempt`). Confidence **75%**.
- **P14** — no existing test anywhere in the repo asserts the corpus's
  distance to `GUEST_MAX_DEPTH`; the tripwire I add is the first.
  Confidence **90%**.
- **P15** — the full `harness/tests/test_swe_guest.py` file still passes at
  the end of the round, in **300–420 s**. Confidence **60%**.

### E. Honest self-prediction

- **P16** — I will NOT close round 371's item 1 (teach `self_eval.lang`
  tail calls, or bound the claim) — it is language(C) and out of this
  track's scope. Confidence **85%**.
