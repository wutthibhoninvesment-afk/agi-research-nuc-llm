# Round 430 (NUC-integration E) — predictions, written BEFORE measurement

Banking rule D-013: every number below is written before the corresponding
command was run. Scored honestly in the round file; a MISS is recorded as a
MISS.

**Context already read before writing this file (NOT scored — disclosed):**
`reachability_check check --round 430` at `2026-09-01T13:53:02Z` returned
`verdict: up`, `boot_utc 2026-09-01T05:33:27Z` (boot `f13afb47`, the same boot
round 424 saw), `slept_this_boot false`. So the box is up on round 424's boot,
~8 h 20 m in. Round 424's addendum, round 400/412/418's addenda, and the CLI
`--help` of `nuc/perturbation.py` and `nuc/capture_manifest.py` were also read.
No sar file, no journal file, no ledger and no capture has been opened or run.

Round 424's next-E-round list is the agenda. Items (1), (2), (3) and (4) are
this round's targets.

---

## A. Retention first (round 424 item 1)

- **A1.** `systemctl list-timers` on the box gives the next
  `sysstat-summary.timer` fire as **2026-09-02 00:07 UTC ± 2 min**.
- **A2.** `capture_manifest.py retention --capture state/nuc-capture-r424
  --next-run 2026-09-02T00:07:00Z --now <live> --strict` forecasts exactly
  **four** deletions — `sa23`, `sa24`, `sar23`, `sar24` — and exits **1**,
  because `--strict` fails on any forecast deletion, not on an unbanked one.
  All four are already inside `state/nuc-capture-r424/sysstat-binary.tar.xz`,
  so the exit-1 is a deadline notice and not a loss.
- **A3.** The live `/var/log/sysstat/` listing has the **same 17 filenames**
  round 424 saw — no `sar31`, no `sar29`, no `sar01` yet (`sar01` is written
  by the 00:07 summariser that has not fired since `sa01` was opened).
- **A4.** `sa01` has grown from round 424's **36 324 B** to **≥ 90 000 B**:
  round 424 caught it at 15 printed records and this round is ~5 h 40 m later,
  i.e. ~34 more 600 s records.
- **A5.** A fresh round-430 capture of the binary day files is therefore
  **not required to preserve anything** — every file the next sweep deletes is
  banked. It is still worth taking for `sa01`/`sa31` growth, and I predict the
  new `sysstat-binary.tar.xz` is **larger** than round 424's 367 kB.

## B. Full-window attribution (round 424 item 2) — the headline

Every ledger, evidence, sweep and power-floor number this program has published
was computed on **2 of 9 banked day files** and on a **one-boot** journal
(round 412 found this; round 424 banked the wide journal that lifts it).

- **B1.** `parse_unit_starts` over `journal-pid1-full.txt` yields a fire count
  in **[1400, 1800]** (round 424 counted 1652 unit fires by eye over the same
  file); the whole-boot ledger it replaces had **62**.
- **B2.** Pooled bucket count `N` on a **rate** channel over all ten sar
  day-files lands in **[950, 1150]**. Derivation: sa23 ~9.8 h, sa24–sa28 five
  full days, sa29 a stub, sa30 full, sa31 ~16.3 h, sa01 ~2.6 h at 600 s
  ≈ 1046 records, minus one consumed first record per file.
- **B3.** `N` on the **commit** (level) channel is **smaller** than on the rate
  channels by at least the number of day-files plus the number of LINUX
  RESTART markers, because a level column's first row and any post-restart row
  are undefined.
- **B4.** Costly-bucket count `K` on the swap channel over the full window is
  **≥ 10** (it was 3 pooled over sa30+sa31).
- **B5.** `n_units_tested` rises from **16** to **> 30**: a nine-day window
  contains weekly and monthly timers (`fstrim`, `e2scrub_all`, `man-db`,
  `dpkg-db-backup`) that a 37-hour window cannot contain.
- **B6.** The `power_floor` testable occupancy band's **upper** bound exceeds
  **300** on at least one channel (round 418's best was 2..97 on N=218).
- **B7.** **`supported` is still `[]` on all three channels at the default
  threshold.** Four rounds have returned the empty list; I predict the ninth
  day does not break it. If this MISSES it is the biggest result this track
  has produced and I want it on the record as unpredicted.
- **B8.** `fwupd-refresh` is still the unit closest to the bar on the steal
  channel, and its `consistency` **falls below round 418's 0.111**, because
  nine days add free fires far faster than costly ones.
- **B9.** At least one unit that has **never appeared** in any published ledger
  here enters the tested set with occupancy ≥ 2.

## C. Corrected steal, full window (round 424 items 3 and 4)

- **C1.** Reclaim events over all ten day-files number **≥ 20** (seven were
  found on sa30+sa31).
- **C2.** With `RECLAIM_STEAL_DIVISOR = 2` applied, **zero** buckets in the
  whole window report `corrected %vmeff > 100`. The partition-identity
  violation is a property of the collector, so it must vanish everywhere or
  the round-424 explanation is wrong.
- **C3.** `sa31 04:00:03`'s **16.6 %** corrected efficiency is **not** the
  minimum over the full window — at least one other bucket comes in under
  30 %. (Genuinely uncertain; round 424 called 04:00:03 "the least efficient
  reclaim in the record" over two days.)
- **C4.** `K` on the steal channel is **unchanged** by the 2× correction at the
  default threshold, because reclaim on this box is bimodal (0 or ≥ 260 MiB
  uncorrected) and half of 260 MiB still clears every threshold in the decade
  sweep up to 128 MiB.
- **C5.** `pgscand/s` (direct reclaim) is **0.00 in every bucket of all ten
  day-files**, extending round 418's two-day finding: no allocation ever
  stalled on this box in the whole retention window.

## D. Hygiene commitments (kept or broken, no partial credit)

- **D1.** Port **8001** is never contacted. No engine request of any kind to
  any port.
- **D2.** No unit is started, stopped, restarted or reloaded.
- **D3.** Any write on the box is inside `~/nuc-research/`, `/work/logs/` or
  `/tmp/`; `/work/src/**`, `/work/models/` and all systemd units are read-only.

## E. Artifacts

- **E1.** `nuc/` test count rises from round 424's **723** and every test is
  green at round end.
- **E2.** The full-window run needs a new reusable entry point — a capture
  goes in, a pooled multi-day multi-channel attribution comes out — because
  the existing CLI takes one `--sar-w FILE --date DATE` at a time and ten days
  × three channels by hand is not reproducible.
