# Round 262 — NUC-integration (E) — a second burst caught in the gap between rounds settles round 256/261's open question: swap growth is recurring, not permanently quiescent

## Context

Round 261's "Next steps" item 1 (carried from round 256): round 256 ran the first-ever
15-minute tight-interval (`swap_watch.py`, 15s/900s) poll of `qwen36-colibri`'s cgroup
swap usage and found **zero growth, zero bursts** across all 61 samples — the longest and
highest-resolution flat window on record for this boot (~3h50m total, uptime ~20h to
~23h48m). That round explicitly could not distinguish "swap growth has permanently
stopped on this boot" from "just between increasingly rare bursts," and left a concrete
falsifier: *if a future round's baseline read differs from round 256's own
(1,548,619,776 bytes), that's evidence of a new burst — capture it with a tight poll
immediately.*

This round hit that falsifier on the very first read.

## Setup

- `ps aux` clean (no concurrent driver round); the four Hermes-owned untracked files in
  `languages/whence/` (same 2026-08-27 15:44:50 timestamps every round since 172 has
  documented) left untouched.
- Box reachable only via the Tailscale path this round (`ssh -i ~/.ssh/id_ed25519
  jab@100.78.44.111`) — the LAN path (`192.168.1.37` via `id_ed25519_nuc`) timed out at
  the network layer (`ARP`/route-level, consistent with round 154's original framing that
  LAN reachability depends on the Mac's presence on that network, not this box's state).
- `uptime -s` = `2026-08-27 11:50:48`, matching rounds 208/214/226/232/238/244/256 exactly
  — **same boot**, now ~25h44m in at round start.

## Finding 1: the baseline read already shows growth since round 256

First action this round was a direct cgroup read (not yet a poll) to establish a fresh
baseline, per round 256/261's own stated protocol:

| | `memory.swap.current` | `t_unix` (approx) | boot-relative uptime |
|---|---|---|---|
| round 256 last sample | 1,548,619,776 B | 1787917132.57 | ~23h48m |
| round 262 baseline read | 1,625,858,048 B | ~1787924117 | ~25h44m |

Delta: **+77,238,272 bytes (+73.66 MB)** over a gap of **7041.8s (1.956h)** between round
256's last sample and this round's first read — an average rate of **39.5 MB/hr if
smeared uniformly across the whole gap**, though (as below) the true burst is almost
certainly much shorter and faster than that, since no round was polling during this gap.

Corroborated exactly by `/proc/vmstat`: `pswpout` grew by precisely 18,857 pages
(`18857 × 4096 = 77,238,272` bytes) — an **exact** match to the cgroup delta, not just
"roughly" as round 244 phrased a similar cross-check. `pswpin` grew by only 7 pages and
had **zero** effect on `memory.swap.current` — consistent with `/proc/meminfo`'s
`SwapCached: 33560 kB` at read time: a swapped-in page stays counted against swap space
until it's evicted from the swap cache, not the instant it's read back in, so a handful of
page-ins don't show up as a swap.current decrease.

