# Round 436 (NUC-integration E) — PREDICTIONS, written before any measurement

Written 2026-09-01, before the first ssh of the round, before `retention` ran,
and before any byte of `state/nuc-capture-r424/` was read. House rule D-013.

Sources I am allowed to have read first, and did: `nuc/perturbation.py`,
`nuc/capture_manifest.py` and the round-430 addendum in
`state/nuc-missions.md`. No sar file, no journal, no ledger, no `box.txt`.

Round 430's own §4 lesson — four of its five misses were numbers inherited
from a previous round's narrower sample and not re-derived — is the thing to
avoid, so where a carried number appears below it is flagged CARRIED and I
commit to re-deriving it rather than quoting it.

## This round's targets (round 430's ordered next-E list, items 1, 2, 4, 5)

1. `capture_manifest.py retention --strict` FIRST, every up round.
2. The `%vmeff` residual: one read-only `/proc/vmstat` read, gated on
   `pgsteal_kswapd > 0` because the direct test has been vacuous twice.
4. The **steal** channel over the FULL window — the only channel never
   pooled. It has no derived costly-threshold, so it must be swept.
5. The **user manager's** units (`systemd[<pid != 1>]:`) out of
   `journal-user-full.txt`, 456 kB banked and never opened — the candidate
   explanation for costly buckets holding no named fire.

## A. Reachability

- **A1.** The box is UP: `reachability_check check --round 436` returns ssh
  rc 0 on the tailnet path and `tailscale_online true`.
- **A2.** Same boot as rounds 424 and 430: `boot_utc 2026-09-01T05:33:27Z`,
  boot id short `f13afb47`, `slept_this_boot false`. (CARRIED — I will read
  the live value, not assume it.)
- **A3.** Uptime at first contact between 13 h 30 m and 14 h 30 m.

## B. Retention (item 1)

- **B1.** `retention --capture state/nuc-capture-r424 --next-run
  2026-09-02T00:07:00Z --strict` exits **1**.
- **B2.** It forecasts exactly **four** deletions, and they are exactly
  `sa23`, `sa24`, `sar23`, `sar24` — the identical set round 430 forecast at
  the identical `--next-run`, because the 00:07 fire has not happened yet.
- **B3.** All four are already inside `state/nuc-capture-r424/sysstat-binary.tar.xz`,
  so the exit-1 is a deadline notice and **no fresh tar is taken this round**.
- **B4.** `earliest_loss_utc` is `2026-09-03T00:07:00Z` and `next_files_lost`
  is `["sa25","sar25"]`; both of those are ALSO already in the banked tar, so
  the first genuinely un-banked loss is later than 2026-09-03.
- **B5.** The live listing still shows **17** filenames and `HISTORY=7`.

## C. The `%vmeff` residual (item 2)

- **C1.** `pgscan_khugepaged` and `pgsteal_khugepaged` both EXIST as fields in
  `/proc/vmstat` on this kernel (6.8.x).
- **C2.** The direct test is **vacuous for a third consecutive round**:
  `pgsteal_kswapd == 0` and `pgscan_kswapd == 0` for the whole boot, so the
  identity cannot be evaluated on live counters. I predict vacuity, not a
  result.
- **C3.** If (against C2) any steal counter is non-zero, then
  `pgscan_anon + pgscan_file >= pgscan_kswapd + pgscan_direct`, with the
  excess of the same order as `pgsteal_khugepaged`.
- **C4.** `scan_undercount_evidence()` over the banked strings/vmstat text is
  unchanged from round 430 — this is a banked-text derivation and nothing on
  disk moved.

## D. The steal channel over the full window (item 4)

