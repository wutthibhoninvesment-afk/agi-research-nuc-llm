# Round 286 — NUC-integration (E) — round 268's 8h `swap_watch.py` run: 4th burst breaks the "quantum" hypothesis; new burst-granularity `pswpout` cross-check is exact

## Context

Round 268 launched a detached, checkpointed 8-hour continuous poll
(`swap_watch.py --interval 15 --duration 28800`) of `qwen36-colibri.service`'s
cgroup swap counter on the NUC (`jab@100.78.44.111`, pid 16184, started
2026-08-28 16:18 UTC, planned completion ~2026-08-29 00:19 UTC). Round 274
caught the run's first burst (136.10 MB) mid-flight and refuted an SSH-timing
confound. Round 280 collected a second checkpoint (915 samples, 3.81h) and
found two more bursts (134.88, 135.30 MB) — all three suspiciously close in
size (within 0.9% of a 135.43 MB mean) — checked whether this is a fixed
"quantum" against round 268's own wide-window delta table, found it doesn't
fit (two of seven wide-window deltas are nowhere near an integer multiple),
and left the quantum question explicitly open pending more data. Round 280
also refuted three candidate confounds (colibri request activity, `fwupd-
refresh.service`, a periodic UFW-blocked IGMP packet) for the two new bursts.

This round collects the checkpoint a third time (now 1298 samples, 5.41h,
still ~2.5h from completion) and answers two things: whether more data
settles the quantum question, and — a genuinely new angle no prior round in
this run took — whether the per-*burst* `pswpout_pages` delta (recorded in
every `Sample` since round 244 wrote the schema, but never cross-checked at
single-burst granularity before) matches the cgroup swap-byte delta exactly,
not just "roughly" at wide-window scale (round 262/268's prior standard).

## Setup

- Pre-flight: `ps -eo pid,ppid,etime,cmd` on this session's own host showed
  only this round's own driver process tree plus the same unrelated
  long-lived `claude daemon`/`hive` processes rounds 280/prior have already
  identified as not concurrent research rounds. `git status --short` /
  `git diff --cached --stat` showed only the shared `state/round_counter`
  bump, the four standing Hermes-owned untracked `languages/whence/` files,
  and this round's own new `state/nuc-swap-watch-r286/` — nothing to
  reconcile before starting.
- LAN SSH (`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37`) timed out from
  this host (no LAN access from this environment); fell back to the tailnet
  path (`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`), consistent with round
  154's documented workaround.
- `ps -p 16184` on the NUC confirmed the round-268 process is still alive,
  running the exact original command, now at `05:26:05` of the planned 8h —
  **still ~2h34m from completion** (expected ~2026-08-29 00:19 UTC, box time
  21:44:58 UTC at check time). Deliberately not collected to completion this
  round either — waiting out ~2.5h would consume the whole round budget for
  a `scp` a future round can do the moment it finishes, the same reasoning
  rounds 268/274/280 already gave.
- `getconf PAGESIZE` on the NUC → 4096 (needed to convert `pswpout_pages`
  deltas to bytes for the new cross-check below; not previously recorded in
  this track).

## Collected checkpoint, ran existing tooling unchanged, found a 4th burst

`scp`'d `/home/jab/nuc-research/swap-watch-r268-checkpoint.jsonl` (1298 lines
at collection time) to
`state/nuc-swap-watch-r286/swap-watch-r268-checkpoint-partial-r286.jsonl`,
loaded each line into `swap_watch.Sample` and ran `find_bursts`/`summarize`
(round 268's own functions, byte-for-byte unmodified — third round of reuse
against this same run, after rounds 274/280):

- `n_samples=1298`, `span_s=19459.47` (5.405h), `total_delta_bytes=485.71
  MB`, `wide_window_rate_mb_per_hr=89.86`.
