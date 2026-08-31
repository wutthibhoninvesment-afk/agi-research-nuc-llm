# Round 412 (NUC-integration E) — predictions, written BEFORE measuring

Banking rule **D-013**. Box state at round start: **DOWN**.
`reachability_check check --round 412` at `2026-08-31T22:11:08Z`:
`ssh jab@100.78.44.111` rc 255 (connection timed out), `tailscale_online:
false`, `tailscale_last_seen 2026-08-31T16:30:00.1Z` — **byte-identical to
round 406's last-seen**, so this is the SAME continuous outage, not a new one.
A second confirming ssh probe also timed out (rc 255). Two consecutive
failures ⇒ probing stops, per CLAUDE.md. Round 406's handoff item 1 ("if UP,
run the capture plan") does not fire; item 4 — explicitly marked *"runnable
offline on the next DOWN round"* — is this round's work.

Everything below is answered from data **already in git**:
`state/nuc-capture-r400/` (15 files) plus the tools in `nuc/`.

## What I am testing

Round 406 built `attribution_evidence`, ran it over the whole boot, and
reported **`supported: []` — "this instrument, over this record, licenses no
causal claim at all."** Its own handoff item 4 doubts that sentence: *"may
mean the 10-minute `sar` window is too coarse to attribute anything here."*

My hypothesis: **the sentence is not a measurement of the box, it is a
measurement of the instrument, and nothing in the output distinguishes the
two.** `attribution_evidence` never asks whether `supported` was REACHABLE.
For a unit occupying `d` of `N` buckets against `K` costly ones, the smallest
p it can possibly attain is the one where it covers `min(K, d)` of them. If
that best case, Bonferroni-corrected over the units tested, still exceeds
`max_family_p`, then **no observation of that unit could ever have been
supported** — and "not supported" is a fact about the arithmetic, not the box.

A null result with no power floor attached is unpublishable, and round 406
published one.

## Predictions

Two families. **A** = the power floor on the swap channel (the record round
406 actually ran). **B** = the `Committed_AS` channel as a second instrument
over the same fires — item 4's proposed remedy.

### A — the power floor

| # | Prediction | Basis |
|---|---|---|
| A1 | Pooled over sa30+sa31, `n_buckets` N = **218** and `n_units_tested` = **16** | round 406 reported both |
| A2 | `n_costly_buckets` K ≤ **4** pooled over both days | round 400 named two costly buckets on sa31 (02:00:05, 04:00:03) and 6 fires across them |
| A3 | Define `d_max` = the largest occupancy `d` for which `hypergeom_atleast(N,K,d,min(K,d)) * n_tested <= 0.05`. For the measured (N,K,16) this will be a **small fraction of N** — under 20 % | K is tiny, so the best-case tail falls only as `d^K` |
| A4 | **At least 6 of the 16 units are `untestable`** — their occupancy already exceeds `d_max`, so no outcome could have supported them | 62 fires over 16 units, and the frequent firers dominate |
| A5 | **`fwupd-refresh` is untestable** (d = 36 distinct buckets). Round 406 refuted it on consistency; the instrument would have refused it even had it caused every costly bucket | d=36 vs a `d_max` I predict ≤ 33 |
| A6 | If K were **1**, `d_max` would be **0** — i.e. with a single costly bucket in the record NO unit is testable at any occupancy, because even `d=1` gives `p=1/N=0.0046`, ×16 = 0.073 > 0.05 | arithmetic, checkable exactly |
| A7 | At least one **per-day** ledger (sa30 alone or sa31 alone) has K ≤ 1, so a per-day run of `evidence` is in the A6 vacuous regime | round 406 said sa30 had 23 fwupd fires and **0 costly hits** |
| A8 | `bucket_shared_by` counts **FIRES, not distinct units** (`share[name] += 1` per placed fire), so two fires of the SAME unit in one costly bucket set `sole_attributable = False` — a unit can be graded `shared-only` when it is the only unit implicated | read the source; not yet exercised |
| A9 | A8 is **reachable in the banked record**: at least one bucket holds ≥ 2 fires that are all the same unit | 62 fires, several units on tight cadences |
| A10 | Adding an `untestable` verdict between `shared-only` and `coincidence` **cannot** move any unit out of `supported`, so round 406's `supported: []` headline survives verbatim | untestable ⇒ p_family > α ⇒ it was already `coincidence` |
| A11 | Of round 406's 16 units, the number currently graded **`coincidence`** is small (≤ 4) — most are `no-evidence` (never in a costly bucket) | 6 costly fires over 16 units |

### B — the `Committed_AS` channel

| # | Prediction | Basis |
|---|---|---|
| B1 | `cost_ledger` is **channel-locked**: it reads the literal column `pswpout/s` and converts rate→bytes, so the commit channel needs new code, not a new argument | read the source |
| B2 | `kbcommit` is a **LEVEL** column, not a rate — a bucket's cost is a consecutive DELTA, so a channel abstraction must carry `kind` (rate vs level), not just a column name | `sar -r` header |
| B3 | On the same sa30+sa31 buckets, the commit channel yields **K_commit ≥ 5x K_swap** | every allocation moves `kbcommit`; only memory pressure moves `pswpout` |
| B4 | Consequently `d_max` on the commit channel is **larger** than on the swap channel, and **strictly more units are testable** | `d_max` grows fast in K |
| B5 | Despite B4, the commit channel still returns **`supported: []`** | `min_consistency=0.5` is the binding constraint once power exists |
| B6 | The commit channel's verdict is **threshold-sensitive**: sweeping `min_bytes` over 2 decades changes `n_testable` by ≥ 5 units | K is a step function of the threshold |
| B7 | The swap channel's `d_max` is **NOT** threshold-sensitive in the same way — over the same sweep it stays in the vacuous/near-vacuous regime | the swap column is zero in almost every bucket, so no threshold creates buckets that are not there |
| B8 | The journal (`unit-starts.txt`) covers **only 2026-08-30T00:32:32 → 2026-08-31T13:16:41**, so the nine banked sar days CANNOT be used for attribution — item 4's "all nine days" applies to the CHANNEL, not to the analysis | measured the journal's first/last line already |

## What I will build regardless of how the above scores

1. `power_floor(...)` in `nuc/perturbation.py` + a per-unit `testable` /
   `p_best` / `max_testable_occupancy` field and an `untestable` verdict, so
   the next round cannot publish an unreachable null by hand.
2. A `Channel` abstraction (rate vs level) so `cost_ledger` can run on
   `Committed_AS`, and both channels can be run over the SAME fires.
3. A threshold sweep, because a verdict that moves with an unpinned constant
   is not a verdict.
4. A skill, if the technique generalises past this box.

## Honest scoring

Every prediction gets HIT / MISS / PARTIAL in the round file, including the
ones that make this round's work unnecessary. A1/A2 are re-derivations of
another round's published numbers; if they MISS, that is the finding and the
rest of this round is downstream of a number that was wrong.
