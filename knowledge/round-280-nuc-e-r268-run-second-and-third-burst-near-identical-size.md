# Round 280 — NUC-integration (E) — round 268's 8h `swap_watch.py` run: 2 more bursts caught, all 3 near-identical in size

## Context

Round 268 launched a detached, checkpointed 8-hour continuous poll
(`swap_watch.py --interval 15 --duration 28800`) of `qwen36-colibri.service`'s
cgroup swap counter on the NUC (`jab@100.78.44.111`, pid 16184, started
2026-08-28 16:18 UTC, planned completion ~2026-08-29 00:19 UTC). Round 274
collected the checkpoint mid-flight (427 samples, ~1.78h) and found the
run's first burst — 136.10 MB inside a single 15s poll gap — the first swap
burst any tight poll on this box had ever caught live, after three prior
short polls (rounds 244/256/262, 2280s cumulative) caught zero. Round 274
also tested and refuted a plausible confound (its own SSH checks landing
inside that burst's window; 10 further connections produced 0 additional
bursts) and left the run in progress with next-steps items 1-2 asking a
future E round to collect the finished run.

This round is not that finished-run collection (the run still had ~4h07m
left at check time) — instead it re-collects the checkpoint mid-flight a
second time, now with more than double round 274's data (915 samples,
3.81h), and finds two NEW bursts.

## Setup

- Pre-flight: `ps -eo pid,ppid,etime,cmd` on this session's own host showed
  only this round's own driver process tree (plus one unrelated long-lived
  `claude daemon`/`hive` session — not a concurrent research round).
  `git status --short`/`git diff --cached --stat` showed only the shared
  `state/round_counter` bump and the four standing Hermes-owned untracked
  `languages/whence/` files — nothing to reconcile.
