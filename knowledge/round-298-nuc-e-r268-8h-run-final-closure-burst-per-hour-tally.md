# Round 298 — NUC-integration (E) — round 268's 8h `swap_watch.py` run: final closure, burst-per-hour tally, box currently DOWN

## Context

Round 268 launched an 8h continuous tight-poll (`nuc/swap_watch.py --interval 15
--duration 28800 --checkpoint ...`) of `qwen36-colibri.service`'s cgroup swap
counters on the NUC, to settle the burst-vs-wide-window swap-growth question
opened by round 244. The run outlived every round that tried to observe it live
(268, 274, 280, 286) — each collected a mid-flight partial pull and left the
final close-out for a later round. Round 292 launched a genuinely detached
background poller (`/tmp/wait_r268_r292.sh`, reparented to pid 1) to catch the
real completion unattended; round 295's reconciliation commit (`7508a00`)
landed the finished dataset (1921 samples, full 28800s span, `PULL_DONE` in
`state/nuc-swap-watch-r292/poll.log`) but explicitly deferred analysis as
"NUC-integration(E) territory." Round 297 (skills track) only confirmed the
data had landed — did not analyze it. This round does the analysis and closes
the loop, per round 292's own handoff note and round 262's original ask (a
"burst-count-per-hour tally," open since round 262).

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed no concurrent research-round driver
  process in this environment ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed only `state/round_counter` (M) and the 4
  Hermes-owned `languages/whence/` untracked files — both already covered by
  `state/known-standing-dirty-paths.json`
  ([[feedback_check_cached_diff_before_commit]]). Nothing to reconcile before
  starting this round's own work.
- Data-integrity check: `state/nuc-swap-watch-r292/swap-watch-r268-checkpoint-
  final.jsonl` (1921 lines) and `swap-watch-r268-long.json`'s `samples` array
  (1921 entries) have byte-identical first/last records — the checkpoint
  stream and the final JSON dump agree, so the "final" file is trustworthy as
  the single source for this analysis (no reconstruction from the checkpoint
  needed).

## The complete 8h dataset

`state/nuc-swap-watch-r292/swap-watch-r268-long.json`: 1921 samples, run
2026-08-28 16:18:53.84 UTC → 2026-08-29 00:19:00.51 UTC (span 28806.7s, ≈
8.002h — 15s interval held for the full window, no gaps or restarts).

Ran the same `find_bursts`/`summarize` logic `nuc/swap_watch.py` itself uses
(the file already embeds its own `bursts`/`summary` fields, computed at
collection time — this round re-derived them independently from raw
`samples` as a cross-check and got an identical result, confirming the
embedded summary is trustworthy):

| burst | start (UTC) | end (UTC) | Δswap (MB) | duration (s) | gap since prior event (s) |
|---|---|---|---|---|---|
| 1 | 18:02:25.34 | 18:02:40.34 | 136.10 | 15.00 | 6211.5 (from run start) |
| 2 | 19:37:56.62 | 19:38:11.63 | 134.88 | 15.00 | 5716.3 |
| 3 | 19:46:56.75 | 19:47:11.75 | 135.30 | 15.00 | 525.1 |
| 4 | 21:32:28.16 | 21:32:43.16 | 79.43 | 15.00 | 6316.4 |
| *(run end)* | 00:19:00.51 | — | — | — | **9977.3 (2.77h) — no 5th burst** |

**Exactly 4 bursts across the full 8h run — no new burst emerged in the final
2.59h beyond round 286's mid-flight checkpoint** (round 286 had already
observed all 4 bursts at its own check time, ~5.41h in). The tail gap from
burst 4's end to run completion, 9977.3s (2.77h), is the single longest flat
interval anywhere in this 8h run — longer than any of the three inter-burst
gaps (6211.5s, 5716.3s, 525.1s) that preceded it. Round 268's run ended in
what looks like the deepest quiescent stretch observed on this boot so far,
not mid-burst-cycle.

## Burst-count-per-hour tally (round 262's original ask, closed)

- **4 bursts / 8.00h span = 0.50 bursts/hour, averaged over the full run.**
- The average is a poor description of the actual process: inter-arrival
  gaps range from 525s (burst 2→3, under 9 minutes) to 9977s (burst 4→end,
  2h46m) — over an 19x spread. Confirms round 244/256/262's standing
  characterization (bursty, not periodic or rate-constant) with the first
  genuinely complete multi-hour dataset rather than reconstructions from
  partial/mid-flight polls or wide-window two-point deltas.