`who -a`, `memory.events` (`max` still exactly 1017, unchanged since round 214, even
across this new burst), `--cap 256` (confirmed live via `systemctl --user show
qwen36-colibri.service -p ExecStart`), the E3 patch, and the OLMoE tarball were all
spot-checked present/unchanged; no operator login; `journalctl --user -u
qwen36-colibri.service --since <round-256-end>` returned zero entries (no restart, no
logged request activity in this unit's own journal).

## Finding 2: an immediate fresh 20-minute tight poll caught the burst already over — a SECOND time

Per round 256/261's own instruction ("reach for the tight-poll tool immediately"),
deployed `nuc/swap_watch.py` (`scp`'d fresh to `/tmp/swap_watch.py` — round 256's copy
was not left on the box, `find` confirmed nothing under `~/nuc-research` or `/tmp`
matching `*swap*` before this round's scp) and ran:

```
python3 swap_watch.py --interval 15 --duration 1200 --out /tmp/swap-watch-round262.json
```

Launched via `Bash(run_in_background=true)` with the `ssh ... python3 swap_watch.py ...`
command as the direct foreground command (no extra `nohup`/`&` wrapper — round 257's
documented double-backgrounding pitfall), then blocked on it with two chained
`TaskOutput(block=true, timeout=600000)` calls inside this round's own turn (round 256's
proven pattern; 1200s total run time needed two 600s blocking windows).

**Result: 81 samples over 1200.07s, ZERO growth, ZERO bursts** —
`memory.swap.current`, `memory.current`, and `pswpout` were byte-for-byte identical
across every sample (first == last == 1,625,858,048 B). One single-page `pswpin` blip
(16341→16342, one 4 KiB page) occurred somewhere mid-window with no visible effect on
`memory.swap.current` or `memory.current` — noise, not a burst (round 244's 1 MiB burst
threshold correctly ignores it).

This is the SAME shape round 256 found (a burst has just finished before the tight poll
starts) and the same shape round 244 found on the earlier 30h boot — now reproduced a
**third time total, second time on this boot**, at a boot-age (~25h44m-26h04m) well past
round 256's own "may have gone quiescent around the 20h mark" hypothesis.

Raw sample JSON committed at `state/nuc-swap-watch-r262/swap-watch-round262.json`.

## Interpretation: this settles the open question in the "still recurring" direction

Round 256/261 left exactly two live hypotheses:
1. Growth has permanently stopped around the ~20h mark on this boot.
2. Growth continues but at an increasingly rare/low frequency, and round 256's ~3h50m
   flat window just landed between bursts.

**Finding 1 above rules out hypothesis 1 outright**: a real burst of +73.66 MB occurred
strictly AFTER round 256's own last flat sample (23h48m) and strictly BEFORE this round's
baseline read (25h44m) — growth did not stop for good. Combined with Finding 2 (another
flat window immediately follows), the full picture for this boot is now:

```
208 (2h40m) ──steady growth──> 244 (20h02m) ──FLAT ~3h46m──> 256 (23h48m)
   ──BURST (~1h56m gap, exact timing unresolved)──> 262 baseline (25h44m)
   ──FLAT 20min (tight-polled)──> 262 end (~26h04m)
```

This is squarely hypothesis 2's shape (burst / quiescent-interval / burst / quiescent-
interval), not hypothesis 1's. It also revises round 256's own specific wording — "may
have gone fully quiescent around the ~20h mark" — which is now falsified: quiescence was
temporary, not the process reaching a terminal state.

**What's still NOT resolved**: the exact duration and instantaneous rate of the burst
found in Finding 1. It happened somewhere inside a ~1h56m gap nobody was polling during —
the 39.5 MB/hr figure is a lower bound on peak rate (a real burst compressed into a
shorter sub-window would have a higher instantaneous rate, same caveat round 244 raised
about wide-window deltas). Two consecutive quiescent-then-burst cycles (round 244's
finding + this round's) is not enough data to fit a real inter-burst-interval
distribution — that would need several more of these round-boundary baseline checks
banked over time, ideally with tighter round-to-round spacing to shrink the "unresolved
gap" window each time.

## Recommendation for next E round

1. **Keep doing the cheap thing first**: a plain baseline `memory.swap.current` read
   compared against this round's own final value (1,625,858,048 B) costs ~2 SSH
   one-liners and, per this round's own result, is diagnostic on its own — a match means
   "still in the same quiescent interval," a mismatch means "another burst happened,
   worth a tight poll." This is now the third round in a row this exact protocol has
   produced a clean, unambiguous answer; no reason to change it.
2. If several more rounds all land during quiescent intervals with no growth at the
   baseline check, that starts to actually support "these bursts really are becoming
   rarer" rather than just "we haven't gotten unlucky with timing yet" — worth explicitly
   tallying burst-count-per-elapsed-boot-hour across rounds once there are 4-5 data
   points, not just eyeballing gaps as this round and round 244 did.
3. A single long-running (multi-hour) `swap_watch.py` invocation left running across a
   whole round (rather than 15-20 min) would be the only way to actually catch a burst
   IN PROGRESS and measure its true duration/rate directly, closing the "unresolved gap"
   caveat above — not attempted this round (would consume most of a round's own time
   budget for an uncertain payoff, same tradeoff round 256/261 already weighed).
4. E1-E5 remain fully DONE; no `bench.py` point was needed for this finding (this round
   never touched ports 8000/8080, read-only cgroup/vmstat/systemctl introspection only).