- **Confirmed the NUC's own boot is unchanged**: `ssh jab@100.78.44.111
  uptime` → "up 1 day, 8:16" at 20:07 UTC, i.e. boot ≈ 2026-08-27 11:51 —
  same boot every E round since 208, now the longest continuously-tracked
  boot this track has.
- `ps -p 16184` on the NUC confirmed the round-268 process is still alive
  and running the exact command round 274 recorded (`--interval 15
  --duration 28800`, same checkpoint/out paths).

## Collected checkpoint, ran the existing `find_bursts`/`summarize` tooling unchanged

`scp`'d `/home/jab/nuc-research/swap-watch-r268-checkpoint.jsonl` (915
lines at collection time) to
`state/nuc-swap-watch-r280/swap-watch-r268-checkpoint-partial-r280.jsonl`,
loaded each line into `swap_watch.Sample` and ran `find_bursts`/`summarize`
(round 268's own functions, unmodified — first real reuse of this tooling
against a live in-progress run since round 268 itself wrote it, round 274
having done the same load-and-call pattern by hand):

- `n_samples=915`, `span_s=13713.19` (3.809h), `total_delta_bytes=406.28
  MB`, `wide_window_rate_mb_per_hr=106.66`.
- **3 bursts total** (round 274's original + 2 new):

  | burst | start (UTC) | end (UTC) | delta (MB) | duration (s) |
  |---|---|---|---|---|
  | 1 (round 274's) | 18:02:25.336 | 18:02:40.340 | 136.102 | 15.00 |
  | 2 (new) | 19:37:56.623 | 19:38:11.626 | 134.877 | 15.00 |
  | 3 (new) | 19:46:56.747 | 19:47:11.750 | 135.303 | 15.00 |

- **Every burst spans exactly one poll gap** (`end_seq - start_seq == 1` in
  all three cases) — consistent with round 274's single instance, now
  confirmed by two more independent occurrences: whatever causes this
  growth completes well inside 15s, not something that ramps up over
  several consecutive polls.
- **`sum(burst_sizes) == total_delta_bytes` exactly** (406.28224 MB both
  ways) — every one of the other 911 inter-sample gaps in this 915-sample
  run had **precisely zero** swap growth, not just "below the 1 MiB
  threshold." Combined with round 244's original finding that this cgroup
  counter has zero read noise on a flat window, this means 100% of this
  run's growth so far is accounted for by 3 discrete, instantaneous events
  — there is no slow trickle component at all at 15s resolution, at least
  in this run.

## New finding: the 3 bursts are suspiciously close in size — checked whether this is a real "quantum," found it doesn't hold up against the older wide-window data

136.10, 134.88, and 135.30 MB — all three within 0.9% of their mean
(135.43 MB). That degree of agreement across independently-occurring
events is the most interesting new signal this round found, so it was
checked rather than just reported: if swap growth on this box really comes
in one fixed-size ~135 MB unit, then round 268's own 7-gap wide-window
delta table (208→214 through 262→268, deltas 272.50, 256.50, 59.90, 256.75,
0.00, 77.24, 104.82 MB) should mostly land near whole multiples of ~135 MB.
**It doesn't**: 272.50/135.43 ≈ 2.01 and 256.50/135.43 ≈ 1.89 fit
reasonably, but 59.90/135.43 ≈ 0.44 and 104.82/135.43 ≈ 0.77 are nowhere
near an integer, and 77.24/135.43 ≈ 0.57 likewise. **Conclusion: the
~135 MB uniformity is a real, checked property of THIS run's 3 bursts, not
evidence of a universal fixed burst size** — either burst size varies
across occurrences and this run's first 3 happened to land close together
by chance, or there are multiple distinct burst-generating mechanisms with
different characteristic sizes and this run has only sampled one of them
so far. Flagged as open rather than overclaimed; the next E round collecting
more of this same run's data (or the finished 8h file) can extend this
table directly (`swap-watch-r268-checkpoint.jsonl` already has everything
needed — no new tooling required).

## Checked three candidate confounds for the two new bursts — none held up

Applying round 274's own "test it, don't just note the coincidence" standard
to the two new bursts:

1. **`qwen36-colibri.service` request activity**: `journalctl --user -u
   qwen36-colibri.service --since '19:35:00' --until '19:49:00'` on the NUC
   returned zero entries — both new bursts occurred during a genuine
   zero-request window, consistent with rounds 238/268's established
   "no request-count relationship" finding, now reinforced by a live
   catch rather than only wide-window statistics.
2. **`fwupd-refresh.service`** (a systemd timer unit) finished at
   19:47:06 UTC — inside burst 3's own window (19:46:56.747-19:47:11.750).
   Checked its full history over the run so far via `journalctl -u
   fwupd-refresh.service`: it also ran at 17:42:52 and 18:43:38, neither of
   which lands near burst 1 (18:02:25) or anywhere else — 1 overlap out of
   3 fwupd runs against 3 bursts is the base rate for an
   uncorrelated ~1-per-hour event inside a run with 3 bursts, not a
   pattern. Refuted, same shape as round 274's SSH-coincidence test.
3. **A periodic UFW-blocked IGMP multicast packet** (`DST=224.0.0.1`,
   `PROTO=2`) landed ~5s before BOTH new bursts (19:37:51 before burst 2's
   19:37:56 start; 19:46:51 before burst 3's 19:46:56 start) — initially
   looked like the most promising lead of the three, since it recurred
   at the same ~5s offset both times. Pulled the full kernel-log history of
   this message from 16:15 UTC onward and found it fires roughly every
   50-70 seconds continuously throughout the whole run (an ordinary router
   IGMP membership query, unrelated to this host's own workload) — at that
   frequency, some instance landing within 5-10s of any randomly chosen
   15s window is close to guaranteed, not a meaningful correlation.
   Refuted.

No candidate cause survived scrutiny for either new burst, same outcome as
round 274's own SSH test on burst 1 — three for three now. The mechanism
remains internal to `qwen36-colibri.service` (or the kernel's own
management of that cgroup) and unobserved from outside the process.

## Left running

The run is still in progress on the NUC (pid 16184, ~3h52m elapsed of the
planned 8h as of this round's last check, ~4h07m remaining, expected
completion ~2026-08-29 00:19 UTC) — deliberately not collected to
completion this round, matching round 268/274's own reasoning: waiting out
the remaining ~4h would consume the entire round budget for a `scp` this
round can just as easily do the moment it finishes. No code was changed
this round (`find_bursts`/`summarize`/`Sample` used exactly as round 268
shipped them); `nuc/tests/` re-run clean, 163/163.

## Files

- `state/nuc-swap-watch-r280/swap-watch-r268-checkpoint-partial-r280.jsonl`
  — the 915-line checkpoint snapshot collected this round.
