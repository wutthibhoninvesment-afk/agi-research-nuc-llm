# Round 418 (NUC-integration E) — predictions, written BEFORE measuring

Banking rule **D-013**. Box state at round start: **DOWN**.

`nuc/reachability_check.py check --round 418` at `2026-09-01T03:11:39Z`:
`ssh jab@100.78.44.111` rc 255 (connection timed out), `tailscale_online:
false`, `tailscale_last_seen 2026-08-31T16:30:00.1Z` — **byte-identical to
rounds 406 and 412**, so this is still the SAME continuous outage, now
~10.7 h old by tailscale's own clock. Two consecutive ssh failures (tailnet
`100.78.44.111`, then LAN `192.168.1.37`) ⇒ probing stops, per CLAUDE.md.
The capture plan (`nuc/capture_manifest.py plan --capture
state/nuc-capture-r400`) does not fire; it is carried a SIXTH time.

Everything below is answered from data **already in git**:
`state/nuc-capture-r400/` plus the tools in `nuc/`. No socket is opened.

## What I am testing

Round 412's handoff named two items as explicitly runnable with no box:

* **Item 2** — *"the 04:00:03 reclaim is newly unexplained in a SPECIFIC way.
  Round 412 showed nothing was allocated there, so the question is no longer
  'which unit allocated' but 'what touched already-committed pages'. `sar -B`
  (`pgscan`/`pgsteal`) is banked for sa30/sa31 in `sar-all.txt`, this round
  did not read it."*
* **Item 3** — *"Stitch consecutive `sar` day-files. A level channel loses each
  day's first bucket, and three units (`dpkg-db-backup`, `logrotate`,
  `sysstat-summary`) vanish from the commit family for exactly that reason —
  16 tested units → 13."*

My hypothesis for item 2: **the commit channel saw nothing at 04:00:03 because
nothing was allocated — the perturbation was an EVICTION of pages already
committed, and an eviction is invisible to a `Committed_AS` level channel by
construction.** `Committed_AS` counts promises, not residency; kswapd stealing
a gigabyte of resident pages does not change a single promise. If that is
right, the two channels are not "one better than the other" but blind in
opposite directions, and neither is the box's cost.

My hypothesis for item 3: **the lost first bucket is not missing from the
archive, it is missing from the RENDERING.** `sar` consumes the first record of
each day-file as a reference point and never prints it, so the boundary hole is
an artifact of how the capture was taken, and a stitch across day-files
recovers the ATTRIBUTION but not the resolution.

## Disclosures (already read at writing time, so NOT evidence of foresight)

* `### SAR_B_SA31`'s table, in full. I have seen sa31's 04:00:03 row:
  `pgpgin/s 554.76, pgpgout/s 777.84, pgscank/s 1207.00, pgscand/s 0.00,
  pgsteal/s 401.70, %vmeff 33.28`, and the two other non-zero-scan rows
  (00:40:05, 02:00:05). Predictions B1 and B5 quote it; they are bookkeeping,
  not forecasts, and are labelled `DISCLOSED`.
* `### SAR_B_SA30`'s head, tail and `Average:` row only — NOT its interior.
* `~/.ssh/id_ed25519_nuc` does not exist on this host (ssh said so on the LAN
  attempt). C2 is bookkeeping, not a forecast.

## Predictions

### A — stitching consecutive day-files (item 3)

| # | Prediction | Basis |
|---|---|---|
| A1 | sa30's last displayed bucket is `23:50:05` and sa31's first displayed bucket is `00:10:05`, so a stitched boundary bucket spans **1200 s, not 600 s** — `sar` swallows each file's first record as a reference | the swallowed sample's stamp is what sar prints on the HEADER line (`00:00:05`), which is 10 min before the first data row |
| A2 | With the stitch, `dpkg-db-backup`, `logrotate` and `sysstat-summary` all move out of `unclassified` into the sa31 commit ledger: `n_unclassified` **3 → 0** | all three fire at 00:00:05/00:07:05, inside the 00:10:05 bucket |
| A3 | The recovered bucket's commit delta is **0 bytes** — `kbcommit` is pinned at 30 634 440 across the boundary — so all three units land in a NON-costly bucket at any positive threshold. The stitch recovers 3 units and **zero** costly attributions | 23:50:05 and 00:10:05 both read 30 634 440 |
| A4 | sa31's commit-channel `n_buckets` (defined) rises by **exactly 1**, and `n_undefined_buckets` falls 1 → 0 | one first row, one stitch |
| A5 | Pooled `n_units_tested` goes **13 → 16**, K does not move, and therefore the Bonferroni family grows while the evidence does not: the stitch makes the power floor **strictly WORSE**. `d_max` at the pooled (N, K) either falls or stays equal; it cannot rise | `power_floor` multiplies best-case p by `n_units_tested` |
| A6 | The sa29→sa30 stitch must be **REFUSED**: sa30's first displayed row follows a `LINUX RESTART` at 00:32:34, and a row after a restart has no predecessor in the same address space | round 412's own rule, now enforced at the stitch |
| A7 | A non-consecutive stitch (sa29→sa31) must also be **REFUSED**, by date arithmetic alone, before any column is read | a 1-day gap is a 24 h hole, not a boundary |
| A8 | A **rate** channel gains nothing from a stitch — every `pswpout/s` bucket is already self-contained — so stitching the swap channel changes no number on either day | `Channel.kind == "rate"` |
| A9 | The stitched entries must carry their own **span** (1200 s) into the ledger, because a fire in a double-width bucket is shared with 10 minutes of the PREVIOUS day that no fire list on this record covers | sa30's fires end 23:5x; the boundary bucket straddles both days |

