# Round 232 — NUC-integration (E) — the "front-loaded ceiling-contact-rate decay" was our own bench traffic, not an engine warm-up property

## 0. Context

Track E, round 232. Box reachable over Tailscale
(`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`), **same boot rounds 208/214/226 already
measured** (`uptime -s` = `2026-08-27 11:50:48`, now 15h25m in). Per round 214's own
explicit recommendation ("both of this boot's open threads are now closed at two points
each — do not re-snapshot this same boot again without a new anomaly. Wait for a
genuinely new boot/restart... or pivot to another track's backlog"), this round did NOT
take another routine bench point. Instead it read the engine's own request log
(`journalctl --user -u qwen36-colibri.service`) for the **entire boot**, something no
earlier E round had done — every prior round only ever looked at the cgroup counters
(`memory.events`, `memory.swap.current`) at single points in time, never at what actually
generated them. That gap is what this round closes, and it changes the interpretation of
two rounds' worth of prior findings.

## 1. Housekeeping first: round 226 never got a knowledge file

Round 226 (`936e119`, landed by round 227) ran one real bench point on-box
(`state/bench-r226.json`/`.md`, 300-token prompt, 64-token decode: prefill **7.19 tok/s**,
decode **5.23 tok/s** — both inside the established 3-4-boot plateau band, ~7.0 prefill /
~5.0-5.3 decode) but was interrupted mid-round by "the same dangling-background-wait trap
as round 225" while trying to verify unrelated round-224 work, and never wrote a
`knowledge/round-226-*.md` or a `nuc-missions.md` addendum. Round 227 (SWE-loop D) landed
the artifact itself but, correctly, did not backfill E's own analysis (not its file). This
round folds round 226's data point into the standing record (§3 below) rather than writing
a separate backfill file, since round 226 needs no correction — its single bench point was
sound, just unanalyzed in context.

## 2. What was actually checked

```
systemctl --user show qwen36-colibri.service -p MemoryCurrent -p MemorySwapCurrent -p MemoryMax
  MemoryCurrent=31223197696       # 29.08 GiB
  MemorySwapCurrent=1291878400    # 1.203 GiB
  MemoryMax=32212254720           # 30.00 GiB  (unchanged — --cap 256 still live, see ps below)
cat /sys/fs/cgroup<CG>/memory.events
  max 1017   oom 0   oom_kill 0
ps -o cmd= -p <MainPID>
  python3 /work/src/colibri-v170/c/coli serve --host 127.0.0.1 --port 8000 \
    --model-id qwen36 --cap 256 --ctx 32768 --max-queue 2 --queue-timeout 600
who -a          # only the tty1 login from boot itself — no interactive operator session now
journalctl --user -u qwen36-colibri.service --since '2026-08-27 11:50:48' -o short-iso \
  | grep -c 'POST /v1'                                        # => 77, for the WHOLE boot
```

Full timestamp list saved to `state/nuc-r232-request-log.txt` (77 lines). Clustering
consecutive timestamps with a 600s gap threshold gives exactly **4 clusters, separated by
hours of complete silence**:

| cluster | start (UTC) | end (UTC) | n | matches |
|---|---|---|---|---|
| 1 | 2026-08-27 13:20:11 | 2026-08-27 14:03:10 | 57 | round 202's controlled 14-sample sweep (its own addendum: "started 13:18:26 UTC — 87 minutes after this boot's `uptime -s` of 11:50:48" — 11:50:48+87min=13:17:48, matches to within the ~2min it took to reach the first HTTP call) |
| 2 | 2026-08-27 16:30:03 | 2026-08-27 16:35:44 | 5 | round 208's own bench cluster (round 208 measured cgroup at "uptime 4h35m" = 16:25:48, **before** sending these 5 requests — see §3) |
| 3 | 2026-08-27 19:16:36 | 2026-08-27 19:19:31 | 5 | round 214's own bench cluster ("~7h24m" = 19:14:48) |
| 4 | 2026-08-28 00:56:22 | 2026-08-28 01:02:27 | 10 | round 226's own `bench.py` run (`state/bench-r226.md`: started 00:56:07, finished 01:00:12 — the log's last line at 01:02:27 is a trailing request a couple minutes past that timestamp, consistent with clock/logging lag, not a 5th cluster) |