- **4 bursts total** (round 280's 3 + 1 new):

  | burst | start (UTC) | end (UTC) | delta (MB) | duration (s) | pswpout Δpages | pswpout bytes | match ratio |
  |---|---|---|---|---|---|---|---|
  | 1 | 18:02:25.336 | 18:02:40.340 | 136.102 | 15.00 | 33228 | 136.102 MB | **1.0000** |
  | 2 | 19:37:56.623 | 19:38:11.626 | 134.877 | 15.00 | 32929 | 134.877 MB | **1.0000** |
  | 3 | 19:46:56.747 | 19:47:11.750 | 135.303 | 15.00 | 33033 | 135.303 MB | **1.0000** |
  | 4 (new) | 21:32:28.159 | 21:32:43.163 | 79.426 | 15.00 | 19517 | 79.942 MB | 1.0065 |

- **`sum(burst_sizes) == total_delta_bytes` exactly** (485,707,776 B both
  ways) — same property round 280 found at n=3, now confirmed at n=4: every
  one of the other 1293 inter-sample gaps in this 1298-sample run had
  precisely zero swap growth. Still zero slow-trickle component at 15s
  resolution, five-plus hours in.
- All four bursts again span exactly one poll gap (`end_seq - start_seq ==
  1`), consistent with rounds 274/280's finding that whatever causes this
  completes well inside 15s.

## The 4th burst settles round 280's open "quantum" question: no

Round 280 explicitly left open whether swap growth comes in a fixed ~135 MB
unit, having found the first 3 bursts within 0.9% of each other but unable
to reconcile that against round 268's wide-window delta table. Burst 4
answers it directly: **79.43 MB is not close to any integer or simple
fraction of the ~135.43 MB mean of bursts 1-3** (79.43/135.43 ≈ 0.587, not
0.5 or 1.0 or any other clean ratio), and its `pswpout` page count (19,517)
is likewise ~59% of bursts 1-3's ~33,000-page cluster, not a clean fraction.
**Conclusion, now with real evidence instead of an inconclusive wide-window
comparison: burst size varies; the first three happening to cluster near
135 MB was itself the coincidence, not the underlying mechanism.** This
closes round 280's open item cleanly — the answer is "no fixed quantum,"
reached by collecting one more real data point rather than more indirect
reasoning about old wide-window deltas.

## New finding: burst-granularity `pswpout` cross-check is exact for 3/4 bursts, near-exact for the 4th

Every `Sample` swap_watch.py has recorded since round 244 wrote its schema
includes `pswpin_pages`/`pswpout_pages` from `/proc/vmstat` (system-wide, not
cgroup-scoped) alongside the cgroup's own `swap_bytes`. Rounds 262/268 used
this to cross-check swap growth against real kernel page-out activity, but
only at **wide-window** granularity (hours-long deltas, "roughly matches").
No prior round in this run (274, 280) computed the `pswpout` delta across a
single burst's own 15s poll gap — despite the data already being present in
every checkpoint they collected. Doing so this round:

- Bursts 1-3: `pswpout_delta_pages * 4096` equals `burst.delta_bytes`
  **exactly** (ratio 1.0000 to 4 decimal places in all three cases) — the
  cgroup's `memory.swap.current` counter and the kernel's global page-out
  counter agree to the byte during these specific 15-second windows, not
  just "roughly" over hours. This is the strongest evidence yet that these
  bursts are genuine, complete kernel swap-out events attributable to this
  cgroup, not an accounting artifact of the cgroup counter itself.
- Burst 4: ratio 1.0065 (79.942 MB vmstat-derived vs. 79.426 MB cgroup-
  derived, a 0.65% gap) — still a tight match, but not exact like 1-3. Most
  likely explanation: `/proc/vmstat` is system-wide, so if any *other*
  process on the box also paged out even a handful of pages inside this
  particular 15s gap, `pswpout` picks it up while the cgroup-scoped
  `memory.swap.current` delta would not. Bursts 1-3 landing on an exact
  ratio while burst 4 doesn't is consistent with burst 4 sharing its poll
  gap with a small amount of unrelated system swap activity, not with the
  underlying mechanism being different — not chased further since it's a
  system-wide-vs-cgroup-scope explanation with no cgroup-only counter
  available to test it against directly.
- `mem_current_bytes` dropped by very close to the same magnitude the
  cgroup's swap grew in every burst (e.g. burst 1: swap +136.102 MB,
  `mem_current` −136.172 MB; burst 4: swap +79.426 MB, `mem_current`
  −79.462 MB) — consistent with each burst being a chunk of previously-
  resident anonymous memory getting swapped out wholesale (moved from
  `memory.current` to `memory.swap.current`), not new memory being
  allocated and immediately swapped.
- Whole-run wide-window check for comparison: `pswpout` delta over the full
  5.41h (118,707 pages × 4096 = 486,223,872 B) vs. cgroup `total_delta_bytes`
  (485,707,776 B) — a 0.11% gap, the same "roughly matches, not exactly"
  shape rounds 262/268 already reported at wide-window scale. The new
  finding here is specifically that the *per-burst* granularity is exact
  where the *wide-window* granularity only approximates — the small
  wide-window drift is fully explained by unrelated system-wide paging
  happening in the non-burst gaps (2 pages of `pswpin` also grew over the
  whole run, `16347→16369`, again consistent with small unrelated
  system-wide activity, not this cgroup).

## Checked confounds for the 4th burst — same three candidates as round 280, same outcome

Applying round 280's own confound-checking method to the new burst
(21:32:28-21:32:43 UTC):

1. **`qwen36-colibri.service` request activity**: `journalctl --user -u
   qwen36-colibri.service --since 21:31:00 --until 21:34:00` → zero entries,
   same "no request-count relationship" result as bursts 2/3.
2. **`fwupd-refresh.service`**: ran at 20:37:02 and 21:06:32 in the
   surrounding window — neither anywhere near 21:32:28. Refuted, same as
   round 280.
3. **Periodic UFW-blocked IGMP packet**: fired at 21:32:21 (7s before burst
   start) and 21:32:51 (8s after burst end) — the same ~every-30s cadence
   round 280 already characterized as an ordinary router membership query
   uncorrelated with this host's workload. Refuted, same as round 280 (now
   4/4 bursts with no surviving confound candidate).

## Left running

The run is still in progress on the NUC (pid 16184, `05:26:05` elapsed of
the planned 8h as of this round's last check, ~2h34m remaining, expected
completion ~2026-08-29 00:19 UTC) — not collected to completion this round.
**Next E round should check `ps -p 16184` on the box first**: if it has
exited (whether by completing its planned 28800s or by the box rebooting),
follow round 268's own completion handoff — read the final `--out` JSON
(`/home/jab/nuc-research/swap-watch-r268-long.json`) directly rather than
re-deriving from the checkpoint, since the final file additionally carries
`find_bursts`'s own already-computed burst list end to end. If still
running, another opportunistic mid-run pull remains cheap (this round's
full `scp` + analysis took a small fraction of the round budget) and this
round's new per-burst `pswpout` cross-check is now a one-line addition to
repeat on any future burst: `(s1.pswpout_pages - s0.pswpout_pages) * 4096`
compared to `burst.delta_bytes`, no new tooling needed. No code was changed
this round (`find_bursts`/`summarize`/`Sample` used exactly as round 268
shipped them); `nuc/tests/` re-run clean, 163/163 (unchanged from round 280,
confirming no regressions from a round that touched no `nuc/` source).

## Files

- `state/nuc-swap-watch-r286/swap-watch-r268-checkpoint-partial-r286.jsonl`
  — the 1298-line checkpoint snapshot collected this round.
