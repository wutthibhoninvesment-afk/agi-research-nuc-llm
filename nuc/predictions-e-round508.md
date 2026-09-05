# Round 508 (NUC-integration E) — predictions, banked BEFORE measuring

House rule **D-013**. Every line below is written before the command that
settles it has been run in this round. Committed as its own commit; the
scoring lives in `knowledge/round-508-*.md`.

## Context fixed before banking (read, not measured this round)

* Box **DOWN**: two tailnet probes 11:27:41Z / 11:28:19Z, rc 255 both;
  `LastSeen 2026-09-04T02:14:05.1Z`, byte-identical to rounds 490/496/502, so
  one continuous outage, fourth consecutive down E-window.
* Round 502 recorded three exclusions in `nuc/survivor_impact.py::BATTERY_GAP`
  and blamed the RECORD for two of them:
  - `reclaim` / `gap` — *"needs one sar table; the union's sar-all.txt is 120
    sections"*.
  - `window --channel commit|steal` — *"rc 1 on this record: no derived
    costly-threshold"*.
* `CHANNEL_MIN_BYTES = {"swap": LEDGER_MIN_BYTES, "commit": None,
  "steal": None}` is a module constant (read at `nuc/perturbation.py:1354`).
* Round 418 ran `reclaim`/`gap` on TWO hand-extracted day files
  (`B31.txt`, `R31.txt`, and sa30): 139 + 79 buckets, 4 + 3 reclaim buckets,
  **0 direct**, largest `stolen_bytes` 987,217,920 at 04:00:03 on 2026-08-31.
* Round 490 built `state/nuc-record-union` and reports **12 dates, 120
  sections, 4 captures read, 5 named unusable**.

## The predictions

**P1 — the `reclaim` exclusion is a property of the TOOL, not of the union.**
`python3 nuc/perturbation.py reclaim --sar-b state/nuc-capture-r424/sar-all.txt`
raises the SAME `header changed mid-table` `PerturbationError` that round 502
recorded against the union. Round 424's capture is the one every published
number in this track was computed from, so if this holds, the exclusion has
never been about the union at all.

**P2 — it fails on EVERY capture, not just on r424 and the union.** Of the
capture directories under `state/` that contain a `sar-all.txt`, **zero** can
be fed to `reclaim --sar-b` without raising. (Scored as a fraction: I predict
0 of N succeed.)

**P3 — the union's section census.** `sar_sections` over
`state/nuc-record-union/sar-all.txt` returns 120 sections of which exactly
**12** match `SAR_B_*` and exactly **12** match `SAR_R_*` (12 dates x 10
section kinds). I will score the two counts separately.

**P4 — the `window --channel commit` exclusion is an UNPASSED FLAG.**
`window --capture state/nuc-record-union --channel commit --min-bytes
<LEDGER_MIN_BYTES>` exits **0** and prints a ledger. The record is not missing
anything; `CHANNEL_MIN_BYTES[commit]` is `None` in the source and `--min-bytes`
has existed the whole time. The rc-1 is a documented refusal, not a fact about
this record — and the error message's own wording ("on this record") is what
made round 502 write it down as one.

**P5 — round 418's negative generalises across the whole union.**
`pgscand/s` (direct reclaim, the path where an allocation waits) is **0.00 in
every bucket of all 12 union days**: `n_direct_reclaim_buckets == 0` summed
over every day. Memory pressure on this box is eviction, never allocator
stall.

**P6 — the loud-reclaim count over 12 days lands in [15, 60].** Round 418 saw
7 loud buckets over 2 days (3.5/day); 12 days at that rate is ~42. I bank the
band rather than the point because the days differ in length (the union's
09-01 is a 30-sample day in one capture and a 3-sample day in another).

**P7 — 2026-08-31's 987,217,920-byte bucket stays the record maximum.** No
other union day has a `largest_bucket.stolen_bytes` above it. (Coin-flip-ish
and banked deliberately: 08-31 is a reboot day, and I am betting the reboot is
what made it the largest.)

**P8 — no `steal_exceeds_scan` bucket anywhere.** Summed over the 12 days,
`n_steal_exceeds_scan == 0`. Round 418 reported none on its two days and did
not say whether it looked.

**P9 — the commit channel is blind, not coarse, on MOST reclaim buckets.**
Over every reclaim bucket in all 12 union days, **at least 60 %** have
`level_bytes == 0` on the commit channel. Round 418 saw 2 of 3 at exactly
zero on one day.

**P10 — the misattributed-subject wording is not confined to one dict.** The
phrase "on this record" (or an equivalent that names the record as the thing
lacking the threshold) appears in **at least 2** places in this repo outside
`survivor_impact.BATTERY_GAP` — the raise site plus at least one knowledge or
state file that copied it.

**P11 — the fix moves the battery from 5 verbs to 7** and cuts `BATTERY_GAP`
from 9 entries to 7, with the two `window_*` entries KEPT but re-worded
(their subject changes; their exclusion does not).

**P12 — I will add 25-40 new test nodes** to `nuc/tests`, and the full
`nuc/tests` suite run solo will land in **[560, 700] s** (round 490 measured
564 s at 1131 nodes; round 502 added 34).

**P13 — mutation.** Of the mutants I generate against this round's own new
code, **at least 80 % die on the first pass**, and at least one survivor is a
real gap rather than an equivalent mutant. (Round 490: 24/29 first pass.)

**P14 — the new day-selection path will find at least one union day that
`reclaim` can parse but that carries ZERO reclaim buckets** — i.e. a day whose
whole contribution to the pooled number is denominator. If every day has at
least one loud bucket, this is a MISS.

**P15 — nothing in this round contacts the box.** Zero ssh sessions succeed,
port 8001 is never contacted, and `reachability_check.py coverage --strict`
stays 0 with `--no-allow-in-flight` as well as without.