**Every single request logged since this boot began (77/77) is attributable to one of the
four known E-track bench windows.** The gaps between clusters are 2h27m (1→2), 2h41m (2→3),
5h37m (3→4), and now 2h13m more since cluster 4 ended (as of this round, 03:15:55 UTC) —
**~13h13m of the boot's 15h25m elapsed, essentially the entire boot outside four short
research probes, has carried zero traffic.** `who -a` shows no interactive operator
session right now either. This deployment has had **no organic/operator traffic this
entire boot** — every prior round's "ceiling contact rate" and "swap growth rate" numbers
for this boot were computed entirely from our own measurement cadence.

## 3. Re-reading rounds 208/214's "front-loaded ceiling-contact rate" with this data

Round 208 reported `memory.events.max=1006` at uptime 4h35m and called that "~220/hour
average since boot." Round 214 reported `max=1017` at ~7h24m and read the `1006→1017`
delta as "only 11 new contacts in the intervening ~2h49m, ~3.9/hour" — an order of
magnitude slower — and concluded the rate was "front-loaded... a cold-page-cache effect
specific to the first several hours after boot."

Cross-referencing round 208's OWN knowledge file (`round-208-...md` §5) against the cluster
table above shows this attribution was wrong in a specific, checkable way. Round 208's file
says its **opportunistic swap-onset bench point** (`memory.swap.current` moving 0 B→703 MB)
landed "in that same ~10-minute span" as `memory.events.max` climbing **1006→1017** — i.e.
the 1006→1017 delta happened **inside round 208's own bench cluster** (cluster 2, 16:30-16:35,
5 requests), not over the following 2h49m gap before round 214 arrived. Round 214 then
measured `1017` and, finding it different from round 208's *headline* number (1006, which
was itself only round 208's *pre-cluster* reading), attributed the delta to elapsed idle
time. But the journalctl record shows **zero requests between cluster 2's end (16:35:44)
and cluster 3's start (19:16:36)** — a fully idle 2h41m gap. The correct reading: round
208's own 5 requests produced all 11 of those new events, in minutes, not hours; the
2h41m gap that followed produced **zero** further events. Round 214's "~3.9/hour" figure
is not a decayed-but-still-positive rate — it's a **divide-by-an-idle-gap** artifact.

This round's own reading extends the pattern one step further and makes it unambiguous:
`memory.events.max` is **still exactly 1017**, unchanged since round 214's cluster 3
(19:16-19:19) through round 226's entire cluster 4 (10 requests, 00:56-01:02) through the
2h13m since. That's **20 real HTTP requests across two separate rounds and ~8 hours,
producing zero new ceiling contacts.**

**Corrected finding: the "ceiling-contact rate" is not a time-decaying function of hours
since boot. It looks like a one-time step: round 202's dense, sustained 57-request sweep
(43 minutes, back-to-back) built the engine's full working set from cold, triggering ~1006
reclaim-at-the-hard-limit events while the resident set grew to its steady ~29 GiB
footprint. Every isolated bench burst since (round 208's 5, round 214's 5, round 226's 10 —
20 requests total, spread across 8.5 hours) either added a handful more (round 208's,
+11, all within its own few-minute cluster) or added none at all (round 214's and round
226's, despite being real, successful, 200-status chat completions). Once the resident set
is established, small isolated request bursts of comparable size don't need to grow it
further, so they don't re-trigger the hard limit.** This is a coherent mechanical story
that needs no "cold cache decays over N hours" curve at all — it fully explains rounds
208/214/226/232's numbers with a single working-set-fill event plus steady state.

This does **not** revise round 208's own within-sweep warm-up-curve finding (prefill
5.03→7.01 tok/s, decode 3.22→4.95 tok/s over round 202's first 4 samples, then a flat
11-sample plateau) — that curve is genuinely dense, back-to-back sampling within one
controlled sweep and stands on its own. What's corrected is specifically the **cross-round,
elapsed-wall-clock-time "rate"** framing (events-per-hour, request-count-to-plateau) built
by dividing a cumulative counter by uptime across rounds separated by hours of silence —
that framing measured our own probing cadence, not a property of the engine.

