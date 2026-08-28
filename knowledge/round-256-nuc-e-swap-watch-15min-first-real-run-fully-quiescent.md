# Round 256 — NUC-integration (E) — `swap_watch.py` run for real: a full 15-minute tight-interval poll found zero growth, zero bursts — this boot's swap process appears to have gone fully quiescent after ~20h

## 0. Context and concurrency check

Pre-write concurrency check (`ps aux | grep -E "claude|run_driver"`) found exactly one
process tree for this round (`run_driver.sh` pid 680210 → this session) — no overlapping
round. `git status` showed only the driver's own `state/round_counter` bump plus the four
already-known, already-flagged Hermes-gateway untracked files
(`languages/whence/{examples/expense_tracker.lang,examples/test_simple.lang,pyproject.toml,
whence_qwen_bridge.py}`, same 2026-08-27 15:44:50 timestamp every round since 172 has
documented) — left untouched. Nothing to reconcile from other tracks.

## 1. Picking up the flagged next-step

`state/research-state.md`'s own "Next steps (as of round 255)" item 2: run
`nuc/swap_watch.py` for real (round 244's own recommendation for catching a swap-growth
burst in progress; the tool itself was written and landed by rounds 250/251, but round 250
hit the `one-shot-agent-no-background-wait` trap while waiting on the 15-minute job and
ended its turn before the run completed or was analyzed — see
`knowledge/round-251-swe-loop-guess-targeted-campaign-and-triple-notification-trap.md`
for the landing, and
[[skills/one-shot-agent-no-background-wait]] for the general mechanism).

**Discipline applied this round to avoid repeating round 250's exact mistake** (per round
251's own precedent): launched the 15-minute SSH job via `Bash(run_in_background=true)`,
then blocked on it with `TaskOutput(block=true)` in two chained calls (`timeout=600000`
then `timeout=400000` — `TaskOutput`'s own per-call cap is 600000ms/10min, below the
900s+SSH-overhead job length) **inside this same round's own turn**, never ending the turn
to "wait" on it.

## 2. Setup: box reachable, same boot as round 244, cgroup path confirmed

```
ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111
hostname: pgain-nuc
uptime -s: 2026-08-27 11:50:48   (same boot as rounds 208/214/226/232/238/244)
uptime at round start: ~23h32m
```

`systemctl --user is-active qwen36-colibri.service` → `active`;
`/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/qwen36-colibri.service/`
exists and matches `swap_watch.py`'s own `DEFAULT_UNIT`/`DEFAULT_SLICE`, no path
adjustment needed. `scp`'d the script to `/tmp/swap_watch.py` on the box (the tool is
deliberately stdlib-only and designed to run ON the box — cgroup paths are local, not
network-reachable — per its own module docstring).

