# Round 370 (NUC-integration E) — PREDICTIONS, written before measuring

House rule **D-013**: predictions first, then measure, then score misses honestly.
Written 2026-08-30 ~14:58 UTC, after the reachability check and the boot-history
capture (both time-sensitive per round 364's handoff item 1) and before any of
the measurements below.

## Already OBSERVED before this file was written (not predictions — recorded so
## the scoring below cannot quietly claim credit for them)
- O1. `check --round 370` -> `verdict: up`, `boot_utc 2026-08-30T00:32:27Z`,
  `source live`, `precision precise`. Box reachable over the tailnet path.
- O2. `journalctl --list-boots -o json` returns the SAME 7 boots with the SAME
  boot_ids as round 364; boot 0 (`43e0c767`) `last_entry` advanced
  1788084251377229 -> 1788101832061199 us (+17580.7 s = 4.88 h). No boot aged
  out of the 3.2 G journal retention between rounds 364 and 370.

## The question this round is trying to close
Round 184 hypothesised that some of this box's reachability gaps are SUSPEND,
not power-off. Round 340's next-step item 2 sharpened it into a soundness
question about our own instrument: `boot_utc` is derived as `now - /proc/uptime`,
and its `reboot_only` classification rests on `/proc/uptime` continuing to count
while the box is suspended. That was read from kernel documentation, never
measured here. Round 364 checked boot 0's kernel log only and left boots -1..-6
explicitly unchecked.

Four independent witnesses, deliberately chosen so that no two share a failure
mode:
- **W1 kernel-log grep**, per boot -6..0: does the box LOG a suspend?
- **W2 silence bound**, computed locally from the round-364 journal-seconds
  cache: how long is the longest interior journal silence per boot? A suspend of
  duration D forces a silence of >= D, so this bounds any suspend the box failed
  to log.
- **W3 clock cross-check**: `boot_utc` (from `/proc/uptime`) vs journald's own
  `first_entry` for the boot that was live at that moment. Two independent
  sources for one wall-clock instant; they diverge exactly when uptime loses
  time.
- **W4 direct kernel accounting**: `CLOCK_BOOTTIME - CLOCK_MONOTONIC` on the
  box IS the kernel's own cumulative-suspend counter for the current boot.

## Predictions

**P1 (W1, kernel-log grep across all 7 boots).** ZERO real suspend/resume
records on every boot. The only matches will be round 364's known false
positive, `PM: hibernation: Registered nosave memory`, at ~7 per boot, which is
boot-time setup on any hibernate-capable machine. I predict `Freezing user
space`, `PM: suspend entry`, `PM: suspend exit` and `systemd-suspend` all return
0 hits on all 7 boots.

**P2 (W2, silence bound from the cache).** Max interior journal silence across
all 7 boots <= 300 s, reproducing round 364's prose figure from the raw cache.
I further predict the single 300 s outlier belongs to the LOWEST-density boot
(-5, 0.037 entries/s) and that the two high-density boots (-1 at 45.5/s, -2 at
58.85/s) have max silence < 130 s.

**P3 (W3, live boot).** `boot_utc` 2026-08-30T00:32:27Z will agree with boot 0's
journald `first_entry` to within 60 s, and boot_utc will be the EARLIER of the
two (the kernel starts counting uptime before journald writes its first record).

**P4 (W3, historical).** EVERY `boot_utc` record in
`state/nuc-reachability-log.jsonl` whose boot is present in the boot-history
table will match that boot's `first_entry` within 120 s. Records predating boot
-6 cannot be checked and I predict there will be some.

**P5 (W4, direct).** `CLOCK_BOOTTIME - CLOCK_MONOTONIC` < 1.0 s on the live box
-> the kernel says ZERO cumulative suspend time in this ~14.4 h boot. And
`/proc/uptime` field 1 will equal CLOCK_BOOTTIME to within 0.05 s, identifying
which clock our instrument actually reads.

**P6 (journal-boots re-run with the warm cache).** 6 of 7 boots skipped from
cache, exactly 1 scanned (boot 0, which is open and has grown). The rescan of
boot 0's full 14.4 h span completes in under 120 s wall. Boot 0's `n_seconds`
grows relative to round 364's capture.

**P7 (continuity after merge).** `unobserved_total` <= 0h25m00s and
`max_unobserved_outage` UNCHANGED at 0h01m57s. Reasoning: the only new wall-clock
since round 364 is 4.88 h inside boot 0, which the rescan covers, so the new
records should add almost nothing unobserved. Per round 364's item 2 this figure
is a SNAPSHOT of a growing append-only log and is only comparable because it is
recomputed by the same method on the same round.

**P8 (standing state, round 304 item 2, thirteenth consecutive boot).** All six
unchanged: `--cap 256` live; E3 prefix-reuse patch still NOT applied (0 markers
in `qwen36.c`); OLMoE tarball still present at 7,420,160,000 B; `memory.events`
`max` still 0; no operator login; both user units `active`. Escalation channel
still dead since round 166.

**P9 (`languages/whence/SECURITY.md`).** Byte-identical to what round 349
escalated — i.e. the Hermes gateway has NOT re-edited it in the 21 rounds since;
this is the same carried diff, not a new one.