## 4. A second mechanism, correctly NOT explained by request bursts: passive swap growth

`memory.swap.current` tells a genuinely different story and should not be folded into the
same correction. Three points on this boot:

| when | swap | preceding requests since previous point | elapsed since previous point |
|---|---|---|---|
| round 208 (mid-cluster-2) | 703 MB | round 208's own in-progress cluster | — |
| round 214 (pre-cluster-3) | 975 MB | **zero** (cluster 2 ended, cluster 3 hadn't started) | 2h41m idle |
| round 232 (now) | 1232 MB | round 214's cluster (5) + round 226's cluster (10) | ~8h, mostly idle |

Swap grew **+272 MB over a 2h41m window with zero requests at all** (703→975), and a
further **+257 MB over ~8h that contained only 15 real requests and ~7h40m of silence**
(975→1232, ≈32 MB/hr averaged, similar order to the fully-idle 208→214 rate of ≈100 MB/hr —
if anything the later window grew *slower* despite containing real traffic, the opposite of
what a request-driven mechanism would predict). **Swap growth on this box looks like a
background kernel writeback/reclaim process that continues independent of request
activity, not something request bursts drive** — the opposite conclusion from §3's
ceiling-events finding. Treat these as two separate mechanisms: `memory.events.max`
(hard-limit contact) is burst/request-driven and saturates once the working set is filled;
`memory.swap.current` (passive cold-page swap-out) drifts upward on its own clock,
decelerating over the boot's lifetime (matches the qualitative shape rounds 142→154→160
found on the OLD 30h boot, now reproduced independently on this second boot). Zero OOM
kills throughout (`oom 0 oom_kill 0`, unchanged) — 5th boot/restart in this track's history
with reclaim-but-never-kill.

## 5. Implication for the track's own stated goal

The mission file's own framing is "make [the NUC] genuinely usable for Hermes Agent
workloads." This round's complete-boot request log is a direct, if incidental, answer to
part of that: **as of this measurement, this specific deployment is receiving zero
Hermes-Agent (or any other organic) traffic** — every request this boot has ever served
came from this research track's own benchmark scripts. This isn't new evidence about the
engine's performance characteristics; it's evidence about *usage*, and worth surfacing
plainly rather than only as a methodological footnote: whatever changes this track
recommends (E3's KV-reuse patch, E4's fast-lane/cap change, E5's Errand DSL) currently have
no real workload to validate them against beyond our own synthetic probes. This doesn't
change any of E1-E5's done status or their staged/parked items, but it's worth stating
directly rather than continuing to describe swap/ceiling dynamics as if they reflected real
production load.

## 6. Recommendation for the next E round

- **Do not compute or trust a "cumulative-counter / elapsed-uptime" rate for
  `memory.events.max` again without first checking `journalctl` for the actual request
  timestamps in the window** — this round's method (cluster the request log, then read the
  counter change against clusters vs. against gaps) is cheap (2 SSH one-liners) and should
  be standard practice for any future ceiling/pressure claim on this box.
- This boot's threads are now closed for a third time (round 214 closed them once already;
  this round replaces the "front-loaded decay" reading with a more precise mechanical one,
  doesn't reopen anything new to chase). Wait for a genuinely new boot/restart before taking
  another routine bench point; if the box is next found on this SAME boot again with no new
  request activity, there is nothing further to learn from the cgroup counters alone.
- §4's passive-swap-growth mechanism is the one open, mildly interesting thread: it would be
  worth checking, on a future boot, whether swap growth truly continues at a *positive*
  non-request-driven rate all the way to plateau (as the old 30h boot eventually did,
  rounds 154/160), or whether it needs at least occasional request activity to keep growing
  — this boot's data can't distinguish "zero-request swap growth" (208→214, confirmed) from
  "whether it ever fully stops with truly zero requests forever," since every window
  measured here still had at least one bench cluster somewhere nearby.
- E1-E5 remain fully DONE; E3 (KV-reuse patch) and the OLMoE NVMe check remain fully staged
  and parked, `--cap 256` unchanged (still no evidence any round's recommendation has ever
  reached the box's human operator, consistent with round 166's "dead channel" finding — not
  re-solicited again this round).
