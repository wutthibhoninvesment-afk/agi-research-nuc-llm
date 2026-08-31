# Round 406 (NUC-integration E) — predictions, written BEFORE measuring

Banking rule **D-013**. Box state at round start: **DOWN**. `tailscale status`
says `pgain-nuc` offline, last seen `2026-08-31T16:30:00.1Z`; a real ssh probe
to `jab@100.78.44.111` timed out (rc 255). Two consecutive ssh failures, so no
further probing this round — CLAUDE.md's rule.

Everything below is therefore answered from data **already in git**:
`state/nuc-capture-r400/` (14 files, committed by round 400) plus the tools in
`nuc/`. Nothing here requires the box.

## What I am testing

Round 400's handoff item 3: *"prove or drop the fwupd attribution — now the
only sole-attributable event in the boot"*. Round 400 reported a whole-boot
ledger of 62 named fires, 6 in a costly bucket, **1 sole-attributable:
`fwupd-refresh` at 01:57:33Z on sa31**, and round 394 before it attributed a
67.7 MB step to the same unit. `sole_attributable` is `cost_ledger`'s only
flag that licenses the sentence "unit X cost this".

My hypothesis going in: **`sole_attributable` has no base rate attached to
it.** It says one named unit started in a costly bucket. It does not say that
unit is unusual, and if the unit fires often enough, landing in a costly
bucket once is what chance looks like.

## Predictions

| # | Prediction | Basis |
|---|---|---|
| P1 | `fwupd-refresh.service` fires **≥ 10 times** on 2026-08-31 in the banked journal window (00:00–13:16Z) | eyeballed 17 `Starting fwupd-refresh` lines on 2026-08-30 before looking at 08-31 |
| P2 | fwupd-refresh is the **most frequently firing** non-excluded unit in the sa31 ledger | it looked roughly hourly on 08-30 |
| P3 | Its `in_costly_bucket` count is exactly **1** — the same 02:00:05 bucket round 400 named | round 400 reported one sole-attributable fire |
| P4 | Under a uniform-chance null (a unit firing n times into the day's buckets, k of which are costly), P(≥1 costly bucket) for fwupd's n is **> 0.15** — i.e. one hit is NOT evidence | if n≈15 and k≈2 of ~79 buckets, 1-(1-k/N)^n ≈ 0.32 |
| P5 | Therefore the correct verdict on item 3 is **DROP**, not prove | follows from P4 |
| P6 | fwupd-refresh's firing pattern is **irregular** (gaps varying by more than 2x), not a fixed `OnCalendar` cadence | the 08-30 timestamps were :39,:53,:13,:11,:28,:42,:13 — no cadence |
| P7 | The banked journal holds **0** `Finished <unit>.service` lines, so oneshot RUN DURATIONS are absent | measured already: 0 Finished lines |
| P8 | Consequently the obvious stronger test — attribute by the interval a unit RAN, not the instant it STARTED — **cannot be run from banked data at all**, and needs a box that is currently down | follows from P7 |
| P9 | Re-running `cost_ledger` on the banked sa31 capture reproduces round 400's headline numbers exactly (62 fires whole-boot; sa31's share of the 6 costly / 1 sole) | the tool and its input are both in git |
| P10 | `sar` activity types banked for all nine days: exactly **2** (`-r`, `-W`); `-B` for **2** days only; **≥ 8** further types (`-u -b -q -d -n -S -w -y -H`) banked for **0** days | measured the section markers already |
| P11 | The number of distinct 10-minute buckets in the banked sa31 `-W` table is **< 84** (a full day is 144) because the capture stopped at 13:16 | capture end time |
| P12 | At least one costly bucket on sa31 has **no named fire at all** (`costly_buckets_without_a_named_fire` non-empty) | round 400 found 6 fires in costly buckets across 2 days but reported bucket counts separately |

## What I will build regardless of how the above scores

1. A base-rate test that any future `sole_attributable` claim has to pass, in
   `nuc/perturbation.py`, with tests — so the next round cannot repeat the
   error by hand.
2. A capture-fidelity audit: what round 400 actually banked vs what only ever
   existed on the box, so "we have the sysstat archive" is a checked claim.
3. Whatever the next up-round needs to capture in ONE command, given P7/P8.

## Honest scoring

Every prediction above gets HIT / MISS / PARTIAL in the round file, including
the ones that make this round's work look unnecessary.
