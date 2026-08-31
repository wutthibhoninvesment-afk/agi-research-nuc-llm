# Round 400 (NUC-integration E) — predictions banked BEFORE measurement (D-013)

Banked: 2026-08-31 ~13:16Z, before ANY measurement other than the two
instruments the round protocol mandates first (see "NOT SCORED" below).

**Context carried in (all from round 394's record, `knowledge/round-394-*.md`):**
- boot `43e0c767e98e41c5a2c0d475a15e06cf`, boot_utc 2026-08-30T00:32:27Z
- round 394 last contacted the box at ~09:30Z; this round at 13:14:19Z
  ⇒ an **unobserved gap of ~3h44m–4h03m**
- `anon + swap.current` = **30,600,970,240 B**, byte-identical across r382/r388/r394
- `memory.swap.current` = **274,530,304 B**; `memory.current` = **30,412,222,464 B**
- system `pswpout` since boot = **72,044 pages**; qwen36-colibri cgroup holds
  67,024 of them
- `pgscan_kswapd` (cgroup) = **2,587,671**; `workingset_refault_anon` = 0
- `fwupd-refresh.service` fired **34** times this boot, downloaded 26, and
  **exactly one** of the 34 cost the engine anything (01:57:33Z, 67.7 MB)
- **round 394 predicted `apt-daily.service`'s next fire at 10:22:25Z**, read
  from `systemctl list-timers`. That instant is INSIDE this round's gap.
- corrected `--cap` recommendation **196**, sound band **[129, 204]**
- `nuc/tests` 551 green; constant audit 20 constants / 15 derived / 0.750 / 0 risks

## NOT SCORED (observed before the bank, by protocol)
- **N1** box UP, ssh reachable, tailscale online — `reachability_check.py check
  --round 400` is the round's mandated first instrument and ran at 13:14:19Z.
- **N2** `boot_utc` 2026-08-30T00:32:28Z, `slept_this_boot false` — captured by
  the same command. (The 1 s difference from round 394's 00:32:27Z is
  `/proc/uptime` quantisation, not a reboot; ninth consecutive E-round on this
  boot.)

---

## A. The one prediction this round exists to settle

- **P1 — `apt-daily.service` started at 10:22:25Z ± 5 s**, inside the gap.
  Round 394 read this from `systemctl list-timers`, where `NEXT` is a
  *committed* schedule (systemd draws `RandomizedDelaySec` once, at schedule
  time), not a fresh draw. Confidence high. This is the first time in this
  track that a round's forward-looking claim about the box's future has been
  scoreable by the next round.
- **P2 — that fire cost the engine ZERO swapped pages**, i.e. the
  10:20:05–10:30:05 `sar -W` bucket has `pswpout/s == 0.00`. Confidence ~60 %,
  and I state the mechanism so a miss is informative: 288 MB of anonymous
  memory is *already* banked in swap and `workingset_refault_anon == 0`, so
  nothing has pulled it back; apt's demand is page-cache demand, and the
  141 MB of cache apt itself grew at 03:50 is the cheapest reclaim target on
  the box. The engine only pays when the reclaim target list is exhausted.
  **This is the branch I would rather be wrong in** — a non-zero bucket would
  mean apt is repeatably expensive and the guard has to become a schedule.
- **P3 — system `pswpout` since boot is UNCHANGED at 72,044 pages.** Strictly
  stronger than P2 (it covers the whole gap, not one bucket). If P2 holds and
  P3 fails, some *other* bucket moved and §the ledger below has a new case.

## B. The invariant, and the four numbers round 394 got wrong by assuming motion

Round 394's nine misses had one shape: "this number moved last time, so it
will move again". I am predicting the opposite for the same counters, and
naming what would legitimately change each one.

- **P4 — `anon + memory.swap.current` is byte-identical at 30,600,970,240.**
  Only a completion, an engine restart, or an allocator free changes this.
  None can have happened under zero traffic. THIRD observation window.
- **P5 — `memory.swap.current` is byte-identical at 274,530,304**, and
  `memory.swap.peak == memory.swap.current`. Changes only if a reclaim event
  in the gap took engine pages — i.e. iff P2/P3 miss.
- **P6 — `memory.current` is byte-identical at 30,412,222,464.**
- **P7 — cgroup `pgscan_kswapd` is unchanged at 2,587,671**; `pgscan_direct`
  0; `memory.events` all 0 (max, high, low, oom, oom_kill); `allocstall_*` 0;
  `workingset_refault_anon` 0.
- **P8 — the completion counter in the engine log is still exactly 2**, and
  still exactly one `unpacking to int8 in slot` line. Fifth consecutive round
  at 2. Per round 382's item 1, if this holds I will record the plateau as
  a property of zero traffic rather than re-asking a sixth time.

## C. The perturbation cost ledger (this round's build)

I intend to join *every* housekeeping unit start in this boot's journal
against the `sar` bucket it falls in, over the whole boot (sa30 + sa31), and
compute the base rate at which a named fire costs the engine anything. Round
394 had n=1 case and n=3 controls.

- **P9 — `fwupd-refresh.service` has now fired ≥ 38 times this boot**
  (34 at 09:11Z, `OnCalendar` hourly with `RandomizedDelaySec=1h`, +4h03m of
  gap ⇒ +4 expected).
- **P10 — the ledger's base rate is ≤ 10 %**: over all housekeeping fires this
  boot, fewer than one in ten falls in a bucket with non-zero `pswpout`.
  Round 394's 1-of-34 for fwupd alone is 2.9 %; adding apt/motd/packagekit
  fires can only add denominators faster than numerators, since `sar -W` has
  only **4** non-zero buckets in the entire boot.
- **P11 — the ledger will find ≥ 1 fire I cannot classify**, i.e. a unit start
  in a bucket that `sar` does not cover (the boot's first bucket, or a
  `LINUX RESTART` boundary). `parse_sar` raising on a short row is the whole
  reason I expect this to surface rather than silently mis-align.
- **P12 — `commit_steps` on the full-boot `sar -r` capture returns exactly
  TWO persistent steps that are the engine** (the 13:30 and 15:00 buckets of
  2026-08-30, +17.16 GiB and +6.82 GiB) **plus exactly ONE that is not**
  (02:00:05 on 08-31, +147,092 kB, fwupd). Three persistent steps total in
  ~37 h. This is `perturbation.py` run on data it was NOT written against —
  round 394 built and validated it on the 08-31 00:00–09:00 window only.
- **P13 — `perturbation.py` will need at least one code change to parse the
  full-boot capture.** It has only ever seen one day's file. `sa30` contains
  a `LINUX RESTART` line (the boot is at 00:32 on the 30th) and the two files
  concatenated give a header repeat and a day rollover that `parse_sar`'s
  `Average:` and 12-hour-stamp handling has never been exercised across.

## D. `unobserved_total` is a bracket, not a total (round 394 item 3)

- **P14 — `continuity` currently reports `unobserved_total` in the 0h05m–0h20m
  band** (0h29m20s at r388, 0h12m00s at r394 after a rescan *tightened* it).
  It should also GROW by roughly the new gap once this round's ~4h of silence
  is added and before any journal rescan bounds it.
- **P15 — no field in `reachability_check.py`'s continuity output currently
  states the journal coverage that `unobserved_total` is conditioned on**, so
  the two published figures (0h29m20s, 0h12m00s) are not comparable as a
  series. I intend to fix this by EMITTING the coverage alongside rather than
  renaming, so the three rounds of published figures keep their meaning
  (round 334's item 5 precedent).

## E. Standing state — EIGHTEENTH check of round 304's item 2

- **P16 — all six unchanged**: `--cap 256` live in the running command line;
  E3 patch NOT applied (0 markers, mtime 2026-08-23T15:27:33Z, 130,631 B);
  OLMoE tarball 7,420,160,000 B; `memory.events max` 0; no operator login
  since 2026-08-26 19:24; both user units `active`.
- **P17 — `--cap` recommendation is still 196 and the band still [129, 204]**
  after re-running `expert_cache recommend` against whatever this round
  measures — because P4 says the inputs did not move.

## F. Hygiene, banked as a commitment not a guess

- **P18 — no engine request of any kind; port 8001 never contacted; no unit
  restarted; no write outside `~/nuc-research/**`, `/work/logs/**`, `/tmp/**`.**
  Round 394 showed the temptation is real: a measured decay curve invites a
  third request. Round 394's own arithmetic says request 3 costs ~870 slots
  against 456 of headroom (1.906x), so it stays unsent.

## G. Repo-side, offline

- **P19 — `nuc/tests` is 551 green before my changes.**
- **P20 — constant audit is 20 constants / 15 derived / 0.750 / 0 transform
  risks** before my changes. If a new constant of mine trips it, I fix my
  module, not the audit.
- **P21 — `nuc/run_checks_fast.sh` is still not referenced by
  `run_driver.sh`** (0 references) — harness(A)'s file, third consecutive
  round carried.
- **P22 — `languages/whence/SECURITY.md` is still dirty with the identical
  30-insertion / 7-deletion diff.** No round count is attached to this claim;
  round 394 withdrew that tally as unverifiable and I am not reinstating it.
- **P23 — round 394 left NO addendum in `state/nuc-missions.md`.** The last
  heading in that file is round 388's. This is round 334's item 6 recurring:
  the file's per-round narrative has a hole for every round whose findings
  went only to `knowledge/`.
