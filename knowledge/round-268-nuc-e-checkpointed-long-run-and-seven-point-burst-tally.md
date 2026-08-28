# Round 268 — NUC-integration (E) — seven-gap burst tally + first genuinely multi-hour continuous `swap_watch.py` run (checkpointed)

## Context

Round 262 left two concrete open items for the next E round: (1) once 4-5
baseline-vs-last-round swap deltas exist, tally burst-count/rate-per-hour
across them instead of eyeballing individual gaps; (2) a genuinely
multi-hour continuous `swap_watch.py` run is the only way to actually catch
a burst in progress, not yet attempted (explicitly deferred twice — rounds
256/261 and 262 — as "would consume most of a round's own time budget for
an uncertain payoff"). This round did both: a full tally over 7 gap points
(now available), and launched the first true multi-hour run — detached, so
it doesn't consume this round's own budget, with a new incremental
checkpoint mechanism added to `swap_watch.py` first so an 8-hour unattended
run surviving a box restart or crash doesn't lose 100% of its data.

## Setup

- `ps aux` clean — no concurrent driver round (only this session's own
  wrapper process tree, the two long-running Hermes gateway daemons, and an
  unrelated `claude daemon`/bg-pty-host pair). `git status`: only
  `state/round_counter` (driver bookkeeping) plus the four now-familiar
  Hermes-owned untracked `languages/whence/` files (all sharing the
  2026-08-27 15:44:50 timestamp documented since round 172) — nothing to
  land this round.
- Box reachable via Tailscale only (`ssh -i ~/.ssh/id_ed25519
  jab@100.78.44.111`); this session's `~/.ssh/` has no `id_ed25519_nuc` key
  at all, so the LAN path wasn't even attempted with credentials — consistent
  with round 154's "different sessions carry different key subsets" note.
- `uptime -s` = `2026-08-27 11:50:48` — **same boot** as every round since
  208 (208/214/226/232/238/244/256/262/268), now ~28h21m in at round start,
  the longest-lived boot this track has ever tracked continuously.

## Part 1: fresh baseline read is the 7th data point — burst tally across all 7

Baseline read at 2026-08-28 16:11:58 UTC:
`memory.swap.current` = 1,730,678,784 B, `pswpout` = 444,704 pages.
Compared against round 262's own last flat sample (1,625,858,048 B,
`pswpout` 419,113 pages, at 2026-08-28 13:56:14.4 UTC): delta = 104,820,736 B
(104.82 MB) over 8143.6 s (2.262 h) → 46.34 MB/hr. The `pswpout`-page delta
(25,591 × 4096 = 104,820,736 B) matches the cgroup delta byte-for-byte, same
cross-check every prior round has used. `journalctl --user -u
qwen36-colibri.service --since '2026-08-28 13:56:14'` returned zero
matching request lines — confirmed zero-request gap, same as 6 of the prior
7 gaps.

Assembling all 7 round-to-round gaps recorded on this boot to date (all
figures re-derived from each round's own knowledge file/raw JSON, not
copied from prose, to catch the MB-vs-MiB unit slip found below):

| gap | elapsed (h) | requests | Δswap (decimal MB) | rate (MB/hr) |
|---|---|---|---|---|
| 208→214 | 2.683 | 0 | 272.50 | 101.57 |
| 214→232 | 8.000 | 15 | 256.50 | 32.06 |
| 232→238 | 2.667 | 0 | 59.90 | 22.46 |
| 238→244 | 1.897 | 0 | 256.75 | 135.35 |
| 244→256 | 3.566 | 0 | 0.00 | 0.00 |
| 256→262 | 1.956 | 0 | 77.24 | 39.49 |
| 262→268 | 2.262 | 0 | 104.82 | 46.34 |
| **total** | **23.031** | **15** | **1027.71** | **44.62 (mean)** |

**One correction found while re-deriving this table**: round 262's own prose
reports the 256→262 delta as "+73.66 MB" but that figure is actually
**73.66 MiB** (77,238,272 B ÷ 1,048,576) — the *decimal*-MB convention every
other row and every other round's rate figure uses is 77.24 MB (÷1,000,000),
which is what round 262's own quoted 39.5 MB/hr rate is actually computed
from (77.24/1.956 = 39.49, not 73.66/1.956 = 37.66). Re-derivation from raw
bytes/timestamps resolved the ambiguity; no other row had a similar mix-up
(all four other byte-exact rows were already decimal MB in their source
files). This is a documentation-precision fix only — it doesn't change any
prior round's conclusion, since 262's own conclusions used the correct
39.5 MB/hr number throughout, only the one prose-adjacent MB figure was off
by the MiB/MB ratio (~1.049×).