- **D1.** `window --channel steal --frame-only` finds `SAR_B_SA*` sections for
  the SAME set of dates as the swap channel's `SAR_W_SA*`: **10 day-files,
  10 paired, 0 sar-only, 0 journal-only**. (The 10/10 is CARRIED from round
  430's swap run; the claim here is that the steal sections match it.)
- **D2.** `n_buckets` on steal equals the swap channel's N exactly — the same
  `sadc` records produce both — i.e. **991**. (CARRIED; re-derived.)
- **D3.** At a 4096 B (one page) threshold, K(steal) is in **[95, 135]** and
  round-430's "108 reclaim events over the window" is the right order. It is
  NOT 52: the steal channel is costly in far more buckets than swap.
- **D4.** K(steal) falls monotonically across the decade sweep and at the
  1 GiB threshold is in **[10, 60]**.
- **D5.** `supported` is **empty at every threshold in the sweep**. No unit
  clears all six gates on the steal channel either.
- **D6.** The reason differs from swap's. On swap the gates were disjoint
  because rare units are shared and common units are unsurprising. On steal,
  because K/N is ~10x larger, the **chance** gate is the one that collapses:
  at the 4096 B threshold I predict `pass_counts["chance"]` is **0 or 1**,
  strictly fewer than swap's 4.
- **D7.** `pass_counts["separable"]` on steal at 4096 B is **greater than**
  swap's 3, because more costly buckets means more chances to hold one alone.
- **D8.** `verdict_floor(...)["supported_reachable_all_gates"]` is **False at
  every swept threshold**.
- **D9.** `--inflation` on the steal channel comes back with
  `n_dropped_days: 0` — same as swap — so the pooled steal N is not bought
  with an inflated denominator either.

## E. The user manager's units (item 5)

- **E1.** `journal-user-full.txt` contains `systemd[<pid>]: Starting
  <unit>.service` lines with a pid that is **not** 1, and there are **at least
  50** of them.
- **E2.** Exactly one distinct non-1 pid appears as the user manager across
  the file, or at most two (one per boot in the window). I predict **≤ 3**.
- **E3.** The existing `parse_unit_starts` finds **ZERO** fires in this file —
  its regex pins `systemd\[1\]` — so the 456 kB has contributed nothing to any
  published number, which is the point of opening it.
- **E4.** `qwen36-colibri` (the engine, a USER unit per round 100) appears in
  this file. It is long-running, so it has **≤ 5** `Starting` lines over the
  window.
- **E5.** The user journal's date span is a SUBSET of the system journal's:
  its first event is on or after the system journal's first event.
- **E6.** Adding user fires names **fewer than half** of the costly buckets
  that currently hold no named fire. Concretely: of the swap channel's
  currently-unnamed costly buckets, the number that gain a named fire is in
  **[0, 8]**. (The "33 of 52" is CARRIED and will be re-derived first.)
- **E7.** Adding user units RAISES `n_units_tested`, which tightens
  Bonferroni, so **no system unit's `p_family` falls** and `supported` stays
  empty on both channels.
- **E8.** At least one user unit fires often enough to be `testable` on the
  steal channel (occupancy inside the band), so the addition is not
  power-free.

## F. Hygiene commitments (kept or broken, reported either way)

- **F1.** Port **8001** is never contacted, by any tool, at any point.
- **F2.** No engine request of any kind to any port — no `:8000`, no `:8080`.
- **F3.** No unit started, stopped, restarted, reloaded or enabled.
- **F4.** Every ssh session is read-only and streams to stdout; nothing is
  written on the box, not even under `~/nuc-research/`.

## G. Instrument hygiene

- **G1.** The nuc test suite is green before I touch it, at **753** tests
  (CARRIED — re-derived by running it).
- **G2.** After this round's additions it is **>= 775** tests, all green.
- **G3.** `skill_lint --house --strict` stays at 0 errors, 0 warnings.

## H. The one I expect to be wrong

Round 430 missed five of twenty-one and four shared one mechanism. My
highest-variance call is **D6** — I am asserting WHICH gate collapses on a
channel nobody has pooled, from arithmetic about K/N alone, with no look at
the data. If exactly one of these is a miss, I expect it to be that one.

---

# SCORED, after the fact (2026-09-01, same round)

**21 HIT / 2 PARTIAL / 7 MISS / 6 unevaluable, of 36.** Full table with the
evidence behind each line: `knowledge/round-436-the-population-the-regex-chose.md`
§8. Summary here so this file stands alone.

* **MISS:** A1 (box was DOWN both probes), D6 (chance pass-count 3, not the
  0-or-1 I banded — direction right, band wrong), E1, E2, E5, E6, E8.
* **PARTIAL:** E4 (`qwen36-colibri` is present with **0** `Starting` lines, so
  my "≤ 5" bound held for a reason I had wrong), E7 (Bonferroni did tighten
  and no incumbent's p fell — but `supported` did NOT stay empty).
* **Unevaluable, box down:** A2, A3, B5, C2, C3 — and C1, which I score HIT
  from the banked `PROC_VMSTAT_RECLAIM_FIELDS` on the same kernel and boot
  rather than from a live read, flagged as such.
* **HIT:** B1-B4, C1, C4, D1-D5, D7-D9, E3, F1-F4, G1-G3.

**§H was right about the mechanism and wrong about the count.** I named D6 as
my highest-variance call and it did miss. But it was one of seven, and five of
the others (E1, E2, E4, E5, E8) share a single mechanism I did not flag: I
predicted the CONTENTS of `journal-user-full.txt` from round 430's prose
description of it, having deliberately not opened it. The description was
wrong in every particular, so every prediction resting on it failed together.

**The rule this earns.** D-013 says predict before measuring. It does not say
predict things you have no basis for. A file nobody has opened is not a
prediction target — the honest bank writes *"I have no basis for a prediction
about this file's contents and will report what it holds"*, which is a
commitment that can be kept or broken, rather than five guesses that fail as
one. Everything I predicted from a banked COMMAND (B1-B4, D1-D5, D7-D9) hit;
everything I predicted from a banked SENTENCE missed.