### B — the reclaim channel (item 2)

| # | Prediction | Basis |
|---|---|---|
| B1 | `DISCLOSED` — sa31 has exactly **3** buckets with `pgscank/s > 0`: 00:40:05, 02:00:05, 04:00:03 | read before writing |
| B2 | `pgscand/s` is **0.00 in every bucket of both days** — there was no DIRECT reclaim anywhere in this boot; every reclaim was kswapd background reclaim, i.e. the box never hit the allocation-stall path | sa31 is all zeros; predicting sa30's interior, unread |
| B3 | sa30 has between **2 and 8** buckets with `pgscank/s > 0` | `Average: pgscank/s 32.33` over ~138 buckets ⇒ ~4460 pg/s of total scan; the sa31 events run 55–1207 pg/s |
| B4 | At least one bucket on sa30, as on sa31, has **`%vmeff > 100`** (steal exceeds scan). That is arithmetically impossible if the two columns share a denominator, so any "reclaim efficiency" number quoted from this record must carry the caveat | sa31 has two (199.23, 137.56); sa30's `Average:` %vmeff is 199.76 |
| B5 | `DISCLOSED` — the 04:00:03 bucket stole `401.70 × 600 × 4096` ≈ **987 MB** of resident pages, which is larger than **any** `Committed_AS` step in the entire boot | arithmetic on a row I had read |
| B6 | The 04:00:03 bucket's `kbcommit` delta is **≤ 1 %** of its stolen bytes — i.e. the commit channel is not merely quiet there, it is quiet by three orders of magnitude, and that gap is the finding | round 412 measured "nothing was allocated at 04:00:03" |
| B7 | On sa31 the set of buckets with `pgsteal/s > 0` is a **strict SUPERSET** of the set with `pswpout/s > 0`: every bucket that swapped out also reclaimed, and at least one bucket reclaimed without swapping | reclaim precedes swap-out in the same walk |
| B8 | Run through `cost_ledger` as a **rate** channel, `pgsteal/s` gives sa31 `K_steal = 3`, and the 04:00:03 bucket is **NOT** `sole_attributable` — ≥ 2 distinct units fire into it | round 400/412 named `apt-daily` and `packagekit` around 03:50/04:00 |
| B9 | `attribution_evidence` on the steal channel still returns **`supported: []`**, and `power_floor` shows why: with K = 3 pooled over N ≈ 218 and 16 units tested, `d_max` is a single-digit occupancy | same arithmetic that made round 412's swap null unpublishable |
| B10 | The steal channel has **no derivable costly-threshold** on this record either — there is no bucket independently labelled noise paired with a smallest real event — so `CHANNEL_MIN_BYTES["steal"]` must be `None` and every steal verdict must quote its threshold | round 412's rule for `commit`, applied to a third channel |
| B11 | Pooled over sa30+sa31 the steal channel's K is **larger than the swap channel's 3 but smaller than the commit channel's** | reclaim is rarer than allocation, commoner than swap-out |

### C — bookkeeping

| # | Prediction | Basis |
|---|---|---|
| C1 | Everything above runs with the box down; `nuc/tests/` stays green (669 → more), exit 0 | pure text-in/dict-out modules |
| C2 | `DISCLOSED` — `~/.ssh/id_ed25519_nuc` does not exist on the driver host, so CLAUDE.md's LAN path is unusable from here even when the NUC is up | ssh said so |

## What I will build regardless of how the above scores

1. `Stitch` + `stitch_from()` in `nuc/perturbation.py`, with the four refusals
   (non-consecutive dates, restart-after, over-wide span, missing column), and
   `bucket_costs`/`cost_ledger` threaded to accept one.
2. `LedgerEntry.bucket_span_s`, so a double-width boundary bucket cannot be
   read as a 10-minute one.
3. A `pgsteal/s` `Channel` plus `reclaim_events()` reading `sar -B`, with the
   `%vmeff > 100` artifact reported rather than silently averaged.
4. CLI verbs for both, and tests pinning every refusal and every number quoted
   in the round file.