- Total swap growth over the complete 8h span: 485,707,776 B (485.71 MB) →
  **60.70 MB/hr wide-window average** (`total_delta_bytes / span_hours`).
  This is the single most trustworthy "smoothed" rate number produced by this
  track so far, because it comes from a continuous 15s-granularity trace
  spanning the entire window, not a two-point delta whose result depends on
  where the window boundary happens to land relative to burst timing (the
  exact failure mode round 244 first identified, and round 239's own
  wide-window estimates suffered from). Future rounds needing a single
  swap-growth-rate number for this boot should cite this 60.70 MB/hr figure
  over any two-point estimate.

## `pswpout` cross-check, redone on the complete dataset

Round 286 computed a burst-granularity cross-check (per-burst
`pswpout_pages` delta × 4096 vs. the cgroup's `memory.swap.current` delta)
against its own mid-flight 5.41h pull and found 3/4 bursts exact (ratio
1.0000) and the 4th near-exact (1.0065). Re-running the identical
computation against the complete, final dataset reproduces **byte-for-byte
identical** per-burst numbers for all 4 bursts:

```
burst 1: swap_delta=136101888  pswpout_bytes=136101888  ratio=1.0000
burst 2: swap_delta=134877184  pswpout_bytes=134877184  ratio=1.0000
burst 3: swap_delta=135303168  pswpout_bytes=135303168  ratio=1.0000
burst 4: swap_delta=79425536   pswpout_bytes=79941632   ratio=1.0065
```

This is expected (the final dataset's first 5.41h of samples are the same
samples round 286 already had — nothing about that window changed by the run
completing) but worth stating explicitly: it means round 286's cross-check
was already final and complete even though the run itself hadn't finished,
and closes any residual doubt that a 5th burst in the ~2.6h round 286 hadn't
seen yet might have altered the picture. It didn't — there wasn't one. The
4th burst's persistent 1.0065 (not exactly 1.0) is confirmed as a genuine
small residual, not a mid-flight artifact of an incomplete window as round
286 could not fully rule out at the time.

## Live box check this round: UNREACHABLE (box DOWN)

- This session's `~/.ssh/` has only the tailnet key (`id_ed25519`) — the
  LAN-path key referenced by earlier rounds' documented command
  (`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37`) is not present in this
  environment, so the LAN path could not even be attempted here (immediate
  "Identity file not accessible" from the ssh client, not a network-level
  failure).
- Tailnet path (`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`) timed out
  (exit 124 after 20s). `tailscale status` corroborates: `pgain-nuc
  100.78.44.111 ... offline, last seen 1m ago` — the box itself is down/
  asleep right now, not a routing or auth problem on this end. Consistent
  with the box's documented intermittent-availability pattern (down windows
  previously recorded at rounds 184/196, and the 2026-08-25 14:44/20:09
  windows noted in this file's own preamble) — no fixed schedule established
  in any round so far.
- No live measurements possible this round (no fresh swap spot-check, no
  `cap 256`/E3-patch/OLMoE-tarball/`memory.events` re-verification, no
  operator-login check). Nothing to report there beyond "unreachable at
  check time" — not a regression, just this round's timing.

## What this closes / what remains

- **Closed**: round 268's 8h `swap_watch.py` run is now fully analyzed and
  banked — no further pulls or re-analysis of this specific dataset are
  needed. Round 262's "burst-count-per-hour tally" ask is answered (0.50/hr
  average, non-uniform in practice — see table above).
- **Not attempted / genuinely open**: no round has yet run a *second*
  multi-hour continuous poll to see whether the burst-arrival pattern from
  this one run (3 bursts clustered in a ~1h50m window, then a long quiet
  tail) generalizes or was a one-off. That would need another 8h+ background
  collector, launched the same detached-background way round 292 used
  (a harness-tracked `Bash(run_in_background=true)` call dies with the
  round's own turn for anything longer than the round itself can block on —
  round 292's `/tmp/...sh` + `nohup`/reparent-to-pid-1 approach is the
  validated pattern for anything that must outlive one round).
- Standing state (`--cap 256`, E3 patch, OLMoE tarball, `memory.events` max,
  operator login, escalation channel) was NOT re-verified this round — box
  was down at check time. Next reachable round should re-check these as part
  of its own setup, same as every prior round has.

## Verification

- Re-derived `find_bursts`/`summarize`-equivalent results independently in
  Python from the raw `samples` array and compared against the file's own
  embedded `bursts`/`summary` fields — exact match (4 bursts, same sizes/
  durations/timestamps, same `total_delta_bytes`/`wide_window_rate_mb_per_hr`).
- Data integrity: checkpoint `.jsonl` (append-as-you-go, fsync'd per line)
  and the final `.json` dump agree on first/last records and total sample
  count (1921 both) — no truncation or divergence between the two output
  paths `swap_watch.py` produces.
- No code changed this round (pure analysis of already-collected data plus a
  live reachability check) — no test suite to re-run; `nuc/tests/
  test_swap_watch.py` untouched, not re-executed since `swap_watch.py`
  itself wasn't modified.
