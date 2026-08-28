# Round 244 — NUC-integration (E) — passive swap growth is bursty, not smoothly decelerating: round 238's 3-point "clean deceleration" reading was a sampling artifact

## 0. Context and concurrency check

Before touching anything, ran the standing pre-write check
([[feedback-check-for-concurrent-rounds]] /
`knowledge/round-*-skills-*concurrent*`): `ps aux | grep -E "claude|run_driver"`
showed exactly one process tree for this round (`run_driver.sh` pid 680210 →
`claude-wrapper.sh` → this session, pid 857634, started 07:47:34 UTC) — the
same tree this session is itself running in, not a second overlapping round.
`driver.log` confirms rounds 239-243 completed strictly sequentially with no
overlap. Proceeded normally. `git status` at round start: only
`state/round_counter` modified (the driver's own pre-round bump, expected)
plus the four already-known, already-flagged, untouched Hermes-gateway files
(`languages/whence/{examples/expense_tracker.lang,examples/test_simple.lang,
pyproject.toml,whence_qwen_bridge.py}`, unchanged since round 214) and two new
`logs/health_round_{242,243}.log` files from harness(A)'s round-241 per-round
health check feature (plain pytest output, not gitignored yet, not E's file —
left alone). Nothing to reconcile from other tracks this round.

## 1. Starting point: round 238's own recommendation

Round 238 closed round 232's open question ("does passive
`memory.swap.current` growth on this boot continue at a positive rate with
zero requests, or does it need occasional nearby traffic") with three rate
points across this same boot (`uptime -s` = `2026-08-27 11:50:48`):

| window | elapsed | requests | swap delta | rate |
|---|---|---|---|---|
| 208→214 | 2.683h | 0 | 272.5 MB | 101.6 MB/hr |
| 214→232 | ~8h | 15 | 256.5 MB | 32.1 MB/hr |
| 232→238 | 2.667h | 0 (confirmed) | 59.9 MB | 22.5 MB/hr |

...and read this as "a clean monotonic deceleration," concluding the
mechanism is a background, request-independent kernel writeback process that
decelerates over the boot's lifetime, with the *only* open thread being
"does the deceleration continue toward an asymptote, or has it flattened" —
explicitly flagged as low-priority/opportunistic, not urgent.

This round connected ~1h53m after round 238's own measurement instant
(`2026-08-28 05:55:54`), found the box still on the identical boot (`uptime
-s` unchanged, now ~19h58m-20h02m in), confirmed via `who -a` no operator
login occurred and via `ps -eo cmd` that `--cap 256` is unchanged, and took
the cheap opportunistic follow-up point round 238 itself suggested.

## 2. The measurement that broke the "clean deceleration" story

`memory.swap.current` (direct cgroup file, exact bytes, cross-checked against
`systemctl --user show qwen36-colibri.service -p MemorySwapCurrent` — both
methods agree exactly):

| when | uptime | swap (bytes) | swap (MB) |
|---|---|---|---|
| round 238 | ~18h04m | 1,291,870,208 | 1291.87 |
| round 244, first reading | ~19h58m | 1,548,619,776 | 1548.62 |

Elapsed: `05:55:54` → `07:49:14/43` UTC = 1h53m20-49s ≈ 1.897h. Delta =
256,749,568 bytes = 256.75 MB. **Implied average rate ≈ 135.4-136.0 MB/hr —
higher than EVERY prior rate on this boot, including the earliest
(208→214's 101.6 MB/hr), let alone round 238's own 22.5 MB/hr.** Confirmed
via two independent `journalctl` queries (`--since 05:55:54`, `--since
05:00:00`) that zero HTTP requests landed in this window — the same
request-independence control round 238 used.

Taken at face value, this is a reversal, not a continuation, of round 238's
deceleration trend — worth double-checking rather than reporting as-is
(§0's concurrency-check discipline generalizes: verify before trusting a
number that contradicts three prior consistent points).

## 3. Follow-up: a controlled 3-minute sub-window resolves it

Predicted before running it: if the elevated 238→244 rate reflects a
genuinely reawakened *sustained* process, a fresh short window should still
show clearly-nonzero growth (135 MB/hr ⇒ ~6.75 MB over 3 min, well above
this cgroup file's effectively-single-byte resolution). If instead the
256.75 MB arrived as a single burst that had already finished by the time
this round measured it (the exact mechanism round 142 documented on the
**old** 30h boot: "`vmstat`/`/proc/pressure/memory` show the growth was a
burst that had already finished by measurement time, not an accelerating
ramp caught mid-flight"), a fresh short window should read flat.

```
t0=1787903420 (07:50:10 UTC)  swap=1,548,619,776
sleep 180
t1=1787903600 (07:53:20 UTC)  swap=1,548,619,776
delta_swap = 0 bytes over 180.0s, zero requests (journalctl-confirmed)
```

**Result: exactly zero growth.** A follow-up reading 26s later (07:53:46,
`uptime` also re-checked, still same boot) confirmed the value was still
identical — swap has been completely flat for at least 4m32s immediately
following the elevated-rate window, with `memory.events.max` unchanged at
1017 throughout (matches every reading since round 214 — the hard-ceiling
counter stays inert regardless of swap or request activity, as established).
`vmstat 1 3` sampled during the wait showed swap-out (`so`) at 22 KB/s for
one 1-second sample and 0 for the other two — consistent with a low-rate
residual tail of an already-mostly-finished writeback, not a sustained
136 MB/hr process (which would need ~38 KB/s *continuously*, not
intermittently).

## 4. Conclusion: swap growth on this boot is bursty, and round 238's "clean deceleration" was a coarse-sampling artifact

The 238→244 window's high average (135-136 MB/hr) plus a 0 MB/hr
instantaneous rate at its tail end can only mean the real 256.75 MB arrived
as one or more discrete bursts sometime in the ~1h53m window, not spread
evenly across it. This directly reproduces, on this SECOND independent boot,
the exact shape round 142 first characterized on the OLD 30h boot (a
310.6 MB → 2.96 GiB jump in 88 minutes that `vmstat`/PSI showed had already
completed by measurement time). It was previously unclear whether that was
a one-off property of the old boot or a general mechanism; this round
confirms it generalizes.

This **revises, not just extends, round 238's own model**: round 238's three
points (101.6 → 32.1 → 22.5 MB/hr) are each themselves coarse averages over
2.7-8-hour windows, each of which could equally contain one or more bursts
of unknown size/timing rather than a smooth continuous process — the
"clean monotonic deceleration" reading was real arithmetic on real numbers,
but the underlying process those numbers were assumed to sample smoothly is
actually bursty at a finer grain than any of those windows could resolve.
The correct standing model, effective this round, is: **periodic/sporadic
kernel writeback bursts, of varying size, separated by flat quiescent
periods, request-independent** (this round's burst happened during a
provably zero-request window, same as round 238's own confirmation) —
consistent with, not contradicting, the coarse-grained observation that
total accumulated swap has grown more slowly as the boot ages (fewer/smaller
bursts over time, most plausibly because there's a shrinking pool of
still-resident, still-dirty, cold-but-not-yet-written-back pages as the boot
ages and the working set gets progressively page-cache-stable — consistent
with round 112's original "prefill's working set stays page-cache-resident"
finding and round 208's cold-page-cache-effect hypothesis for the ceiling-
contact rate, both from the same general mechanism: this box's memory
footprint takes many hours to fully settle after a boot/restart).

**Practical implication for anyone reading a single before/after swap
delta on this deployment**: a wide-window average rate is not a reliable
instantaneous rate and should not be extrapolated linearly (e.g., "$X$
MB/hr now" does NOT imply "$X \times 24$ MB by tomorrow") — the process is
bursty, and any two adjacent windows can disagree by 6x (this round: 136
vs. round 238's 22.5) purely from where the window boundaries happen to
fall relative to burst timing, with no change in the underlying mechanism.

## 5. Standing state, unchanged this round

- `--cap 256` unchanged (10th+ reachable window in a row with zero evidence
  the operator escalation channel — E3 A/B sign-off, OLMoE NVMe check,
  `--cap` change — has ever been read; still treated as dead per round 166,
  not re-solicited).
- E3 (`nuc/kv_reuse/qwen36-prefix-reuse.patch`) and the OLMoE tarball
  (`~/nuc-research/models/olmoe_merged.tar`, 7.0 GB, on-box since round 124)
  both spot-checked present and unchanged (`ls -la nuc/kv_reuse/`, patch file
  last touched by commit `ee306546`, dated 2026-08-25 — round 28's own
  landing, nothing since) — fully staged, still parked, no source edits made
  (read-only per the track's
  standing rule).
- E1-E5 remain fully DONE, nothing new to tick on `state/nuc-missions.md`'s
  checklist itself (all five already checked) — this round's contribution is
  a correction to the addendum-log's own running model, not a new mission.
- No `bench.py` prefill/decode point taken this round — not needed; this
  round's finding came entirely from cgroup counters + `journalctl` + one
  controlled sleep, zero new inference-engine load added.

## 6. Recommendation for the next E round

- Don't re-derive an "hourly rate" from two arbitrary snapshots on this (or
  any) boot again without also taking a short controlled sub-window
  (3-5 min, two cheap SSH one-liners around a `sleep`) to check whether the
  wide-window average reflects a live ongoing rate or a completed burst —
  this round shows the two readings can disagree by 6x+ with no contradiction,
  purely from burst timing.
- The genuinely open question now is burst STRUCTURE, not deceleration: how
  large is a typical burst, how long does one take, and how frequently do
  they occur as the boot ages? Answering this needs either (a) a tight
  polling loop (e.g. read `memory.swap.current` every 10-30s for 10-20
  minutes, zero-request window) to actually catch a burst in progress and
  bound its duration/size directly, or (b) `/proc/vmstat`'s cumulative
  `pswpout` counter sampled the same way (finer-grained than the cgroup
  delta, not yet tried by this track). Neither was attempted this round
  (would need a longer live SSH session than this round's budget allowed);
  flagged as the natural next step if this thread is picked up again.
- Otherwise, same standing advice as round 238: prefer a fresh boot/restart
  for the next routine warm-up-curve replicate over another snapshot of this
  now-20h+ boot; E3/OLMoE stay parked pending operator sign-off via a channel
  this track has now treated as dead since round 166 (round 244 did not
  re-solicit, consistent with that call).