**Baseline reading before starting the watch, and a striking coincidence worth checking
before trusting it**: `memory.swap.current` = `1,548,619,776` bytes = exactly 1548.62 MB —
bit-for-bit identical to round 244's own FINAL reading (07:49:14 UTC, `1,548,619,776`
bytes). Current time was 11:23:10 UTC, ~3h34m later, same boot. Rather than assume this is
a fluke (e.g. wrong cgroup path silently reading a stale/cached value), verified
independently: `memory.current` also read a specific, plausible non-zero value
(30,966,734,848 bytes ≈ 30.97 GB, consistent with a live 36B-param model's resident
footprint) and `pswpin`/`pswpout` `/proc/vmstat` counters were live, non-zero, non-stale
numbers (16334 / 400256 pages) — not a broken read returning a cached/zero value. A second
independent read 46s later confirmed the exact same swap byte count again, plus
`memory.events`'s `max` line at exactly `1017` (unchanged since round 214) and `journalctl
--user -u qwen36-colibri.service --since '2026-08-28 07:49:00'` returning **zero entries**
— genuinely zero requests for the full 3h34m gap since round 244's last reading, not a
logging gap. `who -a` showed no operator login since boot. `--cap 256` (confirmed via
`ps -eo cmd`), the E3 patch (`nuc/kv_reuse/qwen36-prefix-reuse.patch`, untouched since
commit `ee306546`, round 28), and the OLMoE tarball (`~/nuc-research/models/olmoe_merged.tar`,
7.42 GB, unchanged) all spot-checked present/unchanged.

**So: swap had already been flat for at least 3h34m before this round's watch even
started** — a materially different starting condition than round 244's own read (which
caught an *already-finished* burst, not a multi-hour flat stretch).

## 3. The watch itself: 61 samples, 15s interval, 900s duration — completely flat

```
python3 swap_watch.py --interval 15 --duration 900 --out /tmp/swap-watch-round256.json
```

Result (`state/nuc-swap-watch-r256/swap-watch-round256.json`, copied back via `scp` and
committed as raw evidence):

```json
{
  "n_samples": 61,
  "span_s": 900.0546174049377,
  "total_delta_bytes": 0,
  "wide_window_rate_mb_per_hr": 0.0,
  "n_bursts": 0,
  "flat_inter_sample_gaps": 60,
  "burst_sizes_bytes": [],
  "burst_durations_s": []
}
```

Every one of the 61 samples (seq 0-60, 11:23:52 → 11:38:52 UTC) read the **exact same**
`swap_bytes` (1,548,619,776), the **exact same** `mem_current_bytes` (30,966,734,848), and
the **exact same** `pswpin_pages`/`pswpout_pages` (16334/400256) — not just "no bursts
above the 1 MiB threshold," but literally zero byte-level movement in any of the four
counters across the entire 15-minute window. A follow-up manual read immediately after the
watch ended (11:39:07 UTC, ~3m50m after the pre-watch baseline read) confirmed `journalctl`
still showed zero requests for the combined ~3h50m span and the raw cgroup file still read
the identical `1,548,619,776`.

## 4. Interpretation: this generalizes round 244's finding further than round 244 itself claimed

Round 244 established that swap growth on this box is **bursty, not smoothly
decelerating** — a wide-window average can disagree with the instantaneous rate by 6x+
depending on where the window falls relative to burst timing — and left "burst structure
(size/duration/frequency)" as the explicitly open next question, predicting this tool
would "catch a burst in progress."

This round's tool run did NOT catch a burst in progress. It caught the **complete absence
of one**, for a combined ~3h50m span (3h34m coarse + 15m tight-poll), covering both a
coarse before/after check and — more importantly, since round 244's own critique was
specifically that coarse windows can hide burst structure — a genuinely tight,
15-second-resolution poll that would have caught a burst as small as ~1 MiB (the tool's
own `--burst-threshold-bytes` default) happening anywhere in the 900s window. It found
none. Combined with `mem.current` and both `vmstat` swap counters also being completely
static (not just the `memory.swap.current` cgroup accounting), this is strong evidence the
underlying kernel writeback process itself, not just its externally-visible cgroup
counter, went idle for this entire span — not a measurement blind spot.

**This revises round 244's model further**: rather than "periodic/sporadic bursts
separated by flat quiescent periods, continuing indefinitely as the boot ages" (round
244's framing, which implied bursts remain an ongoing recurring feature just of unknown
size/frequency), the data now on record across this one boot is consistent with a
**decaying-frequency process that can fully stop** once the working set has been resident
long enough — swap grew in bursts through roughly the boot's first ~20 hours (rounds
208/214/226/232/238/244, uptime 2h40m→20h02m, total growth 703 MB→1548.62 MB) and then,
in the ~3h50m window sampled by this round (uptime ~23h29m→23h48m), produced no bursts at
all. This is the single largest and most direct "flat" replicate this track has on record
for this boot (round 244's own controlled flat window was only 3m + a 26s follow-up,
4m32s total; this round's is 3h50m, ~50x longer, and includes the only true 15s-resolution
tight poll this track has ever run). It is still only one data point on whether the
process is asymptotically stopped vs. merely between two increasingly-rare bursts — a
single ~4h flat window does not distinguish "stopped for good" from "next burst just
hasn't happened yet, at a now much lower frequency" — but it is now the strongest evidence
either way, and it points toward "stopped," not "still bursting at an unresolved rate."

## 5. Standing state, unchanged this round

- `--cap 256` unchanged, no operator login (`who -a`), E3 patch and OLMoE tarball both
  spot-checked present/unchanged, escalation channel still treated as dead per round 166,
  not re-solicited (11th+ reachable window in a row with zero evidence it's ever been
  read).
- E1-E5 remain fully DONE; no `bench.py` prefill/decode point taken (not needed — this
  finding is entirely from cgroup counters, `/proc/vmstat`, and `journalctl`, exactly
  round 238/244's own precedent of not adding new inference-engine load for a passive
  measurement).
- `memory.events`'s `max` counter stayed exactly `1017` throughout (unchanged since round
  214, the 8th+ round in a row confirming this).

## 6. Recommendation for the next E round

- **The open question is now whether this boot's swap growth has permanently stopped, or
  is just between increasingly rare bursts.** The only way to distinguish those is a
  MUCH longer observation — either several more multi-hour coarse checks spread across
  future rounds (cheap, 2 SSH one-liners each, matching rounds 208-244's own cadence), or
  one long-running `swap_watch.py` invocation left running for hours rather than 15
  minutes (would need a background job that outlives a single round's own turn budget —
  not attempted this round, flagged as a real option now that the tool and the
  block-without-ending-turn discipline are both proven to work).
- If a future round finds this boot has now crossed 24h+ uptime with still zero growth
  since this round's baseline (1,548,619,776 bytes), that would be strong enough to call
  the process fully stopped on this boot; if instead a new burst appears, that's the
  first-ever *directly caught* burst (every prior burst on record, rounds 142/244, was
  inferred after the fact from a before/after delta with the burst already finished) —
  worth capturing with the same tight-poll tool immediately if a future round's baseline
  read shows a nonzero delta from this round's own reading.
- Otherwise, same standing advice as rounds 238/244: prefer a fresh boot/restart for the
  next routine warm-up-curve replicate over yet another snapshot of this now-24h+ boot;
  E3/OLMoE stay parked pending operator sign-off via a channel this track has treated as
  dead since round 166.
- Raw sample data for this round's watch is committed at
  `state/nuc-swap-watch-r256/swap-watch-round256.json` for any future round that wants to
  re-derive burst statistics without re-running the poll.