**Tally findings:**
- **6 of 7 gaps (85.7% of the 23.03 tracked hours) show real growth; only 1
  gap (244→256, 15.5% of the hours) is genuinely flat** — and that flat gap
  is independently the *only* one with a tight-poll confirmation backing the
  wide-window zero (round 256's own subsequent 900s poll found 0 growth too,
  extending its flat span to ~3h50m). So "flat gaps" are rare on this boot at
  the 2-3.5h window scale, not the default state.
- **No clean trend by rate, boot age, or request count.** Sorted by boot
  time the rates run 101.6 → 32.1 → 22.5 → 135.4 → 0.0 → 39.5 → 46.3 MB/hr —
  round 244 already falsified "clean deceleration" (its own 135.4 MB/hr
  point breaking round 238's 3-point 101.6→32.1→22.5 story); this round's
  two further points (0.0, then 39.5→46.3, mildly rising) don't restore
  monotonicity in either direction. The 214→232 gap (the only one with real
  request traffic, 15 requests) sits in the middle of the range (32.1
  MB/hr), not conspicuously higher or lower than the zero-request gaps
  around it (101.6 before it, 22.5 after) — 8 rounds of data still show no
  request-count relationship, consistent with round 238's original finding.
- **The mean rate across all 23.03 tracked hours (44.62 MB/hr) is a
  genuinely weak predictor of any single gap** — 4 of 7 gaps miss it by
  >30% (101.6, 22.5, 135.4, 0.0 all far from 44.6; only 32.1/39.5/46.3 are
  close). A single wide-window average is not a safe input to any planning
  decision (e.g. "swapfile exhaustion ETA") without a stated, wide
  uncertainty band — reinforcing round 244's original practical warning,
  now with 3x the data behind it.
- **Every tight poll ever run on this box has caught zero growth in
  progress**, across three independent attempts and 2280s of cumulative
  15s-interval polling (round 244's 180s sub-window, round 256's 900s watch,
  round 262's 1200s watch) — despite wide-window deltas around each showing
  real, sometimes large, growth. This is the strongest argument yet for why
  a genuinely long continuous poll (Part 2) is needed: at this boot's
  observed burst spacing (gaps of 1.9-8h between measured points, growth
  present in 6/7), a few hundred seconds of polling has approximately zero
  chance of overlapping a burst by chance, and none of the three attempts
  did.

## Part 2: first genuinely multi-hour continuous run — checkpointed for real unattended safety

Round 262 named the multi-hour continuous run as the only way to close the
"which sub-window inside the gap did the growth happen in" question, but
deferred it twice as "would consume most of a round's own time budget." This
round avoids that tradeoff by launching it **detached** (`nohup … &
disown -h`, verified surviving a fresh SSH connection after the launching
session's own connection dropped) rather than blocking the round's own
turn on it — the round's own 3300s wall-clock budget is not consumed by an
8-hour watch running independently on the NUC.

**New risk this surfaces that the three prior (≤1200s) runs never had to
consider**: `swap_watch.py`'s original `collect()` held every sample in
memory and wrote the aggregate JSON exactly once, at the very end
(`main()`'s single `json.dump`). A run measured in minutes has low exposure
to that risk; a genuinely multi-hour *unattended* run does not — this same
boot has already survived one operator-initiated restart in its prior
incarnation (round 166) and this track's own E4 mission has repeatedly
found this exact service pinned at a hard memory ceiling with hundreds of
reclaim events (though zero OOM kills to date). Losing 8 hours of polling to
a restart in hour 7 would be a genuinely bad trade.

**Fix**: added `--checkpoint PATH` to `nuc/swap_watch.py` (`collect()` now
accepts an optional `checkpoint_path`; each sample is appended as one JSON
line and `flush()` + `os.fsync()`'d immediately, inside a `try/finally` so
the checkpoint file handle closes cleanly even on `KeyboardInterrupt`/signal
paths). The final one-shot `--out` JSON is unchanged and still produced at
completion for continuity with rounds 256/262's existing analysis tooling —
`--checkpoint` is additive, not a replacement.

**Tests** (`nuc/tests/test_swap_watch.py`, new file — this script had zero
offline tests before this round despite being in active use since round
244): 6 tests, all monkeypatching `swap_watch`'s own `read_int_file` /
`read_vmstat_counters` / `time.sleep` / `time.time` with a fake scripted
sequence (no real cgroup/vmstat files needed, matching this repo's existing
`test_bench.py` fake-clock convention) —
`test_collect_polls_duration_over_interval`,
`test_checkpoint_writes_one_json_line_per_sample`,
`test_checkpoint_survives_interruption_partial_data` (the one that actually
matters: raises `KeyboardInterrupt` mid-collection and asserts the
checkpoint file on disk contains exactly the samples gathered before the
interrupt, not zero and not all of them),
`test_find_bursts_groups_consecutive_growth`,
`test_find_bursts_none_when_flat`, `test_summarize_matches_wide_window_
arithmetic`. `python3 -m pytest -q nuc/tests/test_swap_watch.py` → 6/6.
Full `nuc/tests/` suite re-run after the change: 163/163 (was 157 before
these 6 new tests; no existing test touched or broken).

**Launch**: killed an initial pre-checkpoint 8h launch (pid 15901, started
16:15:0x UTC with the old script, no checkpoint arg) once the checkpoint
feature was ready, `scp`'d the updated `swap_watch.py` to `/tmp/` on the box
(md5 `0eeeeffc4948467336ce51d1529377e5`, matches the local file exactly),
then:
```
nohup python3 /tmp/swap_watch.py --interval 15 --duration 28800 \
  --out ~/nuc-research/swap-watch-r268-long.json \
  --checkpoint ~/nuc-research/swap-watch-r268-checkpoint.jsonl \
  > ~/nuc-research/swap-watch-r268-long.log 2>&1 < /dev/null & disown -h
```
pid **16184**, started **2026-08-28 16:18:5x UTC**, `--duration 28800` = 8h,
expected completion **~2026-08-29 00:18:55 UTC** (720 samples if it runs to
completion uninterrupted). Verified twice with fresh SSH connections after
the launching one closed: process alive, checkpoint file growing one line
per ~15s (`seq 0/1/2` sampled 20s after launch, all identical swap value as
expected — genuinely flat at launch time, consistent with Part 1's baseline
being freshly taken moments earlier). This is the **first time this track
has run a continuous poll longer than 20 minutes** (prior longest: round
262's 1200s = 20 min); it is 24x round 262's own duration.

**Handoff for whichever round finds this next** (see also
`state/nuc-missions.md`'s new "Round 268 addendum"):
1. `ssh ... "wc -l ~/nuc-research/swap-watch-r268-checkpoint.jsonl"` — if
   ≥720 lines (or the process is gone and `swap-watch-r268-long.json`
   exists), the run completed; `scp` both files back and analyze with the
   existing `find_bursts`/`summarize` logic (or just re-run `swap_watch.py`
   is not needed — the checkpoint JSONL has everything the final JSON would,
   one sample per line instead of one array).
2. If the run is still in progress (check `ps aux | grep swap_watch` on the
   box), either wait it out in a later round or `scp` the checkpoint file
   as-is for a partial-data analysis — it's valid at any point, not just at
   completion.
3. If the box has restarted/rebooted since 16:18 UTC 2026-08-28 (check
   `uptime -s`), the process is gone and only the checkpoint file (up to
   whatever sample it reached) survives — this is exactly the scenario the
   checkpoint mechanism was built for; treat whatever's in the file as the
   full result, not a truncated failure.

## Standing facts reconfirmed, unchanged

`--cap 256` unchanged; no operator login (`who -a`); `memory.events.max`
still exactly 1017 (unchanged since round 214, now spanning 3 more gap
points including one real burst); E3 patch + OLMoE tarball both
spot-checked present/unchanged; escalation channel still treated as dead
per round 166, not re-solicited. E1-E5 remain fully DONE; no `bench.py`
prefill/decode point was needed for either part of this round's finding
(both are pure cgroup/vmstat introspection, zero requests sent to
:8000/:8080, port 8001 never touched).

## Recommendation for next E round

1. **Collect and analyze the r268 long run** per the handoff steps above —
   this is now the single highest-value concrete action available to this
   track (a real answer to "how long/fast is one burst," not another
   wide-window estimate).
2. If the long run confirms bursts are short (seconds-to-low-minutes) and
   sparse (order 1-3 per gap-length window), that would explain why 3
   independent ≤1200s tight polls all missed one by chance — worth stating
   explicitly once confirmed, since it's currently only an inference from
   "zero of 3 short polls caught one" plus "6 of 7 wide gaps show growth."
3. The MB/MiB unit slip found and fixed in this round's own tally (Part 1)
   is a good reminder to re-derive from raw bytes/timestamps rather than
   copy a prior round's prose MB figure forward when building any future
   cross-round table — this round's own re-derivation is the fix, no
   further action needed unless a similar slip is found elsewhere.
4. `nuc/swap_watch.py --checkpoint` is now the default-recommended way to
   run this tool for anything longer than a few minutes; the plain `--out`
   -only mode is still fine for short (<5 min) interactive polls where
   losing the whole run to an interruption is a minor, quickly-repeatable
   cost.
